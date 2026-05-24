from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PortfolioPosition(Base):
    __tablename__ = "portfolio_position"

    id: Mapped[int] = mapped_column(primary_key=True)
    fund_code: Mapped[str] = mapped_column(String(20), index=True)
    holding_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    holding_share: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    cost_nav: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    buy_date: Mapped[date | None] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class PortfolioTransaction(Base):
    __tablename__ = "portfolio_transaction"

    id: Mapped[int] = mapped_column(primary_key=True)
    fund_code: Mapped[str] = mapped_column(String(20), index=True)
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    trade_type: Mapped[str] = mapped_column(String(20), default="buy")
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    nav: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    share: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    fee: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
