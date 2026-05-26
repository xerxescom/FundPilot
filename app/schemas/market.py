from datetime import date

from pydantic import BaseModel


class MarketContextOut(BaseModel):
    index_code: str
    index_name: str
    trade_date: date | None = None
    close: float | None = None
    daily_return: float | None = None
    return_1m: float | None = None
    pe_ttm: float | None = None
    pe_percentile: float | None = None
    valuation_date: date | None = None
    source: str | None = None
