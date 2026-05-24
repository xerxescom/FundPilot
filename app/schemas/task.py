from datetime import datetime

from pydantic import BaseModel, ConfigDict


class TaskLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_name: str
    status: str
    duration_ms: int | None = None
    success_count: int | None = None
    failure_count: int | None = None
    message: str | None = None
    created_at: datetime
