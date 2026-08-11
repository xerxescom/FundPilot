import httpx

from app.core.config import get_settings
from app.services.ai.base import AIClient


class DeepSeekClient(AIClient):
    """OpenAI-compatible DeepSeek chat-completions client for report generation."""

    def __init__(self, base_url: str | None = None, model: str | None = None, timeout: float | None = None):
        settings = get_settings()
        self.base_url = (base_url or settings.deepseek_base_url).rstrip("/")
        self.model_name = model or settings.deepseek_model
        self.timeout = timeout if timeout is not None else settings.deepseek_timeout
        self.api_key = settings.deepseek_api_key or settings.online_llm_api_key

    def generate(self, prompt: str) -> str:
        if not self.api_key:
            raise RuntimeError("DeepSeek API key is not configured")
        try:
            response = httpx.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model_name,
                    "messages": [
                        {"role": "system", "content": "你是谨慎的个人投资复盘助手，只解释已提供的结构化事实。"},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.2,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
        except Exception as exc:
            raise RuntimeError(f"DeepSeek generate failed for model `{self.model_name}`: {exc}") from exc
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            return ""
        return str((choices[0].get("message") or {}).get("content") or "").strip()

    def check_status(self) -> dict:
        return {
            "provider": "deepseek",
            "base_url": self.base_url,
            "configured_model": self.model_name,
            "timeout_seconds": self.timeout,
            "api_key_configured": bool(self.api_key),
        }
