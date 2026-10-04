from datetime import date, datetime
from decimal import Decimal

from app.db.models import (
    AIReport,
    FundIndicator,
    FundNav,
    FundScore,
    TaskBatch,
    TaskBatchItem,
    TaskRunLog,
    Watchlist,
)
from app.services.data_health_service import data_health_overview, fund_data_health


def _add_batch_sync_item(db_session, status: str, error_message: str | None = None) -> None:
    batch = TaskBatch(
        batch_type="daily_update",
        idempotency_key="daily_update:2026-05-24",
        status="partial_success",
        trade_date=date(2026, 5, 24),
    )
    db_session.add(batch)
    db_session.flush()
    db_session.add(
        TaskBatchItem(
            batch_id=batch.id,
            step="sync_nav",
            asset_type="fund",
            asset_code="000001",
            status=status,
            error_message=error_message,
            idempotency_key="daily_update:2026-05-24:sync_nav:fund:000001",
            finished_at=datetime(2026, 5, 24, 18, 0),
        )
    )
    db_session.commit()


def test_data_health_detects_stale_missing_return_and_pending_indicator(db_session):
    db_session.add(Watchlist(fund_code="000001", fund_name="测试基金", is_active=True))
    db_session.add(
        FundNav(
            fund_code="000001",
            nav_date=date(2026, 5, 1),
            unit_nav=Decimal("1.0"),
            daily_return=None,
        )
    )
    db_session.add(
        FundIndicator(
            fund_code="000001",
            calc_date=date(2026, 4, 30),
        )
    )
    db_session.commit()

    overview = data_health_overview(db_session, today=date(2026, 5, 24))

    assert overview["stale_fund_count"] == 1
    assert overview["pending_indicator_count"] == 1
    assert overview["pending_score_count"] == 1
    assert overview["pending_report_count"] == 0
    assert overview["missing_daily_return_count"] == 1
    assert "最新净值日期过时" in overview["funds"][0]["issues"]
    assert "评分需要重新生成" in overview["funds"][0]["issues"]


def test_data_health_detects_pending_fund_report(db_session):
    db_session.add(Watchlist(fund_code="000001", fund_name="测试基金", is_active=True))
    db_session.add(FundNav(fund_code="000001", nav_date=date(2026, 5, 24), unit_nav=Decimal("1.0")))
    db_session.add(FundIndicator(fund_code="000001", calc_date=date(2026, 5, 24)))
    db_session.add(FundScore(fund_code="000001", score_date=date(2026, 5, 24), total_score=Decimal("80")))
    db_session.commit()

    overview = data_health_overview(db_session, today=date(2026, 5, 24))

    assert overview["pending_score_count"] == 0
    assert overview["pending_report_count"] == 1
    assert "基金解释报告待生成" in overview["funds"][0]["issues"]


def test_data_health_clears_report_todo_when_report_created_after_latest_score(db_session):
    db_session.add(Watchlist(fund_code="000001", fund_name="测试基金", is_active=True))
    db_session.add(FundNav(fund_code="000001", nav_date=date(2026, 5, 24), unit_nav=Decimal("1.0")))
    db_session.add(FundIndicator(fund_code="000001", calc_date=date(2026, 5, 24)))
    db_session.add(
        FundScore(
            fund_code="000001",
            score_date=date(2026, 5, 24),
            total_score=Decimal("80"),
            created_at=datetime(2026, 5, 23, 23, 30),
        )
    )
    db_session.add(
        AIReport(
            report_type="fund",
            target_code="000001",
            title="000001 基金解释",
            content="已生成基金解释。",
            created_at=datetime(2026, 5, 24, 0, 10),
        )
    )
    db_session.commit()

    overview = data_health_overview(db_session, today=date(2026, 5, 24))

    assert overview["pending_report_count"] == 0
    assert "基金解释报告待生成" not in overview["funds"][0]["issues"]


def test_data_health_clears_report_todo_when_report_created_after_score_even_if_report_date_is_earlier(db_session):
    db_session.add(Watchlist(fund_code="000001", fund_name="测试基金", is_active=True))
    db_session.add(FundNav(fund_code="000001", nav_date=date(2026, 5, 27), unit_nav=Decimal("1.0")))
    db_session.add(FundIndicator(fund_code="000001", calc_date=date(2026, 5, 27)))
    db_session.add(
        FundScore(
            fund_code="000001",
            score_date=date(2026, 5, 27),
            total_score=Decimal("80"),
            created_at=datetime(2026, 5, 26, 23, 50),
        )
    )
    db_session.add(
        AIReport(
            report_type="fund",
            target_code="000001",
            title="000001 基金解释",
            content="已生成基金解释。",
            created_at=datetime(2026, 5, 26, 23, 55),
        )
    )
    db_session.commit()

    overview = data_health_overview(db_session, today=date(2026, 5, 27))

    assert overview["pending_report_count"] == 0
    assert "基金解释报告待生成" not in overview["funds"][0]["issues"]


def test_sync_status_reads_queued_result_json(db_session):
    db_session.add(Watchlist(fund_code="000001", fund_name="测试基金", is_active=True))
    db_session.add(
        TaskRunLog(
            task_name="queued_sync_watchlist_nav",
            status="failed",
            created_at=datetime(2026, 5, 24, 9, 0),
            result_json={"000001": {"status": "failed", "quality": {"issues": ["全部数据源同步失败"]}}},
        )
    )
    db_session.commit()

    health = fund_data_health(db_session, "000001", today=date(2026, 5, 25))

    assert health["latest_sync_status"] == "failed"
    assert "全部数据源同步失败" in health["latest_failure_reason"]
    assert health["latest_sync_date"] == date(2026, 5, 24)


def test_sync_status_prefers_result_json_over_truncated_message(db_session):
    db_session.add(Watchlist(fund_code="000001", fund_name="测试基金", is_active=True))
    truncated = ("x" * 1990 + str({"000001": {"status": "success"}}))[:2000]
    db_session.add(
        TaskRunLog(
            task_name="manual_sync_watchlist_nav",
            status="success",
            message=truncated,
            result_json={"000001": {"status": "success"}},
            created_at=datetime(2026, 5, 24, 9, 0),
        )
    )
    db_session.commit()

    health = fund_data_health(db_session, "000001", today=date(2026, 5, 25))

    assert health["latest_sync_status"] == "success"


def test_health_reads_pending_batch_item_as_not_published(db_session):
    db_session.add(Watchlist(fund_code="000001", fund_name="测试基金", is_active=True))
    db_session.add(
        FundNav(
            fund_code="000001",
            nav_date=date(2026, 5, 24),
            unit_nav=Decimal("1.0"),
            daily_return=Decimal("0.010000"),
        )
    )
    db_session.commit()
    _add_batch_sync_item(db_session, "pending")

    health = fund_data_health(db_session, "000001", today=date(2026, 5, 25))

    assert health["latest_sync_status"] == "pending"
    assert health["latest_sync_date"] == date(2026, 5, 24)
    assert any("暂未发布" in issue for issue in health["issues"])
    assert health["status"] == "正常"  # 暂未发布不是失败，不改变健康状态


def test_health_reads_failed_batch_item_and_marks_attention(db_session):
    db_session.add(Watchlist(fund_code="000001", fund_name="测试基金", is_active=True))
    db_session.add(
        FundNav(
            fund_code="000001",
            nav_date=date(2026, 5, 24),
            unit_nav=Decimal("1.0"),
            daily_return=Decimal("0.010000"),
        )
    )
    db_session.commit()
    _add_batch_sync_item(db_session, "failed", error_message="全部数据源同步失败")

    health = fund_data_health(db_session, "000001", today=date(2026, 5, 25))

    assert health["latest_sync_status"] == "failed"
    assert health["latest_failure_reason"] == "全部数据源同步失败"
    assert health["status"] == "需关注"
    assert any("同步失败" in issue for issue in health["issues"])


def test_health_reads_interrupted_batch_item_as_recoverable(db_session):
    db_session.add(Watchlist(fund_code="000001", fund_name="测试基金", is_active=True))
    db_session.add(
        FundNav(
            fund_code="000001",
            nav_date=date(2026, 5, 24),
            unit_nav=Decimal("1.0"),
            daily_return=Decimal("0.010000"),
        )
    )
    db_session.commit()
    _add_batch_sync_item(db_session, "interrupted", error_message="worker 中断，租约已过期，等待恢复")

    health = fund_data_health(db_session, "000001", today=date(2026, 5, 25))

    assert health["latest_sync_status"] == "interrupted"
    assert health["status"] == "需关注"
    assert any("中断" in issue for issue in health["issues"])


def test_sync_status_legacy_message_fallback_still_works(db_session):
    db_session.add(Watchlist(fund_code="000001", fund_name="测试基金", is_active=True))
    db_session.add(
        TaskRunLog(
            task_name="manual_sync_watchlist_nav",
            status="success",
            message=str({"000001": {"status": "success"}}),
            created_at=datetime(2026, 5, 24, 9, 0),
        )
    )
    db_session.commit()

    health = fund_data_health(db_session, "000001", today=date(2026, 5, 25))

    assert health["latest_sync_status"] == "success"
    assert health["latest_sync_date"] == date(2026, 5, 24)
