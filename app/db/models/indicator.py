from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FundIndicator(Base):
    __tablename__ = "fund_indicator"
    __table_args__ = (UniqueConstraint("fund_code", "calc_date", name="uq_indicator_code_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    fund_code: Mapped[str] = mapped_column(String(20), index=True)
    calc_date: Mapped[date] = mapped_column(Date, index=True)
    return_1w: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    return_1m: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    return_3m: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    return_6m: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    return_1y: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    max_drawdown_1y: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    volatility_1y: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    sharpe_1y: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    win_rate_1y: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
