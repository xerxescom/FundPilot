from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class MarketIndexDaily(Base):
    __tablename__ = "market_index_daily"
    __table_args__ = (UniqueConstraint("index_code", "trade_date", name="uq_market_index_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    index_code: Mapped[str] = mapped_column(String(30), index=True)
    index_name: Mapped[str] = mapped_column(String(100))
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    close: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    daily_return: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    source: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
