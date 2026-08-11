from app.core.config import get_settings
from app.services.ai.base import AIClient
from app.services.ai.deepseek_client import DeepSeekClient
from app.services.ai.ollama_client import OllamaClient


def get_ai_client() -> AIClient:
    provider = get_settings().ai_provider.lower().strip()
    if provider == "deepseek":
        return DeepSeekClient()
    if provider == "ollama":
        return OllamaClient()
    raise ValueError(f"Unsupported AI provider: {provider}")
