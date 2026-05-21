from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class FundInfo(Base):
    __tablename__ = "fund_info"

    id: Mapped[int] = mapped_column(primary_key=True)
    fund_code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    fund_name: Mapped[str] = mapped_column(String(255))
    fund_type: Mapped[str | None] = mapped_column(String(100))
    fund_company: Mapped[str | None] = mapped_column(String(255))
    fund_manager: Mapped[str | None] = mapped_column(String(255))
    establish_date: Mapped[date | None] = mapped_column(Date)
    fund_size: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    risk_level: Mapped[str | None] = mapped_column(String(50))
    tracking_index: Mapped[str | None] = mapped_column(String(255))
    buy_status: Mapped[str | None] = mapped_column(String(50))
    sell_status: Mapped[str | None] = mapped_column(String(50))
    source: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class FundNav(Base):
    __tablename__ = "fund_nav"
    __table_args__ = (UniqueConstraint("fund_code", "nav_date", name="uq_fund_nav_code_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    fund_code: Mapped[str] = mapped_column(String(20), index=True)
    nav_date: Mapped[date] = mapped_column(Date, index=True)
    unit_nav: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    accumulated_nav: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    daily_return: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    source: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
