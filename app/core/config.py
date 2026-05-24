from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "FundPilot"
    app_env: str = "dev"
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/fund_watcher"
    backend_port: int = 8000
    streamlit_port: int = 8501
    sync_nav_cron: str = "18:00"
    ai_provider: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:14b"
    ollama_timeout: float = 180.0
    online_llm_api_key: str = ""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
