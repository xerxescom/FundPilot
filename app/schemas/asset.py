from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class AssetOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    asset_code: str
    asset_type: str
    asset_name: str
    market: str | None = None
    currency: str
    industry: str | None = None
    source: str | None = None


class AssetPriceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    asset_code: str
    price_date: date
    close: Decimal | None = None
    daily_return: Decimal | None = None
    source: str | None = None


class AssetSyncOut(BaseModel):
    asset: AssetOut
    synced_rows: int
    latest_price_date: date | None = None


class ListedAssetSyncIn(BaseModel):
    asset_type: str = Field(default="stock", pattern="^(stock|etf)$")
