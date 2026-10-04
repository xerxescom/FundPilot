from datetime import date, datetime, timedelta

from sqlalchemy import select

from app.db.models import TaskBatchItem, Watchlist
from app.services import batch_worker_service as worker
from app.services import daily_batch_service as batches
from app.services import daily_batch_steps as steps

TRADE_DATE = date(2026, 10, 9)
NOW = datetime(2026, 10, 9, 18, 0)


def _make_batch(db_session, *funds: str):
    for code in funds or ("000001",):
        db_session.add(Watchlist(fund_code=code, fund_name=f"基金{code}", is_active=True))
    db_session.commit()
    batch, _ = batches.create_or_get_daily_batch(db_session, trade_date=TRADE_DATE, now=NOW)
    return batch


def _item(db_session, batch, step: str, asset_type: str, asset_code: str) -> TaskBatchItem:
    return db_session.scalar(
        select(TaskBatchItem).where(
            TaskBatchItem.batch_id == batch.id,
            TaskBatchItem.step == step,
            TaskBatchItem.asset_type == asset_type,
            TaskBatchItem.asset_code == asset_code,
        )
    )


def _drain(db_session, owner: str = "test-worker", now: datetime = NOW, max_steps: int = 60) -> int:
    executed = 0
    for _ in range(max_steps):
        if not worker.run_once(db_session, owner, now):
            break
        executed += 1
    return executed


def test_claim_item_is_exclusive(db_session):
    batch = _make_batch(db_session)
    item = _item(db_session, batch, "market", "", "")

    assert worker.claim_item(db_session, item.id, "worker-a", NOW) is True
    assert worker.claim_item(db_session, item.id, "worker-b", NOW) is False
    refreshed = db_session.get(TaskBatchItem, item.id)
    assert refreshed.status == "running"
    assert refreshed.lease_owner == "worker-a"


def test_touch_leases_extends_item_and_batch(db_session):
    batch = _make_batch(db_session)
    item = _item(db_session, batch, "market", "", "")
    worker.claim_batch(db_session, batch.id, "worker-a", NOW)
    worker.claim_item(db_session, item.id, "worker-a", NOW)

    touched = worker.touch_leases(db_session, "worker-a", NOW + timedelta(seconds=15))

    assert touched == 2
    refreshed_item = db_session.get(TaskBatchItem, item.id)
    assert refreshed_item.heartbeat_at == NOW + timedelta(seconds=15)
    assert refreshed_item.lease_expires_at > NOW + timedelta(seconds=100)


def test_recover_expired_lease_then_requeue_after_delay(db_session):
    batch = _make_batch(db_session)
    item = _item(db_session, batch, "sync_nav", "fund", "000001")
    # 除目标项外全部完成，模拟 worker 死亡时只剩一个在途步骤
    for other in db_session.scalars(select(TaskBatchItem).where(TaskBatchItem.batch_id == batch.id)):
        if other.id != item.id:
            other.status = "success"
    item.status = "running"
    item.lease_owner = "dead-worker"
    item.lease_expires_at = NOW - timedelta(seconds=10)
    db_session.commit()

    recovered = worker.recover_expired_leases(db_session, NOW)

    assert recovered == {"interrupted": 1}
    assert db_session.get(TaskBatchItem, item.id).status == "interrupted"
    assert db_session.get(TaskBatchItem, item.id).error_class == "lease_expired"
    assert batch.status == "interrupted"  # 没有其他活动项时批次显示中断

    # 延迟期内保持中断可见
    assert worker.requeue_interrupted(db_session, NOW + timedelta(seconds=5)) == 0
    assert db_session.get(TaskBatchItem, item.id).status == "interrupted"

    # 超过可见期后自动重排
    assert worker.requeue_interrupted(db_session, NOW + timedelta(seconds=60)) == 1
    requeued = db_session.get(TaskBatchItem, item.id)
    assert requeued.status == "queued"
    assert requeued.retry_count == 1


def test_interrupted_item_fails_when_retries_exhausted(db_session):
    batch = _make_batch(db_session)
    item = _item(db_session, batch, "sync_nav", "fund", "000001")
    item.status = "interrupted"
    item.retry_count = item.max_retries
    item.error_class = "lease_expired"
    item.finished_at = NOW - timedelta(minutes=5)
    db_session.commit()

    assert worker.requeue_interrupted(db_session, NOW) == 1
    failed = db_session.get(TaskBatchItem, item.id)
    assert failed.status == "failed"
    assert failed.error_class == "interrupted_max_retries"


def test_run_once_executes_steps_in_dependency_order(db_session, monkeypatch):
    batch = _make_batch(db_session)
    calls: list[tuple[str, str]] = []

    def _fake_execute(db, item, batch, now=None):
        calls.append((item.step, item.asset_code))
        return steps.ItemOutcome("success", {"ok": True})

    monkeypatch.setattr(steps, "execute_item", _fake_execute)

    executed = _drain(db_session)

    assert executed == len(batches.STEP_ORDER)
    assert [step for step, _ in calls] == list(batches.STEP_ORDER)
    refreshed = db_session.get(type(batch), batch.id)
    assert refreshed.status == "success"
    assert refreshed.finished_at is not None


def test_failed_sync_blocks_only_its_own_downstream(db_session, monkeypatch):
    batch = _make_batch(db_session, "000001", "000002")

    def _fake_execute(db, item, batch, now=None):
        if item.step == "sync_nav" and item.asset_code == "000001":
            return steps.ItemOutcome("failed", {"error": "boom"}, "source_error", "数据源失败")
        return steps.ItemOutcome("success", {"ok": True})

    monkeypatch.setattr(steps, "execute_item", _fake_execute)

    _drain(db_session)

    assert _item(db_session, batch, "sync_nav", "fund", "000001").status == "failed"
    blocked = _item(db_session, batch, "quality_check", "fund", "000001")
    assert blocked.status == "skipped"
    assert blocked.error_class == "upstream_failed"
    assert blocked.result_json["blocked_by"]["step"] == "sync_nav"
    assert _item(db_session, batch, "calc_indicators", "fund", "000001").status == "skipped"
    assert _item(db_session, batch, "calc_scores", "fund", "000001").status == "skipped"

    # 其他资产不受影响
    assert _item(db_session, batch, "sync_nav", "fund", "000002").status == "success"
    assert _item(db_session, batch, "calc_scores", "fund", "000002").status == "success"
    # 全局步骤照常完成，报告在预警之后
    assert _item(db_session, batch, "alerts", "", "").status == "success"
    assert _item(db_session, batch, "report", "", "").status == "success"
    assert batch.status == "partial_success"


def test_run_once_returns_false_when_idle(db_session):
    assert worker.run_once(db_session, "idle-worker", NOW) is False


def test_step_logs_carry_batch_id_via_context(db_session, monkeypatch):
    from app.services import task_log_service

    batch = _make_batch(db_session)

    def _fake_execute(db, item, batch_obj, now=None):
        # 模拟步骤内部调用 run_logged（如 market_service 的做法）
        task_log_service.run_logged(db, "sync_market_context", lambda: {"000300": 1})
        return steps.ItemOutcome("success", {"ok": True})

    monkeypatch.setattr(steps, "execute_item", _fake_execute)
    worker.run_once(db_session, "log-worker", NOW)

    logs = task_log_service.latest_task_logs(db_session)
    assert logs[0].batch_id == batch.id
