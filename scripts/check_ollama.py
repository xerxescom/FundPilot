"""Check whether the configured Ollama model is available.

Run this when AI reports fall back to rules and you want to verify whether
Ollama is reachable and whether `OLLAMA_MODEL` exists locally.

Run:
    uv run python scripts/check_ollama.py
"""

from app.services.ai.ollama_client import OllamaClient


def main() -> None:
    status = OllamaClient().check_model_available()
    print(f"Base URL: {status['base_url']}")
    print(f"Configured model: {status['configured_model']}")
    print(f"Timeout seconds: {status['timeout_seconds']}")
    print(f"Model available: {status['model_available']}")
    print("Available models:")
    for model in status["available_models"]:
        print(f"- {model}")


if __name__ == "__main__":
    main()
