from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PortfolioCreate(BaseModel):
    fund_code: str | None = None
    asset_code: str | None = None
    asset_type: str = Field(default="fund", pattern="^(fund|stock|etf)$")
    holding_amount: Decimal | None = None
    holding_share: Decimal | None = None
    cost_nav: Decimal | None = None
    buy_date: date | None = None
    note: str | None = None

    @model_validator(mode="after")
    def has_asset_code(self):
        if not self.asset_code and not self.fund_code:
            raise ValueError("asset_code is required")
        return self


class PortfolioTransactionCreate(BaseModel):
    fund_code: str | None = None
    asset_code: str | None = None
    asset_type: str = Field(default="fund", pattern="^(fund|stock|etf)$")
    trade_date: date
    trade_type: str = Field(default="buy", pattern="^(buy|sell|subscription|redemption|opening)$")
    amount: Decimal
    nav: Decimal
    share: Decimal | None = None
    fee: Decimal | None = None
    note: str | None = None

    @model_validator(mode="after")
    def has_asset_code(self):
        if not self.asset_code and not self.fund_code:
            raise ValueError("asset_code is required")
        return self


class PortfolioBuySimulationIn(BaseModel):
    fund_code: str
    amount: Decimal


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
    asset_code: str | None = None
    asset_type: str = "fund"
    holding_amount: Decimal | None = None
    holding_share: Decimal | None = None
    cost_nav: Decimal | None = None
    buy_date: date | None = None
    note: str | None = None


class PortfolioTransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fund_code: str
    asset_code: str | None = None
    asset_type: str = "fund"
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
    latest_price: Decimal | None = None
    price_date: date | None = None
    price_source: str | None = None
    missing_reason: str | None = None
    asset_code: str | None = None
    asset_type: str = "fund"
    asset_name: str | None = None
    current_value: Decimal | None
    profit_amount: Decimal | None
    profit_rate: Decimal | None


class MissingAsset(BaseModel):
    asset_type: str
    asset_code: str
    asset_name: str | None = None
    reason: str


class DrawdownBasis(BaseModel):
    """Basis of the drawdown number: a simulation over current holdings, not account history."""

    basis: str = "current_holdings_simulation"
    label: str = "当前持仓历史模拟"
    window: str
    window_days: int
    aligned_days: int
    included_asset_count: int
    excluded_asset_codes: list[str] = Field(default_factory=list)
    start_date: date | None = None
    end_date: date | None = None


class PortfolioOverview(BaseModel):
    as_of: date
    price_as_of: date | None = None
    valuation_status: Literal["complete", "partial", "empty"]
    is_complete: bool
    known_value: Decimal
    priced_position_count: int
    missing_price_assets: list[MissingAsset] = Field(default_factory=list)
    missing_cost_assets: list[MissingAsset] = Field(default_factory=list)
    total_value: Decimal | None
    total_cost: Decimal | None
    profit_amount: Decimal | None
    profit_rate: Decimal | None
    max_weight: Decimal | None = None
    drawdown_1m: Decimal | None = None
    drawdown_basis: DrawdownBasis | None = None
    positions: list[PortfolioSummary]


class HoldingScreenshotDraft(BaseModel):
    """One editable holding row produced from a broker screenshot."""

    asset_code: str = Field(min_length=1, max_length=30)
    asset_type: str = Field(pattern="^(fund|stock|etf)$")
    asset_name: str | None = Field(default=None, max_length=255)
    holding_share: Decimal = Field(gt=0)
    cost_price: Decimal | None = Field(default=None, gt=0)
    current_price: Decimal | None = Field(default=None, gt=0)
    market_value: Decimal | None = Field(default=None, gt=0)
    confidence: Decimal | None = Field(default=None, ge=0, le=1)


class HoldingScreenshotRecognitionOut(BaseModel):
    provider: str
    model: str
    holdings: list[HoldingScreenshotDraft]
    warning: str


class HoldingScreenshotImportIn(BaseModel):
    holdings: list[HoldingScreenshotDraft] = Field(min_length=1, max_length=100)
    as_of_date: date = Field(default_factory=date.today)


class HoldingScreenshotImportOut(BaseModel):
    created: int
    updated: int
    skipped: list[dict[str, str]]
