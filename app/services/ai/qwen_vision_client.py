from __future__ import annotations

import base64
import json
import re
from decimal import Decimal

import httpx
from pydantic import ValidationError

from app.core.config import get_settings
from app.schemas.portfolio import HoldingScreenshotDraft
from app.services import asset_service


class QwenVisionClient:
    """Minimal OpenAI-compatible Qwen-VL client for temporary image recognition."""

    provider = "qwen-vl"

    def __init__(self, base_url: str | None = None, model: str | None = None, timeout: float | None = None):
        settings = get_settings()
        self.base_url = (base_url or settings.qwen_base_url).rstrip("/")
        self.model_name = model or settings.qwen_vl_model
        self.timeout = timeout if timeout is not None else settings.qwen_timeout
        self.api_key = settings.qwen_api_key

    def recognize_holdings(self, image_bytes: bytes, content_type: str) -> list[HoldingScreenshotDraft]:
        if not self.api_key:
            raise RuntimeError("Qwen API key is not configured")
        if content_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise ValueError("仅支持 JPG、PNG 或 WebP 格式的持仓截图")
        if not image_bytes:
            raise ValueError("截图文件为空")
        if len(image_bytes) > 10 * 1024 * 1024:
            raise ValueError("截图不能超过 10MB")

        image_data = base64.b64encode(image_bytes).decode("ascii")
        prompt = """识别这张中信证券持仓截图中的实际持仓。只返回一个 JSON 对象，格式严格如下：
{"holdings":[{"asset_code":"代码","asset_type":"stock|etf|fund","asset_name":"名称","holding_share":0,"cost_price":0,"current_price":0,"market_value":0,"confidence":0.0}]}

规则：
1. 只提取能在截图中明确看出的持仓行；不要把总资产、可用资金、盈亏汇总当成持仓。
2. asset_type 只能是 stock、etf、fund；场内基金写 etf，普通股票写 stock，场外基金写 fund。
3. 数量、成本价、现价、市值看不清时填 null；没有把握的整行不要猜。
4. 代码保留 6 位数字；confidence 为 0 到 1。
5. 不要输出 Markdown、说明文字或任何 JSON 以外的内容。"""
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model_name,
                    "messages": [
                        {"role": "system", "content": "你是严谨的证券持仓表识别器。"},
                        {
                            "role": "user",
                            "content": [
                                {"type": "image_url", "image_url": {"url": f"data:{content_type};base64,{image_data}"}},
                                {"type": "text", "text": prompt},
                            ],
                        },
                    ],
                    "temperature": 0,
                    "response_format": {"type": "json_object"},
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
        except Exception as exc:
            raise RuntimeError(f"Qwen-VL 持仓截图识别失败：{exc}") from exc

        content = _response_content(response.json())
        return _parse_holdings(content)

    def check_status(self) -> dict:
        return {
            "provider": self.provider,
            "base_url": self.base_url,
            "configured_model": self.model_name,
            "timeout_seconds": self.timeout,
            "api_key_configured": bool(self.api_key),
        }


def _response_content(data: dict) -> str:
    choices = data.get("choices") or []
    if not choices:
        raise ValueError("Qwen-VL 未返回识别结果")
    content = (choices[0].get("message") or {}).get("content")
    if isinstance(content, list):
        content = "".join(str(item.get("text", "")) if isinstance(item, dict) else str(item) for item in content)
    if not content:
        raise ValueError("Qwen-VL 返回了空的识别结果")
    return str(content).strip()


def _parse_holdings(content: str) -> list[HoldingScreenshotDraft]:
    clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", content.strip(), flags=re.IGNORECASE)
    try:
        payload = json.loads(clean)
    except json.JSONDecodeError as exc:
        raise ValueError("Qwen-VL 返回的识别结果不是有效 JSON") from exc
    rows = payload.get("holdings") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        raise ValueError("Qwen-VL 未识别到持仓列表")

    holdings: list[HoldingScreenshotDraft] = []
    errors: list[str] = []
    for index, raw in enumerate(rows, start=1):
        try:
            holdings.append(_normalize_holding(raw))
        except (ValidationError, ValueError, TypeError) as exc:
            errors.append(f"第 {index} 行：{exc}")
    if not holdings:
        detail = "；".join(errors[:3]) or "截图中没有可确认的持仓"
        raise ValueError(f"没有可导入的持仓：{detail}")
    return holdings


def _normalize_holding(raw: object) -> HoldingScreenshotDraft:
    if not isinstance(raw, dict):
        raise ValueError("持仓行不是对象")
    raw_type = str(raw.get("asset_type") or "").strip().lower()
    type_map = {"股票": "stock", "stock": "stock", "equity": "stock", "基金": "fund", "fund": "fund", "etf": "etf", "场内基金": "etf"}
    asset_type = type_map.get(raw_type, raw_type)
    code = str(raw.get("asset_code") or raw.get("code") or "").strip()
    if asset_type not in {"fund", "stock", "etf"}:
        raise ValueError("资产类型无法确认")
    if not code:
        raise ValueError("资产代码为空")
    values = {
        "asset_code": asset_service.normalize_asset_code(code, asset_type),
        "asset_type": asset_type,
        "asset_name": _string_or_none(raw.get("asset_name") or raw.get("name")),
        "holding_share": _decimal(raw.get("holding_share") or raw.get("quantity") or raw.get("share")),
        "cost_price": _decimal_or_none(raw.get("cost_price")),
        "current_price": _decimal_or_none(raw.get("current_price") or raw.get("price")),
        "market_value": _decimal_or_none(raw.get("market_value") or raw.get("value")),
        "confidence": _decimal_or_none(raw.get("confidence")),
    }
    return HoldingScreenshotDraft.model_validate(values)


def _string_or_none(value: object) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _decimal_or_none(value: object) -> Decimal | None:
    if value is None or value == "":
        return None
    return _decimal(value)


def _decimal(value: object) -> Decimal:
    text = str(value).replace(",", "").replace("¥", "").replace("%", "").strip()
    return Decimal(text)
