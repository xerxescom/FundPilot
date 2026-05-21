from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class FundInfoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fund_code: str
    fund_name: str
    fund_type: str | None = None
    fund_company: str | None = None
    fund_manager: str | None = None
    fund_size: Decimal | None = None
    source: str | None = None


class FundNavOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    fund_code: str
    nav_date: date
    unit_nav: Decimal | None = None
    accumulated_nav: Decimal | None = None
    daily_return: Decimal | None = None
    source: str | None = None
