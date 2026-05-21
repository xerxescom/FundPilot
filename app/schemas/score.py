from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


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
