from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class PortfolioCreate(BaseModel):
    fund_code: str
    holding_amount: Decimal | None = None
    holding_share: Decimal | None = None
    cost_nav: Decimal | None = None
    buy_date: date | None = None
    note: str | None = None


class PortfolioUpdate(BaseModel):
    holding_amount: Decimal | None = None
    holding_share: Decimal | None = None
    cost_nav: Decimal | None = None
    buy_date: date | None = None
    note: str | None = None


class PortfolioOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fund_code: str
    holding_amount: Decimal | None = None
    holding_share: Decimal | None = None
    cost_nav: Decimal | None = None
    buy_date: date | None = None
    note: str | None = None


class PortfolioSummary(BaseModel):
    position: PortfolioOut
    latest_nav: Decimal | None
    current_value: Decimal | None
    profit_amount: Decimal | None
    profit_rate: Decimal | None
