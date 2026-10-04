"""每日更新批次接口（挂在 /api/v1/tasks 之下，旧任务端点保持兼容）。"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.models import TaskBatch, TaskBatchItem
from app.db.session import get_db
from app.schemas.task import BatchDetailOut, BatchOut, BatchRetryIn, BatchRetryOut, DailyBatchOut
from app.services import daily_batch_service as batches

router = APIRouter()


def _effective_status(status: str, lease_expires_at: datetime | None) -> str:
    """进程死亡时租约过期但状态还停在 running —— 对外显示为中断。"""
    if status == batches.BATCH_RUNNING and lease_expires_at and lease_expires_at < datetime.now():
        return batches.BATCH_INTERRUPTED
    if status == batches.ITEM_RUNNING and lease_expires_at and lease_expires_at < datetime.now():
        return batches.ITEM_INTERRUPTED
    return status


def serialize_batch(batch: TaskBatch) -> dict:
    return {
        "id": batch.id,
        "batch_type": batch.batch_type,
        "status": batch.status,
        "effective_status": _effective_status(batch.status, batch.lease_expires_at),
        "trade_date": batch.trade_date,
        "created_at": batch.created_at,
        "started_at": batch.started_at,
        "finished_at": batch.finished_at,
        "heartbeat_at": batch.heartbeat_at,
        "lease_expires_at": batch.lease_expires_at,
        "total_count": batch.total_count,
        "success_count": batch.success_count,
        "failure_count": batch.failure_count,
        "skipped_count": batch.skipped_count,
        "pending_count": batch.pending_count,
        "interrupted_count": batch.interrupted_count,
        "params_json": batch.params_json,
        "coverage_json": batch.coverage_json,
    }


def serialize_item(item: TaskBatchItem) -> dict:
    return {
        "id": item.id,
        "step": item.step,
        "step_label": batches.STEP_LABELS.get(item.step, item.step),
        "asset_type": item.asset_type,
        "asset_code": item.asset_code,
        "display_name": item.display_name,
        "status": item.status,
        "effective_status": _effective_status(item.status, item.lease_expires_at),
        "error_class": item.error_class,
        "error_message": item.error_message,
        "retry_count": item.retry_count,
        "max_retries": item.max_retries,
        "result_json": item.result_json,
        "started_at": item.started_at,
        "finished_at": item.finished_at,
    }


@router.post("/batches/daily", response_model=DailyBatchOut)
def create_daily_batch(db: Session = Depends(get_db)):
    batch, created = batches.create_or_get_daily_batch(db, trigger="api")
    return {"created": created, "batch": serialize_batch(batch)}


@router.get("/batches", response_model=list[BatchOut])
def list_batches(limit: int = Query(default=20, ge=1, le=100), db: Session = Depends(get_db)):
    return [serialize_batch(item) for item in batches.list_batches(db, limit)]


@router.get("/batches/{batch_id}", response_model=BatchDetailOut)
def get_batch(batch_id: int, db: Session = Depends(get_db)):
    batch = db.get(TaskBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    detail = batches.batch_detail(db, batch)
    return {
        "batch": serialize_batch(batch),
        "items": [serialize_item(item) for item in detail["items"]],
    }


@router.post("/batches/{batch_id}/retry", response_model=BatchRetryOut)
def retry_batch(batch_id: int, payload: BatchRetryIn | None = None, db: Session = Depends(get_db)):
    payload = payload or BatchRetryIn()
    batch, retried = batches.retry_batch_items(
        db,
        batch_id,
        step=payload.step,
        asset_type=payload.asset_type,
        asset_code=payload.asset_code,
        include_global=payload.include_global,
    )
    if batch is None:
        raise HTTPException(status_code=404, detail="Batch not found")
    return {"retried": retried, "batch": serialize_batch(batch)}
