from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TaskRunLog(Base):
    __tablename__ = "task_run_log"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_name: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(30), index=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer)
    success_count: Mapped[int | None] = mapped_column(Integer)
    failure_count: Mapped[int | None] = mapped_column(Integer)
    message: Mapped[str | None] = mapped_column(Text)
    # Full structured per-item result; message stays as the human-readable preview.
    result_json: Mapped[Any | None] = mapped_column(JSON)
    # Links logs produced inside a daily batch to its task_batch row.
    batch_id: Mapped[int | None] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
