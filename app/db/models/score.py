from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FundScore(Base):
    __tablename__ = "fund_score"
    __table_args__ = (UniqueConstraint("fund_code", "score_date", name="uq_score_code_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    fund_code: Mapped[str] = mapped_column(String(20), index=True)
    score_date: Mapped[date] = mapped_column(Date, index=True)
    total_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    return_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    drawdown_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    volatility_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    stability_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    size_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    trade_status_score: Mapped[Decimal | None] = mapped_column(Numeric(8, 2))
    rating: Mapped[str | None] = mapped_column(String(50))
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
