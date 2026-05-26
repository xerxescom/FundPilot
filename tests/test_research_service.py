from datetime import date
from decimal import Decimal

from app.db.models import FundIndicator, FundScore, Watchlist
from app.services.research_service import compare_funds, industry_overview, score_trend


def test_compare_funds_and_score_trend(db_session):
    db_session.add(Watchlist(fund_code="000001", fund_name="测试A", industry="宽基", is_active=True))
    db_session.add(Watchlist(fund_code="000002", fund_name="测试B", industry="医药", is_active=True))
    db_session.add(
        FundIndicator(
            fund_code="000001",
            calc_date=date(2026, 5, 20),
            return_1y=Decimal("0.12"),
            max_drawdown_1y=Decimal("-0.08"),
            volatility_1y=Decimal("0.18"),
        )
    )
    db_session.add(
        FundScore(
            fund_code="000001",
            score_date=date(2026, 5, 20),
            total_score=Decimal("80"),
            rating="可以观察",
        )
    )
    db_session.add(
        FundScore(
            fund_code="000001",
            score_date=date(2026, 5, 21),
            total_score=Decimal("82"),
            rating="可以观察",
        )
    )
    db_session.commit()

    comparison = compare_funds(db_session, ["000001", "000002"])
    trend = score_trend(db_session, "000001")
    industries = industry_overview(db_session)

    assert comparison["funds"][0]["fund_name"] == "测试A"
    assert comparison["funds"][0]["score"] == 82.0
    assert [row["total_score"] for row in trend] == [80.0, 82.0]
    assert trend[0]["trend_direction"] == "baseline"
    assert trend[1]["score_change"] == 2.0
    assert trend[1]["trend_direction"] == "flat"
    assert {row["industry"] for row in industries} == {"宽基", "医药"}


def test_score_trend_marks_large_score_and_rating_changes(db_session):
    db_session.add_all(
        [
            FundScore(
                fund_code="000001",
                score_date=date(2026, 5, 20),
                total_score=Decimal("82"),
                rating="可以观察",
            ),
            FundScore(
                fund_code="000001",
                score_date=date(2026, 5, 21),
                total_score=Decimal("75"),
                rating="一般",
            ),
        ]
    )
    db_session.commit()

    trend = score_trend(db_session, "000001")

    assert trend[1]["score_change"] == -7.0
    assert trend[1]["trend_direction"] == "down"
    assert trend[1]["rating_changed"] is True
    assert trend[1]["previous_rating"] == "可以观察"
