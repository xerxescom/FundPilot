from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class IndicatorOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fund_code: str
    calc_date: date
    return_1w: Decimal | None = None
    return_1m: Decimal | None = None
    return_3m: Decimal | None = None
    return_6m: Decimal | None = None
    return_1y: Decimal | None = None
    max_drawdown_1y: Decimal | None = None
    volatility_1y: Decimal | None = None
    sharpe_1y: Decimal | None = None
    win_rate_1y: Decimal | None = None
