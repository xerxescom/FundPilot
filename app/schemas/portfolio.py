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


class PortfolioTransactionCreate(BaseModel):
    fund_code: str
    trade_date: date
    amount: Decimal
    nav: Decimal
    share: Decimal | None = None
    fee: Decimal | None = None
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


class PortfolioTransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fund_code: str
    trade_date: date
    trade_type: str
    amount: Decimal
    nav: Decimal
    share: Decimal
    fee: Decimal | None = None
    note: str | None = None


class PortfolioSummary(BaseModel):
    position: PortfolioOut
    latest_nav: Decimal | None
    current_value: Decimal | None
    profit_amount: Decimal | None
    profit_rate: Decimal | None


class PortfolioOverview(BaseModel):
    total_value: Decimal
    total_cost: Decimal | None
    profit_amount: Decimal | None
    profit_rate: Decimal | None
    max_weight: Decimal | None = None
    drawdown_1m: Decimal | None = None
    positions: list[PortfolioSummary]
