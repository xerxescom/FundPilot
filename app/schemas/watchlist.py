from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WatchlistCreate(BaseModel):
    fund_code: str = Field(min_length=1, max_length=20)
    fund_name: str | None = None
    group_name: str = "default"
    note: str | None = None


class WatchlistOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    fund_code: str
    fund_name: str | None = None
    group_name: str
    note: str | None = None
    is_active: bool
    created_at: datetime
