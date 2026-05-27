from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


class ScoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fund_code: str
    score_date: date
    total_score: Decimal | None = None
    return_score: Decimal | None = None
    drawdown_score: Decimal | None = None
    volatility_score: Decimal | None = None
    stability_score: Decimal | None = None
    size_score: Decimal | None = None
    trade_status_score: Decimal | None = None
    rating: str | None = None
    reason: str | None = None
    confidence_score: Decimal | None = None
    confidence_level: str | None = None
    buy_window_signal: str | None = None
    buy_window_reason: str | None = None
    risk_flags: list[str] = Field(default_factory=list)
    risk_flag_labels: list[str] = Field(default_factory=list)
    market_signal: str | None = None
    market_reason: str | None = None
    market_pe_percentile: Decimal | None = None
    peer_group: str | None = None
    peer_group_size: int | None = None
    peer_percentile: Decimal | None = None
    peer_reason: str | None = None
    peer_metric_percentiles: dict[str, Decimal] = Field(default_factory=dict)
    portfolio_fit_score: Decimal | None = None
    portfolio_fit_level: str | None = None
    portfolio_fit_reason: str | None = None
