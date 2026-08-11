from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from app.db.models import AssetInfo, AssetPriceDaily, PortfolioPosition
from app.schemas.portfolio import HoldingScreenshotDraft
from app.services.ai import qwen_vision_client
from app.services.portfolio_service import create_transaction, import_screenshot_holdings, portfolio_overview


def test_qwen_vision_client_sends_image_and_normalizes_holding(monkeypatch):
    settings = SimpleNamespace(
        qwen_base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        qwen_vl_model="qwen-vl-plus",
        qwen_timeout=30.0,
        qwen_api_key="test-key",
    )
    captured = {}

    class Response:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": '{"holdings":[{"asset_code":"600519","asset_type":"股票","asset_name":"贵州茅台","holding_share":"10","cost_price":"1500","current_price":"1600","market_value":"16000","confidence":0.96}]}'
                        }
                    }
                ]
            }

    def fake_post(url, **kwargs):
        captured["url"] = url
        captured.update(kwargs)
        return Response()

    monkeypatch.setattr(qwen_vision_client, "get_settings", lambda: settings)
    monkeypatch.setattr(qwen_vision_client.httpx, "post", fake_post)

    result = qwen_vision_client.QwenVisionClient().recognize_holdings(b"fake-image", "image/png")

    assert result[0].asset_type == "stock"
    assert result[0].asset_code == "600519"
    assert result[0].holding_share == Decimal("10")
    assert captured["url"] == "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    image_url = captured["json"]["messages"][1]["content"][0]["image_url"]["url"]
    assert image_url.startswith("data:image/png;base64,")


def test_screenshot_import_creates_snapshot_position_and_price(db_session):
    result = import_screenshot_holdings(
        db_session,
        [
            HoldingScreenshotDraft(
                asset_code="600519",
                asset_type="stock",
                asset_name="贵州茅台",
                holding_share=Decimal("10"),
                cost_price=Decimal("1500"),
                current_price=Decimal("1600"),
                market_value=Decimal("16000"),
            )
        ],
        date(2026, 8, 11),
    )

    assert result == {"created": 1, "updated": 0, "skipped": []}
    position = db_session.query(PortfolioPosition).one()
    asset = db_session.query(AssetInfo).one()
    price = db_session.query(AssetPriceDaily).one()
    assert position.holding_amount == Decimal("15000.0000")
    assert asset.asset_name == "贵州茅台"
    assert price.close == Decimal("1600.000000")
    assert portfolio_overview(db_session)["positions"][0]["current_value"] == Decimal("16000.000000")


def test_screenshot_import_does_not_overwrite_transaction_position(db_session):
    create_transaction(
        db_session,
        {
            "asset_type": "stock",
            "asset_code": "600519",
            "trade_date": date(2026, 8, 10),
            "amount": Decimal("15000"),
            "nav": Decimal("1500"),
            "share": Decimal("10"),
        },
    )

    result = import_screenshot_holdings(
        db_session,
        [
            HoldingScreenshotDraft(
                asset_code="600519",
                asset_type="stock",
                holding_share=Decimal("20"),
                cost_price=Decimal("1200"),
            )
        ],
        date(2026, 8, 11),
    )

    assert result["created"] == 0
    assert result["updated"] == 0
    assert result["skipped"] == [{"asset_code": "600519", "reason": "已有交易流水，未用截图覆盖成本与持仓"}]
    assert db_session.query(PortfolioPosition).one().holding_share == Decimal("10.0000")
