"""批次 worker：领取、心跳、中断恢复与执行循环。

领取用条件 UPDATE 实现（SQLite/PostgreSQL 通用），正确性不依赖行锁；
心跳线程每 heartbeat_interval_seconds 续租，租约过期即可判定进程已死。
"""

from __future__ import annotations

import os
import socket
import threading
import uuid
from datetime import datetime, timedelta

from loguru import logger
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.metrics import record_batch_item_outcome
from app.db.models import TaskBatch, TaskBatchItem
from app.db.session import SessionLocal
from app.services import daily_batch_service as batches
from app.services import daily_batch_steps, task_log_service

_BLOCKED_ERROR = {
    "blocked_failed": ("upstream_failed", "上游步骤失败，已跳过"),
    "blocked_pending": ("upstream_pending", "上游数据暂未发布，已跳过"),
    "blocked_skipped": ("upstream_skipped", "上游步骤被跳过，已跳过"),
}


def worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"


def _lease_ttl() -> timedelta:
    return timedelta(seconds=get_settings().lease_ttl_seconds)


def claim_batch(db: Session, batch_id: int, owner: str, now: datetime | None = None) -> bool:
    now = now or datetime.now()
    result = db.execute(
        update(TaskBatch)
        .where(
            TaskBatch.id == batch_id,
            TaskBatch.status.in_([batches.BATCH_QUEUED, batches.BATCH_RUNNING]),
            (TaskBatch.lease_owner.is_(None))
            | (TaskBatch.lease_owner == owner)
            | (TaskBatch.lease_expires_at.is_(None))
            | (TaskBatch.lease_expires_at <= now),
        )
        .values(
            status=batches.BATCH_RUNNING,
            lease_owner=owner,
            lease_expires_at=now + _lease_ttl(),
            heartbeat_at=now,
            started_at=func.coalesce(TaskBatch.started_at, now),
        )
    )
    db.commit()
    return result.rowcount == 1


def claim_item(db: Session, item_id: int, owner: str, now: datetime | None = None) -> bool:
    now = now or datetime.now()
    result = db.execute(
        update(TaskBatchItem)
        .where(TaskBatchItem.id == item_id, TaskBatchItem.status == batches.ITEM_QUEUED)
        .values(
            status=batches.ITEM_RUNNING,
            lease_owner=owner,
            lease_expires_at=now + _lease_ttl(),
            heartbeat_at=now,
            started_at=func.coalesce(TaskBatchItem.started_at, now),
            error_class=None,
            error_message=None,
        )
    )
    db.commit()
    return result.rowcount == 1


def touch_leases(db: Session, owner: str, now: datetime | None = None) -> int:
    now = now or datetime.now()
    expires = now + _lease_ttl()
    batch_result = db.execute(
        update(TaskBatch)
        .where(TaskBatch.lease_owner == owner, TaskBatch.status == batches.BATCH_RUNNING)
        .values(heartbeat_at=now, lease_expires_at=expires)
    )
    item_result = db.execute(
        update(TaskBatchItem)
        .where(TaskBatchItem.lease_owner == owner, TaskBatchItem.status == batches.ITEM_RUNNING)
        .values(heartbeat_at=now, lease_expires_at=expires)
    )
    db.commit()
    return batch_result.rowcount + item_result.rowcount


def _mark_blocked(db: Session, batch: TaskBatch, item: TaskBatchItem, state: str, now: datetime) -> None:
    error_class, message = _BLOCKED_ERROR[state]
    blocked = batches.blocking_dependency(db, batch, item)
    dep_step = blocked[0] if blocked else None
    dep_status = blocked[1].status if blocked else None
    detail = f"（上游 {dep_step}：{dep_status}）" if dep_step else ""
    item.status = batches.ITEM_SKIPPED
    item.error_class = error_class
    item.error_message = message + detail
    item.result_json = {"blocked_by": {"step": dep_step, "status": dep_status}}
    item.finished_at = now
    item.lease_owner = None
    item.lease_expires_at = None
    db.flush()


def next_ready_item(db: Session, batch: TaskBatch, now: datetime | None = None) -> TaskBatchItem | None:
    now = now or datetime.now()
    items = list(
        db.scalars(
            select(TaskBatchItem).where(TaskBatchItem.batch_id == batch.id).order_by(TaskBatchItem.id.asc())
        )
    )
    for step in batches.STEP_ORDER:
        for item in items:
            if item.step != step or item.status != batches.ITEM_QUEUED:
                continue
            state = batches.item_dependency_state(db, batch, item)
            if state == "waiting":
                continue
            if state.startswith("blocked_"):
                _mark_blocked(db, batch, item, state, now)
                db.commit()
                continue
            return item
    return None


def execute_claimed_item(
    db: Session, batch: TaskBatch, item: TaskBatchItem, now: datetime | None = None
) -> None:
    now = now or datetime.now()
    item_id, batch_id = item.id, batch.id
    token = task_log_service.CURRENT_BATCH_ID.set(batch_id)
    try:
        outcome = daily_batch_steps.execute_item(db, item, batch, now)
    except Exception as exc:  # noqa: BLE001 - 未预期异常也必须有明确终态
        logger.exception(f"批次步骤执行异常：{item.step}/{item.asset_code or '全局'}")
        db.rollback()
        item = db.get(TaskBatchItem, item_id)
        batch = db.get(TaskBatch, batch_id)
        outcome = daily_batch_steps.ItemOutcome("failed", None, "unexpected", str(exc)[:500])
    finally:
        task_log_service.CURRENT_BATCH_ID.reset(token)
    item.status = outcome.status
    item.result_json = outcome.result_json
    item.error_class = outcome.error_class
    item.error_message = outcome.error_message
    item.finished_at = now if outcome.status in batches.ITEM_TERMINAL else None
    item.lease_owner = None
    item.lease_expires_at = None
    db.flush()
    batches.refresh_batch_status(db, batch)
    db.commit()
    record_batch_item_outcome(item.step, item.status)


def recover_expired_leases(db: Session, now: datetime | None = None) -> dict[str, int]:
    """把租约过期的运行项标记为中断；启动/轮询都会调用，进程死亡即可被识别。"""
    now = now or datetime.now()
    expired = list(
        db.scalars(
            select(TaskBatchItem).where(
                TaskBatchItem.status == batches.ITEM_RUNNING, TaskBatchItem.lease_expires_at <= now
            )
        )
    )
    touched_batches: set[int] = set()
    for item in expired:
        item.status = batches.ITEM_INTERRUPTED
        item.error_class = "lease_expired"
        item.error_message = "worker 中断，租约已过期，等待恢复"
        item.lease_owner = None
        item.lease_expires_at = None
        item.finished_at = now
        touched_batches.add(item.batch_id)
        record_batch_item_outcome(item.step, "interrupted")
    db.flush()
    for batch_id in touched_batches:
        batch = db.get(TaskBatch, batch_id)
        if batch is not None:
            batches.refresh_batch_status(db, batch)
    db.commit()
    return {"interrupted": len(expired)}


def requeue_interrupted(db: Session, now: datetime | None = None) -> int:
    """中断项在短暂可见期后自动重排；超过重试上限或超出批次恢复窗口则判失败。"""
    now = now or datetime.now()
    settings = get_settings()
    delay = timedelta(seconds=settings.interrupted_requeue_delay_seconds)
    window = timedelta(days=settings.batch_recovery_window_days)
    items = list(
        db.scalars(
            select(TaskBatchItem).where(
                TaskBatchItem.status == batches.ITEM_INTERRUPTED,
                (TaskBatchItem.finished_at.is_(None)) | (TaskBatchItem.finished_at <= now - delay),
            )
        )
    )
    requeued = failures = 0
    touched_batches: set[int] = set()
    for item in items:
        batch = db.get(TaskBatch, item.batch_id)
        in_window = bool(
            batch and batch.trade_date and batch.trade_date >= (now - window).date()
        )
        if item.retry_count < item.max_retries and in_window:
            item.status = batches.ITEM_QUEUED
            item.retry_count += 1
            item.error_class = None
            item.error_message = None
            item.finished_at = None
            requeued += 1
            record_batch_item_outcome(item.step, "requeued")
        else:
            item.status = batches.ITEM_FAILED
            item.error_class = "interrupted_max_retries"
            item.error_message = "中断次数超过上限或批次已超出恢复窗口"
            failures += 1
            record_batch_item_outcome(item.step, "failed")
        touched_batches.add(item.batch_id)
    db.flush()
    for batch_id in touched_batches:
        batch = db.get(TaskBatch, batch_id)
        if batch is not None:
            batches.refresh_batch_status(db, batch)
    db.commit()
    return requeued + failures


def _next_batch(db: Session) -> TaskBatch | None:
    candidates = db.scalars(
        select(TaskBatch)
        .where(TaskBatch.status.in_([batches.BATCH_QUEUED, batches.BATCH_RUNNING]))
        .order_by(TaskBatch.created_at.asc(), TaskBatch.id.asc())
    )
    for batch in candidates:
        active = db.scalar(
            select(func.count())
            .select_from(TaskBatchItem)
            .where(
                TaskBatchItem.batch_id == batch.id,
                TaskBatchItem.status.in_(list(batches.ITEM_ACTIVE)),
            )
        )
        if active:
            return batch
        # 没有活动项但状态未收敛（例如刚被重试清空）：刷新一次并继续找下一个
        batches.refresh_batch_status(db, batch)
        db.commit()
    return None


def run_once(db: Session, owner: str, now: datetime | None = None) -> bool:
    """恢复过期租约并执行一个步骤项；无活可干返回 False。"""
    now = now or datetime.now()
    recover_expired_leases(db, now)
    requeue_interrupted(db, now)
    batch = _next_batch(db)
    if batch is None:
        return False
    if not claim_batch(db, batch.id, owner, now):
        return False
    batch = db.get(TaskBatch, batch.id)
    item = next_ready_item(db, batch, now)
    if item is None:
        batches.refresh_batch_status(db, batch)
        db.commit()
        return False
    if not claim_item(db, item.id, owner, now):
        return False
    item = db.get(TaskBatchItem, item.id)
    execute_claimed_item(db, batch, item, now)
    return True


def _heartbeat_loop(owner: str, stop_event: threading.Event) -> None:
    interval = get_settings().heartbeat_interval_seconds
    while not stop_event.wait(interval):
        try:
            with SessionLocal() as db:
                touch_leases(db, owner)
        except Exception as exc:  # noqa: BLE001 - 心跳失败只记日志，不终止 worker
            logger.warning(f"worker 心跳失败：{exc}")


def run_forever(stop_event: threading.Event, owner: str | None = None) -> None:
    owner = owner or worker_id()
    settings = get_settings()
    logger.info(f"批次 worker 启动：{owner}")
    heartbeat = threading.Thread(target=_heartbeat_loop, args=(owner, stop_event), daemon=True)
    heartbeat.start()
    try:
        with SessionLocal() as db:
            recover_expired_leases(db)
        while not stop_event.is_set():
            did_work = False
            with SessionLocal() as db:
                try:
                    did_work = run_once(db, owner)
                except Exception as exc:  # noqa: BLE001 - 单轮失败不应终止进程
                    db.rollback()
                    logger.exception(f"worker 循环异常：{exc}")
            if not did_work:
                stop_event.wait(settings.worker_poll_seconds)
    finally:
        logger.info(f"批次 worker 退出：{owner}")
