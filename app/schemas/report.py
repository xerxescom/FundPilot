from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ReportOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    report_type: str
    target_code: str | None = None
    title: str | None = None
    content: str
    model_name: str | None = None
    created_at: datetime
