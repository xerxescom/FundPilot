from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import Date, DateTime, Numeric, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class AssetInfo(Base):
    __tablename__ = "asset_info"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    asset_type: Mapped[str] = mapped_column(String(20), index=True)
    asset_name: Mapped[str] = mapped_column(String(255))
    market: Mapped[str | None] = mapped_column(String(50))
    currency: Mapped[str] = mapped_column(String(10), default="CNY")
    industry: Mapped[str | None] = mapped_column(String(100), index=True)
    source: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class AssetPriceDaily(Base):
    __tablename__ = "asset_price_daily"
    __table_args__ = (UniqueConstraint("asset_code", "price_date", name="uq_asset_price_code_date"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_code: Mapped[str] = mapped_column(String(30), index=True)
    price_date: Mapped[date] = mapped_column(Date, index=True)
    close: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    daily_return: Mapped[Decimal | None] = mapped_column(Numeric(12, 6))
    source: Mapped[str | None] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
