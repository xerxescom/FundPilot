from datetime import date, datetime, timedelta

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.api.v1.batch import create_daily_batch, get_batch, list_batches, retry_batch
from app.db.models import TaskBatchItem, Watchlist
from app.schemas.task import BatchRetryIn
from app.services import daily_batch_service as batches
from app.services import trading_calendar_service

TRADE_DATE = date(2026, 10, 9)


@pytest.fixture
def fixed_trade_date(monkeypatch):
    monkeypatch.setattr(
        trading_calendar_service, "latest_expected_trade_date", lambda db, now=None: TRADE_DATE
    )


def _seed_watchlist(db_session, *codes: str) -> None:
    for code in codes:
        db_session.add(Watchlist(fund_code=code, fund_name=f"基金{code}", is_active=True))
    db_session.commit()


def _item(db_session, batch_id: int, step: str, asset_type: str, asset_code: str) -> TaskBatchItem:
    return db_session.scalar(
        select(TaskBatchItem).where(
            TaskBatchItem.batch_id == batch_id,
            TaskBatchItem.step == step,
            TaskBatchItem.asset_type == asset_type,
            TaskBatchItem.asset_code == asset_code,
        )
    )


def test_create_daily_batch_endpoint_is_idempotent(fixed_trade_date, db_session):
    _seed_watchlist(db_session, "000001")

    first = create_daily_batch(db_session)
    second = create_daily_batch(db_session)

    assert first["created"] is True
    assert second["created"] is False
    assert first["batch"]["id"] == second["batch"]["id"]
    assert first["batch"]["status"] == "queued"
    assert first["batch"]["effective_status"] == "queued"
    assert first["batch"]["trade_date"] == TRADE_DATE
    assert first["batch"]["total_count"] == 7  # 基金 4 步 + 全局 3 步


def test_batch_detail_lists_items_with_labels(fixed_trade_date, db_session):
    _seed_watchlist(db_session, "000001")
    created = create_daily_batch(db_session)

    detail = get_batch(created["batch"]["id"], db_session)

    assert len(detail["items"]) == detail["batch"]["total_count"]
    labels = {item["step"]: item["step_label"] for item in detail["items"]}
    assert labels["market"] == "行情及市场背景"
    assert labels["report"] == "生成报告"
    assert all(item["status"] == "queued" for item in detail["items"])
    assert all(item["effective_status"] == "queued" for item in detail["items"])


def test_retry_endpoint_filters_and_rearms_downstream(fixed_trade_date, db_session):
    _seed_watchlist(db_session, "000001", "000002")
    created = create_daily_batch(db_session)
    batch_id = created["batch"]["id"]

    failed = _item(db_session, batch_id, "sync_nav", "fund", "000001")
    failed.status = "failed"
    failed.error_class = "source_error"
    blocked = _item(db_session, batch_id, "quality_check", "fund", "000001")
    blocked.status = "skipped"
    blocked.result_json = {"blocked_by": {"step": "sync_nav", "status": "failed"}}
    other = _item(db_session, batch_id, "sync_nav", "fund", "000002")
    other.status = "success"
    db_session.commit()

    result = retry_batch(batch_id, BatchRetryIn(asset_code="000001"), db_session)

    assert result["retried"] == 2
    assert _item(db_session, batch_id, "sync_nav", "fund", "000001").status == "queued"
    assert _item(db_session, batch_id, "quality_check", "fund", "000001").status == "queued"
    assert _item(db_session, batch_id, "sync_nav", "fund", "000002").status == "success"


def test_expired_lease_reports_interrupted(fixed_trade_date, db_session):
    _seed_watchlist(db_session, "000001")
    created = create_daily_batch(db_session)
    batch_id = created["batch"]["id"]

    from app.db.models import TaskBatch

    batch = db_session.get(TaskBatch, batch_id)
    batch.status = "running"
    batch.lease_owner = "dead-worker"
    batch.lease_expires_at = datetime.now() - timedelta(seconds=10)
    item = _item(db_session, batch_id, "market", "", "")
    item.status = "running"
    item.lease_expires_at = datetime.now() - timedelta(seconds=10)
    db_session.commit()

    detail = get_batch(batch_id, db_session)

    assert detail["batch"]["effective_status"] == "interrupted"
    assert next(item for item in detail["items"] if item["step"] == "market")["effective_status"] == "interrupted"


def test_list_batches_returns_recent_first(fixed_trade_date, db_session):
    _seed_watchlist(db_session, "000001")
    create_daily_batch(db_session)

    listed = list_batches(5, db_session)

    assert len(listed) == 1
    assert listed[0]["trade_date"] == TRADE_DATE


def test_missing_batch_returns_404(fixed_trade_date, db_session):
    with pytest.raises(HTTPException) as excinfo:
        get_batch(99999, db_session)
    assert excinfo.value.status_code == 404

    with pytest.raises(HTTPException) as excinfo:
        retry_batch(99999, None, db_session)
    assert excinfo.value.status_code == 404


def test_legacy_task_endpoints_still_work(db_session, monkeypatch):
    """旧端点（日志/可用任务/前台运行）保持兼容。"""
    from app.api.v1 import task as task_api
    from app.services import task_runner_service

    assert task_api.list_tasks()[0]["task_name"] == "sync_watchlist_nav"
    assert task_api.task_logs(10, db_session) == []

    monkeypatch.setattr(task_runner_service, "_task_factories", lambda db: {"demo": lambda: {"ok": True}})
    assert task_api.run_named_task("demo", db_session) == {"ok": True}
    assert batches.list_batches(db_session, 5) == []
