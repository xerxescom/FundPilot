from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AIReport(Base):
    __tablename__ = "ai_report"
    __table_args__ = (
        # 同一批次的日报至多一份；batch_id 为 NULL 的基金报告不受影响（NULL 互不冲突）。
        UniqueConstraint("report_type", "batch_id", name="uq_ai_report_batch_daily"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    report_type: Mapped[str] = mapped_column(String(50), index=True)
    target_code: Mapped[str | None] = mapped_column(String(20), index=True)
    batch_id: Mapped[int | None] = mapped_column(Integer, index=True)
    trade_date: Mapped[date | None] = mapped_column(Date, index=True)
    title: Mapped[str | None] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    model_name: Mapped[str | None] = mapped_column(String(100))
    is_fallback: Mapped[bool] = mapped_column(Boolean, default=False)
    fallback_reason: Mapped[str | None] = mapped_column(Text)
    input_snapshot: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
