import contextvars
import json
from time import perf_counter
from typing import Any, Callable, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.metrics import record_task_run
from app.db.models import TaskRunLog

T = TypeVar("T")

# worker 在执行步骤期间设置，步骤内部产生的任务日志自动关联到该批次
CURRENT_BATCH_ID: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "current_batch_id", default=None
)

STATUS_SUCCESS = "success"
STATUS_PARTIAL_SUCCESS = "partial_success"
STATUS_FAILED = "failed"

_FAILED_STRINGS = {"failed", "error"}


def summarize_result(result: object) -> tuple[int | None, int, int]:
    """Count per-item success / failure / skipped for a task result payload."""
    if isinstance(result, (list, tuple)):
        return len(result), 0, 0
    if not isinstance(result, dict):
        return None, 0, 0
    success = failure = skipped = 0
    for value in result.values():
        if isinstance(value, dict):
            status = value.get("status")
            if status == "skipped":
                skipped += 1
            elif status is None or status in {"success", "ok"}:
                success += 1
            else:
                failure += 1
        elif isinstance(value, str):
            if value.startswith("failed:") or value in _FAILED_STRINGS:
                failure += 1
            elif value == "skipped":
                skipped += 1
            else:
                success += 1
        else:
            success += 1
    return success, failure, skipped


def derive_task_status(success_count: int | None, failure_count: int, skipped_count: int = 0) -> str:
    if failure_count and (success_count or skipped_count):
        return STATUS_PARTIAL_SUCCESS
    if failure_count:
        return STATUS_FAILED
    return STATUS_SUCCESS


def serialize_result_payload(result: object) -> Any | None:
    """Normalize a task result into a JSON-safe payload for structured storage."""
    if result is None:
        return None
    try:
        return json.loads(json.dumps(result, ensure_ascii=False, default=str))
    except (TypeError, ValueError):
        return {"repr": str(result)[:2000]}


def record_task_log(
    db: Session,
    task_name: str,
    status: str,
    duration_ms: int | None = None,
    success_count: int | None = None,
    failure_count: int | None = None,
    message: str | None = None,
    result_json: Any | None = None,
    batch_id: int | None = None,
) -> TaskRunLog:
    log = TaskRunLog(
        task_name=task_name,
        status=status,
        duration_ms=duration_ms,
        success_count=success_count,
        failure_count=failure_count,
        message=message,
        result_json=result_json,
        batch_id=batch_id if batch_id is not None else CURRENT_BATCH_ID.get(),
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    record_task_run(task_name, status)
    return log


def update_task_log(
    db: Session,
    log_id: int,
    status: str,
    duration_ms: int | None = None,
    success_count: int | None = None,
    failure_count: int | None = None,
    message: str | None = None,
    result_json: Any | None = None,
) -> TaskRunLog:
    log = db.get(TaskRunLog, log_id)
    if not log:
        raise ValueError(f"Task log not found: {log_id}")
    log.status = status
    log.duration_ms = duration_ms
    log.success_count = success_count
    log.failure_count = failure_count
    log.message = message
    log.result_json = result_json
    db.commit()
    db.refresh(log)
    record_task_run(log.task_name, status)
    return log


def run_logged(db: Session, task_name: str, fn: Callable[[], T]) -> T:
    started = perf_counter()
    try:
        result = fn()
    except Exception as exc:
        record_task_log(
            db,
            task_name=task_name,
            status=STATUS_FAILED,
            duration_ms=int((perf_counter() - started) * 1000),
            message=str(exc),
            result_json={"error": str(exc)},
        )
        raise

    success_count, failure_count, skipped_count = summarize_result(result)
    record_task_log(
        db,
        task_name=task_name,
        status=derive_task_status(success_count, failure_count, skipped_count),
        duration_ms=int((perf_counter() - started) * 1000),
        success_count=success_count,
        failure_count=failure_count,
        message=str(result)[:2000],
        result_json=serialize_result_payload(result),
    )
    return result


def latest_task_logs(db: Session, limit: int = 20) -> list[TaskRunLog]:
    return list(db.scalars(select(TaskRunLog).order_by(TaskRunLog.created_at.desc()).limit(limit)))
