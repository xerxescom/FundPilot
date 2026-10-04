from datetime import date, datetime
from typing import Any

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TaskBatch(Base):
    """一次“更新今日数据”批次；同一交易日按 idempotency_key 唯一。"""

    __tablename__ = "task_batch"

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_type: Mapped[str] = mapped_column(String(50), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(120), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    trade_date: Mapped[date | None] = mapped_column(Date, index=True)
    params_json: Mapped[Any | None] = mapped_column(JSON)
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    failure_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    pending_count: Mapped[int] = mapped_column(Integer, default=0)
    interrupted_count: Mapped[int] = mapped_column(Integer, default=0)
    coverage_json: Mapped[Any | None] = mapped_column(JSON)
    lease_owner: Mapped[str | None] = mapped_column(String(100))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)


class TaskBatchItem(Base):
    """批次中的单个步骤项；全局步骤（market/alerts/report）用空串作为资产哨兵。"""

    __tablename__ = "task_batch_item"
    __table_args__ = (
        UniqueConstraint("batch_id", "step", "asset_type", "asset_code", name="uq_task_batch_item_key"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    batch_id: Mapped[int] = mapped_column(ForeignKey("task_batch.id", ondelete="CASCADE"), index=True)
    step: Mapped[str] = mapped_column(String(50), index=True)
    asset_type: Mapped[str] = mapped_column(String(20), default="", index=True)
    asset_code: Mapped[str] = mapped_column(String(30), default="", index=True)
    display_name: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(20), index=True)
    error_class: Mapped[str | None] = mapped_column(String(50))
    error_message: Mapped[str | None] = mapped_column(Text)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, default=3)
    idempotency_key: Mapped[str] = mapped_column(String(200), unique=True)
    result_json: Mapped[Any | None] = mapped_column(JSON)
    lease_owner: Mapped[str | None] = mapped_column(String(100))
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
