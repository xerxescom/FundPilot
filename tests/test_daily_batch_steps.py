from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.db.models import AIReport, AssetPriceDaily, FundNav, TaskBatchItem, TradeCalendar, Watchlist
from app.services import (
    alert_service,
    asset_service,
    daily_batch_service as batches,
    daily_batch_steps as steps,
    indicator_service,
    market_service,
    nav_service,
    score_service,
)
from app.services.ai import report_service

TRADE_DATE = date(2026, 10, 9)


def _seed_calendar(db_session) -> None:
    cursor = date(2026, 9, 28)
    while cursor <= date(2026, 10, 12):
        if cursor.weekday() < 5:
            db_session.add(TradeCalendar(trade_date=cursor, is_open=True, source="akshare"))
        cursor += timedelta(days=1)
    db_session.commit()


def _make_batch(db_session, code: str = "000001"):
    db_session.add(Watchlist(fund_code=code, fund_name=f"基金{code}", is_active=True))
    db_session.commit()
    batch, _ = batches.create_or_get_daily_batch(db_session, trade_date=TRADE_DATE)
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


class _FakeAlert:
    def __init__(self, title: str):
        self.title = title


def test_market_handler_success_and_total_failure(db_session, monkeypatch):
    batch = _make_batch(db_session)
    item = _item(db_session, batch, "market", "", "")

    monkeypatch.setattr(
        market_service, "sync_market_context", lambda db: {"000300": 5, "000905": "failed: 超时"}
    )
    outcome = steps.execute_item(db_session, item, batch)
    assert outcome.status == "success"
    assert outcome.result_json == {"synced_indexes": 1, "failed_indexes": 1}

    monkeypatch.setattr(market_service, "sync_market_context", lambda db: {"000300": "failed: 超时"})
    outcome = steps.execute_item(db_session, item, batch)
    assert outcome.status == "failed"
    assert outcome.error_class == "source_error"


def test_sync_fund_stale_within_grace_is_pending(db_session, monkeypatch):
    _seed_calendar(db_session)
    batch = _make_batch(db_session)
    db_session.add(FundNav(fund_code="000001", nav_date=date(2026, 10, 8), unit_nav=Decimal("1.0")))
    db_session.commit()
    monkeypatch.setattr(
        nav_service,
        "sync_fund_nav_detailed",
        lambda db, code: {"synced_rows": 1, "source": "akshare", "quality": {"valid": True, "issues": []}},
    )

    outcome = steps.execute_item(db_session, _item(db_session, batch, "sync_nav", "fund", "000001"), batch)

    assert outcome.status == "pending"
    assert outcome.result_json["latest_nav_date"] == "2026-10-08"


def test_sync_fund_overdue_is_disclosure_failed(db_session, monkeypatch):
    _seed_calendar(db_session)
    batch = _make_batch(db_session)
    db_session.add(FundNav(fund_code="000001", nav_date=date(2026, 10, 5), unit_nav=Decimal("1.0")))
    db_session.commit()
    monkeypatch.setattr(
        nav_service,
        "sync_fund_nav_detailed",
        lambda db, code: {"synced_rows": 1, "source": "akshare", "quality": {"valid": True, "issues": []}},
    )

    outcome = steps.execute_item(db_session, _item(db_session, batch, "sync_nav", "fund", "000001"), batch)

    assert outcome.status == "failed"
    assert outcome.error_class == "disclosure_overdue"


def test_sync_fund_source_exception_is_real_failure(db_session, monkeypatch):
    _seed_calendar(db_session)
    batch = _make_batch(db_session)

    def _boom(db, code):
        raise ValueError("全部数据源同步失败")

    monkeypatch.setattr(nav_service, "sync_fund_nav_detailed", _boom)
    outcome = steps.execute_item(db_session, _item(db_session, batch, "sync_nav", "fund", "000001"), batch)

    assert outcome.status == "failed"
    assert outcome.error_class == "source_error"


def test_sync_listed_retries_once_then_succeeds(db_session, monkeypatch):
    _seed_calendar(db_session)
    db_session.add(
        Watchlist(fund_code="000001", fund_name="基金", is_active=True),
    )
    db_session.commit()
    batch, _ = batches.create_or_get_daily_batch(db_session, trade_date=TRADE_DATE)
    # 手动补一个股票项来测试重试
    listed = TaskBatchItem(
        batch_id=batch.id, step="sync_nav", asset_type="stock", asset_code="600519",
        status="queued", idempotency_key=f"{batch.idempotency_key}:sync_nav:stock:600519",
    )
    db_session.add(listed)
    db_session.add(AssetPriceDaily(asset_code="600519", price_date=TRADE_DATE, close=Decimal("10")))
    db_session.commit()

    attempts = {"count": 0}

    def _flaky(db, code, asset_type):
        attempts["count"] += 1
        if attempts["count"] == 1:
            raise RuntimeError("临时网络错误")
        return {"synced_rows": 1, "latest_price_date": TRADE_DATE}

    monkeypatch.setattr(asset_service, "sync_listed_asset", _flaky)
    outcome = steps.execute_item(db_session, listed, batch)

    assert attempts["count"] == 2
    assert outcome.status == "success"
    assert outcome.result_json["latest_price_date"] == "2026-10-09"


def test_sync_listed_exhausts_retries(db_session, monkeypatch):
    _seed_calendar(db_session)
    batch = _make_batch(db_session)
    listed = TaskBatchItem(
        batch_id=batch.id, step="sync_nav", asset_type="etf", asset_code="510300",
        status="queued", idempotency_key=f"{batch.idempotency_key}:sync_nav:etf:510300",
    )
    db_session.add(listed)
    db_session.commit()

    attempts = {"count": 0}

    def _always_fail(db, code, asset_type):
        attempts["count"] += 1
        raise RuntimeError("数据源不可用")

    monkeypatch.setattr(asset_service, "sync_listed_asset", _always_fail)
    outcome = steps.execute_item(db_session, listed, batch)

    assert attempts["count"] == 2
    assert outcome.status == "failed"
    assert outcome.error_class == "source_error"


def test_quality_check_reads_sync_diagnostics(db_session, monkeypatch):
    batch = _make_batch(db_session)
    db_session.add(FundNav(fund_code="000001", nav_date=TRADE_DATE, unit_nav=Decimal("1.0")))
    sync_item = _item(db_session, batch, "sync_nav", "fund", "000001")
    quality_item = _item(db_session, batch, "quality_check", "fund", "000001")
    sync_item.result_json = {"quality": {"valid": False, "issues": ["存在重复净值日期"]}}
    db_session.commit()

    outcome = steps.execute_item(db_session, quality_item, batch)
    assert outcome.status == "failed"
    assert outcome.error_class == "data_quality"
    assert outcome.result_json["issues"] == ["存在重复净值日期"]

    sync_item.result_json = {"quality": {"valid": True, "issues": []}}
    db_session.commit()
    outcome = steps.execute_item(db_session, quality_item, batch)
    assert outcome.status == "success"


def test_indicators_and_scores_map_value_errors(db_session, monkeypatch):
    batch = _make_batch(db_session)

    def _raise(db, code):
        raise ValueError("NAV data is empty")

    monkeypatch.setattr(indicator_service, "calculate_and_save_indicators", _raise)
    outcome = steps.execute_item(db_session, _item(db_session, batch, "calc_indicators", "fund", "000001"), batch)
    assert (outcome.status, outcome.error_class) == ("failed", "insufficient_history")

    monkeypatch.setattr(score_service, "calculate_and_save_score", _raise)
    outcome = steps.execute_item(db_session, _item(db_session, batch, "calc_scores", "fund", "000001"), batch)
    assert (outcome.status, outcome.error_class) == ("failed", "indicator_missing")


def test_alerts_handler_counts_and_maps_errors(db_session, monkeypatch):
    batch = _make_batch(db_session)
    item = _item(db_session, batch, "alerts", "", "")

    monkeypatch.setattr(alert_service, "generate_alerts", lambda db: [_FakeAlert("a"), _FakeAlert("b")])
    outcome = steps.execute_item(db_session, item, batch)
    assert outcome.status == "success"
    assert outcome.result_json == {"alert_count": 2}

    def _boom(db):
        raise RuntimeError("预警失败")

    monkeypatch.setattr(alert_service, "generate_alerts", _boom)
    outcome = steps.execute_item(db_session, item, batch)
    assert (outcome.status, outcome.error_class) == ("failed", "alert_error")


def test_report_handler_is_idempotent_per_batch(db_session, monkeypatch):
    batch = _make_batch(db_session)
    item = _item(db_session, batch, "report", "", "")
    batch.coverage_json = {"notes": ["1 个资产暂未发布 2026-10-09 数据"], "trade_date": "2026-10-09"}
    db_session.commit()

    def _no_ai():
        raise RuntimeError("AI 不可用")

    monkeypatch.setattr(report_service, "get_ai_client", _no_ai)

    first = steps.execute_item(db_session, item, batch)
    second = steps.execute_item(db_session, item, batch)

    assert first.status == "success"
    assert first.result_json["is_fallback"] is True
    assert second.result_json["report_id"] == first.result_json["report_id"]
    reports = list(db_session.scalars(select(AIReport).where(AIReport.batch_id == batch.id)))
    assert len(reports) == 1
    assert "batch_coverage" in (reports[0].input_snapshot or "")
    assert "暂未发布" in reports[0].content


def test_unknown_step_is_reported(db_session):
    batch = _make_batch(db_session)
    item = TaskBatchItem(
        batch_id=batch.id, step="mystery", asset_type="", asset_code="",
        status="queued", idempotency_key=f"{batch.idempotency_key}:mystery::",
    )
    db_session.add(item)
    db_session.commit()

    outcome = steps.execute_item(db_session, item, batch)
    assert (outcome.status, outcome.error_class) == ("failed", "unknown_step")
