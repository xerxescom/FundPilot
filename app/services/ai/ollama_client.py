import httpx

from app.core.config import get_settings
from app.services.ai.base import AIClient


class OllamaClient(AIClient):
    def __init__(self, base_url: str | None = None, model: str | None = None, timeout: float = 30.0):
        settings = get_settings()
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.ollama_model
        self.timeout = timeout

    def generate(self, prompt: str) -> str:
        response = httpx.post(
            f"{self.base_url}/api/generate",
            json={"model": self.model, "prompt": prompt, "stream": False},
            timeout=self.timeout,
        )
        response.raise_for_status()
        data = response.json()
        return str(data.get("response", "")).strip()
