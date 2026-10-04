from datetime import date, datetime
from typing import Any

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
    batch_id: int | None = None
    created_at: datetime


class BatchOut(BaseModel):
    id: int
    batch_type: str
    status: str
    effective_status: str
    trade_date: date | None = None
    created_at: datetime | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None
    heartbeat_at: datetime | None = None
    lease_expires_at: datetime | None = None
    total_count: int
    success_count: int
    failure_count: int
    skipped_count: int
    pending_count: int
    interrupted_count: int
    params_json: Any | None = None
    coverage_json: Any | None = None


class BatchItemOut(BaseModel):
    id: int
    step: str
    step_label: str
    asset_type: str
    asset_code: str
    display_name: str | None = None
    status: str
    effective_status: str
    error_class: str | None = None
    error_message: str | None = None
    retry_count: int
    max_retries: int
    result_json: Any | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None


class DailyBatchOut(BaseModel):
    created: bool
    batch: BatchOut


class BatchDetailOut(BaseModel):
    batch: BatchOut
    items: list[BatchItemOut]


class BatchRetryIn(BaseModel):
    step: str | None = None
    asset_type: str | None = None
    asset_code: str | None = None
    include_global: bool = False


class BatchRetryOut(BaseModel):
    retried: int
    batch: BatchOut
