from loguru import logger

from app.core.config import get_settings


def configure_logging(level: str | None = None, json_output: bool | None = None) -> None:
    """按配置初始化日志：LOG_LEVEL 控制级别，LOG_JSON 切换 JSON 行格式。"""
    settings = get_settings()
    log_level = (level or settings.log_level or "INFO").upper()
    use_json = settings.log_json if json_output is None else json_output
    logger.remove()
    logger.add(
        sink=lambda msg: print(msg, end=""),
        level=log_level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level} | {message}",
        serialize=use_json,
    )
