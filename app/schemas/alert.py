from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    alert_type: str
    fund_code: str | None = None
    fund_name: str | None = None
    alert_level: str | None = None
    title: str | None = None
    content: str | None = None
    status: str = "unread"
    is_read: bool
    created_at: datetime


class AlertUpdate(BaseModel):
    status: str

