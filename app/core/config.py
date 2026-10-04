from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "FundPilot"
    app_env: str = "dev"
    database_url: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/fund_watcher"
    backend_port: int = 8000
    sync_nav_cron: str = "18:00"
    enable_scheduler: bool = False
    auto_create_tables: bool = True
    ai_provider: str = "ollama"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "qwen3:14b"
    ollama_timeout: float = 180.0
    online_llm_api_key: str = ""
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-v4-flash"
    deepseek_timeout: float = 90.0
    qwen_api_key: str = ""
    qwen_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    qwen_vl_model: str = "qwen-vl-plus"
    qwen_timeout: float = 90.0
    # 批次与交易日历
    market_close_time: str = "15:00"
    trade_calendar_refresh_days: int = 7
    fund_disclosure_grace_trade_days: int = 3
    market_data_grace_trade_days: int = 1
    # 账户收益基线：默认对比沪深300
    benchmark_index_code: str = "sh000300"
    batch_item_max_retries: int = 3
    batch_recovery_window_days: int = 3
    interrupted_requeue_delay_seconds: int = 30
    # worker 心跳与租约
    worker_poll_seconds: float = 2.0
    heartbeat_interval_seconds: int = 15
    lease_ttl_seconds: int = 120
    shutdown_grace_seconds: int = 30

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()
