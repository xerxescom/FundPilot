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
    is_fallback: bool = False
    fallback_reason: str | None = None
    input_snapshot: str | None = None
    created_at: datetime
