from loguru import logger

from app.db.session import SessionLocal
from app.services import daily_batch_service as batches
from app.services import trading_calendar_service


def enqueue_daily_update_batch() -> None:
    """创建（或复用）今日批次；实际执行由独立 worker 进程消费。"""
    with SessionLocal() as db:
        trading_calendar_service.ensure_calendar_coverage(db)
        batch, created = batches.create_or_get_daily_batch(db, trigger="scheduler")
        logger.info(f"每日批次{'创建' if created else '已存在'}：#{batch.id}（交易日 {batch.trade_date}）")
