from datetime import date
from decimal import Decimal

from app.db.models import FundIndicator, FundScore
from app.services.score_service import available_strategies, score_indicator, score_indicator_with_strategy, top_scores, top_scores_by_strategy
from app.services.watchlist_service import infer_industry


def test_score_indicator_high_quality():
    indicator = FundIndicator(
        fund_code="000001",
        calc_date=date.today(),
        return_1y=Decimal("0.25"),
        max_drawdown_1y=Decimal("-0.05"),
        volatility_1y=Decimal("0.10"),
        win_rate_1y=Decimal("0.60"),
    )

    result = score_indicator(indicator)

    assert result["total_score"] >= 85
    assert result["rating"] == "重点关注"
    assert result["reason"]


def test_score_indicator_missing_data_degrades():
    indicator = FundIndicator(fund_code="000001", calc_date=date.today())

    result = score_indicator(indicator)

    assert result["total_score"] < 60
    assert result["rating"] == "暂不关注"
    assert "数据不足" in result["reason"]


def test_top_scores_deduplicates_by_latest_fund_code(db_session):
    db_session.add_all(
        [
            FundScore(
                fund_code="000001",
                score_date=date(2026, 1, 1),
                total_score=Decimal("99"),
                rating="重点关注",
            ),
            FundScore(
                fund_code="000001",
                score_date=date(2026, 1, 2),
                total_score=Decimal("70"),
                rating="可以观察",
            ),
            FundScore(
                fund_code="000002",
                score_date=date(2026, 1, 2),
                total_score=Decimal("80"),
                rating="可以观察",
            ),
        ]
    )
    db_session.commit()

    rows = top_scores(db_session)

    assert [row.fund_code for row in rows] == ["000002", "000001"]
    assert rows[1].total_score == Decimal("70.00")


def test_infer_industry_from_fund_name_and_type():
    assert infer_industry("招商中证白酒指数", "股票指数") == "消费"
    assert infer_industry("易方达沪深300ETF联接", "指数型") == "宽基"
    assert infer_industry("广发纳斯达克100QDII", None) == "海外/QDII"
    assert infer_industry("某某纯债债券", None) == "债券"


def test_score_strategies_are_available():
    strategies = available_strategies()

    assert {item["key"] for item in strategies} >= {"default", "steady", "growth", "low_drawdown"}


def test_score_indicator_with_strategy_changes_context():
    indicator = FundIndicator(
        fund_code="000001",
        calc_date=date.today(),
        return_1y=Decimal("0.30"),
        max_drawdown_1y=Decimal("-0.25"),
        volatility_1y=Decimal("0.32"),
        win_rate_1y=Decimal("0.52"),
    )

    growth = score_indicator_with_strategy(indicator, strategy="growth")
    steady = score_indicator_with_strategy(indicator, strategy="steady")

    assert growth["strategy_name"] == "进攻型"
    assert steady["strategy_name"] == "稳健型"
    assert growth["total_score"] > steady["total_score"]


def test_top_scores_by_strategy_uses_latest_indicators(db_session):
    db_session.add_all(
        [
            FundIndicator(
                fund_code="000001",
                calc_date=date(2026, 1, 1),
                return_1y=Decimal("0.30"),
                max_drawdown_1y=Decimal("-0.25"),
                volatility_1y=Decimal("0.32"),
                win_rate_1y=Decimal("0.52"),
            ),
            FundIndicator(
                fund_code="000002",
                calc_date=date(2026, 1, 1),
                return_1y=Decimal("0.04"),
                max_drawdown_1y=Decimal("-0.06"),
                volatility_1y=Decimal("0.10"),
                win_rate_1y=Decimal("0.58"),
            ),
        ]
    )
    db_session.commit()

    growth = top_scores_by_strategy(db_session, strategy="growth")
    steady = top_scores_by_strategy(db_session, strategy="steady")

    assert growth[0]["fund_code"] == "000001"
    assert steady[0]["fund_code"] == "000002"
