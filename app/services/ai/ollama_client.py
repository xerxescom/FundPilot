import httpx

from app.core.config import get_settings
from app.services.ai.base import AIClient


class OllamaClient(AIClient):
    def __init__(self, base_url: str | None = None, model: str | None = None, timeout: float | None = None):
        settings = get_settings()
        self.base_url = (base_url or settings.ollama_base_url).rstrip("/")
        self.model = model or settings.ollama_model
        self.model_name = self.model
        self.timeout = timeout if timeout is not None else settings.ollama_timeout

    def generate(self, prompt: str) -> str:
        try:
            response = httpx.post(
                f"{self.base_url}/api/generate",
                json={"model": self.model, "prompt": prompt, "stream": False},
                timeout=self.timeout,
            )
            response.raise_for_status()
        except Exception as exc:
            raise RuntimeError(
                f"Ollama generate failed for model `{self.model}` at {self.base_url}: {exc}"
            ) from exc
        data = response.json()
        return str(data.get("response", "")).strip()

    def list_models(self) -> list[str]:
        try:
            response = httpx.get(f"{self.base_url}/api/tags", timeout=5.0)
            response.raise_for_status()
        except Exception as exc:
            raise RuntimeError(f"Ollama tags failed at {self.base_url}: {exc}") from exc
        data = response.json()
        return [item.get("name", "") for item in data.get("models", []) if item.get("name")]

    def check_model_available(self) -> dict:
        models = self.list_models()
        return {
            "base_url": self.base_url,
            "configured_model": self.model,
            "timeout_seconds": self.timeout,
            "available_models": models,
            "model_available": self.model in models,
        }
