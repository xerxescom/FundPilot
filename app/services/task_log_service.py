from time import perf_counter
from typing import Callable, TypeVar

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import TaskRunLog

T = TypeVar("T")


def _is_failed_result(value: object) -> bool:
    if isinstance(value, str):
        return value.startswith("failed:")
    if isinstance(value, dict):
        return value.get("status") == "failed"
    return False


def record_task_log(
    db: Session,
    task_name: str,
    status: str,
    duration_ms: int | None = None,
    success_count: int | None = None,
    failure_count: int | None = None,
    message: str | None = None,
) -> TaskRunLog:
    log = TaskRunLog(
        task_name=task_name,
        status=status,
        duration_ms=duration_ms,
        success_count=success_count,
        failure_count=failure_count,
        message=message,
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def run_logged(db: Session, task_name: str, fn: Callable[[], T]) -> T:
    started = perf_counter()
    try:
        result = fn()
    except Exception as exc:
        record_task_log(
            db,
            task_name=task_name,
            status="failed",
            duration_ms=int((perf_counter() - started) * 1000),
            message=str(exc),
        )
        raise

    success_count = len(result) if isinstance(result, (list, dict)) else None
    failure_count = sum(1 for value in result.values() if _is_failed_result(value)) if isinstance(result, dict) else 0
    record_task_log(
        db,
        task_name=task_name,
        status="success",
        duration_ms=int((perf_counter() - started) * 1000),
        success_count=success_count,
        failure_count=failure_count,
        message=str(result)[:2000],
    )
    return result


def latest_task_logs(db: Session, limit: int = 20) -> list[TaskRunLog]:
    return list(db.scalars(select(TaskRunLog).order_by(TaskRunLog.created_at.desc()).limit(limit)))
