from datetime import date
from decimal import Decimal

from sqlalchemy import select

from app.db.models import PortfolioPosition, TaskBatchItem, Watchlist
from app.services import daily_batch_service as batches


def _seed_watchlist(db_session, *codes: str) -> None:
    for code in codes:
        db_session.add(Watchlist(fund_code=code, fund_name=f"基金{code}", is_active=True))
    db_session.commit()


def _item(db_session, batch, step: str, asset_type: str, asset_code: str) -> TaskBatchItem:
    return db_session.scalar(
        select(TaskBatchItem).where(
            TaskBatchItem.batch_id == batch.id,
            TaskBatchItem.step == step,
            TaskBatchItem.asset_type == asset_type,
            TaskBatchItem.asset_code == asset_code,
        )
    )


def _set_status(db_session, batch, step: str, status: str, asset_type: str = "", asset_code: str = "") -> None:
    item = _item(db_session, batch, step, asset_type, asset_code)
    item.status = status
    db_session.commit()


def test_create_or_get_daily_batch_is_idempotent(db_session):
    _seed_watchlist(db_session, "000001")

    first, created_first = batches.create_or_get_daily_batch(db_session, trade_date=date(2026, 10, 9))
    second, created_second = batches.create_or_get_daily_batch(db_session, trade_date=date(2026, 10, 9))

    assert created_first is True
    assert created_second is False
    assert first.id == second.id
    items = list(db_session.scalars(select(TaskBatchItem).where(TaskBatchItem.batch_id == first.id)))
    assert len(items) == len(set(item.idempotency_key for item in items))
    assert first.total_count == len(items)
    assert first.params_json["universe"] == {"funds": 1, "stocks": 0, "etfs": 0}


def test_universe_expansion_dedupes_and_includes_listed(db_session):
    _seed_watchlist(db_session, "000001")
    db_session.add_all(
        [
            # 与自选重复的持仓基金，且 asset_code 为空（旧数据形态，回落到 fund_code）
            PortfolioPosition(fund_code="000001", holding_share=Decimal("100"), holding_amount=Decimal("100")),
            PortfolioPosition(
                fund_code="600519", asset_type="stock", asset_code="600519",
                holding_share=Decimal("10"), holding_amount=Decimal("1000"),
            ),
            PortfolioPosition(
                fund_code="510300", asset_type="etf", asset_code="510300",
                holding_share=Decimal("100"), holding_amount=Decimal("300"),
            ),
        ]
    )
    db_session.commit()

    batch, _ = batches.create_or_get_daily_batch(db_session, trade_date=date(2026, 10, 9))

    # 基金 4 步 + 股票 2 步 + ETF 2 步 + 全局 3 步
    assert batch.total_count == 11
    assert _item(db_session, batch, "calc_scores", "fund", "000001") is not None
    assert _item(db_session, batch, "sync_nav", "stock", "600519") is not None
    assert _item(db_session, batch, "calc_indicators", "stock", "600519") is None
    assert _item(db_session, batch, "sync_nav", "etf", "510300") is not None
    assert _item(db_session, batch, "report", "", "") is not None


def test_derive_batch_status_matrix():
    assert batches.derive_batch_status(["success", "pending"]) == "success"
    assert batches.derive_batch_status(["pending", "pending"]) == "success"
    assert batches.derive_batch_status(["failed", "success"]) == "partial_success"
    assert batches.derive_batch_status(["failed", "skipped", "pending"]) == "partial_success"
    assert batches.derive_batch_status(["failed", "failed"]) == "failed"
    assert batches.derive_batch_status(["interrupted", "failed"]) == "interrupted"
    assert batches.derive_batch_status(["running", "failed"]) == "running"
    assert batches.derive_batch_status(["queued", "success"]) == "queued"


def test_dependency_states_isolate_failed_asset(db_session):
    _seed_watchlist(db_session, "000001", "000002")
    batch, _ = batches.create_or_get_daily_batch(db_session, trade_date=date(2026, 10, 9))

    _set_status(db_session, batch, "market", "success")
    _set_status(db_session, batch, "sync_nav", "failed", "fund", "000001")
    _set_status(db_session, batch, "sync_nav", "pending", "fund", "000002")

    assert batches.item_dependency_state(db_session, batch, _item(db_session, batch, "quality_check", "fund", "000001")) == "blocked_failed"
    assert batches.item_dependency_state(db_session, batch, _item(db_session, batch, "quality_check", "fund", "000002")) == "blocked_pending"

    _set_status(db_session, batch, "sync_nav", "success", "fund", "000002")
    assert batches.item_dependency_state(db_session, batch, _item(db_session, batch, "quality_check", "fund", "000002")) == "ready"
    # 上游未终态时等待
    _set_status(db_session, batch, "sync_nav", "queued", "fund", "000002")
    assert batches.item_dependency_state(db_session, batch, _item(db_session, batch, "quality_check", "fund", "000002")) == "waiting"


def test_alerts_and_report_dependencies(db_session):
    _seed_watchlist(db_session, "000001")
    batch, _ = batches.create_or_get_daily_batch(db_session, trade_date=date(2026, 10, 9))

    alerts_item = _item(db_session, batch, "alerts", "", "")
    report_item = _item(db_session, batch, "report", "", "")

    # 任一资产项未终结 → alerts 等待
    assert batches.item_dependency_state(db_session, batch, alerts_item) == "waiting"
    for step in batches.FUND_STEPS:
        _set_status(db_session, batch, step, "success", "fund", "000001")
    _set_status(db_session, batch, "market", "success")
    assert batches.item_dependency_state(db_session, batch, alerts_item) == "ready"

    # report 必须等 alerts 终结（软依赖：即使 alerts 失败也继续）
    assert batches.item_dependency_state(db_session, batch, report_item) == "waiting"
    _set_status(db_session, batch, "alerts", "failed")
    assert batches.item_dependency_state(db_session, batch, report_item) == "ready"


def test_retry_rearms_failed_item_and_blocked_downstream(db_session):
    _seed_watchlist(db_session, "000001", "000002")
    batch, _ = batches.create_or_get_daily_batch(db_session, trade_date=date(2026, 10, 9))

    _set_status(db_session, batch, "market", "success")
    failed = _item(db_session, batch, "sync_nav", "fund", "000001")
    failed.status = "failed"
    failed.error_class = "source_error"
    failed.retry_count = 1
    blocked = _item(db_session, batch, "quality_check", "fund", "000001")
    blocked.status = "skipped"
    blocked.result_json = {"blocked_by": {"step": "sync_nav", "status": "failed"}}
    other = _item(db_session, batch, "sync_nav", "fund", "000002")
    other.status = "success"
    alerts = _item(db_session, batch, "alerts", "", "")
    alerts.status = "success"
    db_session.commit()

    _, count = batches.retry_batch_items(db_session, batch.id, asset_code="000001")

    assert count == 2
    assert failed.status == "queued"
    assert failed.retry_count == 2
    assert failed.error_class is None
    assert blocked.status == "queued"
    assert other.status == "success"  # 其他资产不受影响
    assert alerts.status == "success"  # 全局项默认不动


def test_repeat_click_rearms_pending_only_after_terminal(db_session):
    _seed_watchlist(db_session, "000001")
    batch, _ = batches.create_or_get_daily_batch(db_session, trade_date=date(2026, 10, 9))

    # 未终结：重复点击只返回状态，不重置
    running = _item(db_session, batch, "sync_nav", "fund", "000001")
    running.status = "running"
    db_session.commit()
    batches.create_or_get_daily_batch(db_session, trade_date=date(2026, 10, 9))
    assert _item(db_session, batch, "sync_nav", "fund", "000001").status == "running"

    # 终态且有 pending：重新排队，且不计入重试次数
    running.status = "pending"
    for item in db_session.scalars(select(TaskBatchItem).where(TaskBatchItem.batch_id == batch.id)):
        if item.status == "queued":
            item.status = "success"
    db_session.commit()
    batches.refresh_batch_status(db_session, batch)
    db_session.commit()
    assert batch.status == "success"
    assert batch.pending_count == 1

    batches.create_or_get_daily_batch(db_session, trade_date=date(2026, 10, 9))
    pending = _item(db_session, batch, "sync_nav", "fund", "000001")
    assert pending.status == "queued"
    assert pending.retry_count == 0


def test_coverage_notes_summarize_pending_and_failed(db_session):
    _seed_watchlist(db_session, "000001", "000002")
    batch, _ = batches.create_or_get_daily_batch(db_session, trade_date=date(2026, 10, 9))

    _set_status(db_session, batch, "sync_nav", "pending", "fund", "000001")
    _set_status(db_session, batch, "sync_nav", "failed", "fund", "000002")
    for item in db_session.scalars(select(TaskBatchItem).where(TaskBatchItem.batch_id == batch.id)):
        if item.status == "queued":
            item.status = "success"
    db_session.commit()
    batches.refresh_batch_status(db_session, batch)
    db_session.commit()

    coverage = batch.coverage_json
    assert coverage["asset_counts"] == {"total": 2, "success": 0, "pending": 1, "failed": 1}
    assert any("暂未发布" in note for note in coverage["notes"])
    assert any("同步失败" in note for note in coverage["notes"])
    assert batch.status == "partial_success"
