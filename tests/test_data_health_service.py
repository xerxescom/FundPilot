from datetime import date
from decimal import Decimal

from app.db.models import FundIndicator, FundNav, FundScore, Watchlist
from app.services.data_health_service import data_health_overview


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
