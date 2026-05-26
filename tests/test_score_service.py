from datetime import date
from decimal import Decimal

from app.db.models import (
    FundInfo,
    FundIndicator,
    FundNav,
    FundScore,
    MarketIndexDaily,
    MarketValuationDaily,
    PortfolioPosition,
    Watchlist,
)
from app.services import score_service
from app.services.score_service import (
    available_strategies,
    score_indicator,
    score_indicator_with_strategy,
    score_payload,
    top_scores,
    top_scores_by_strategy,
)
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
    assert result["confidence_level"] in {"medium", "high"}
    assert result["buy_window_signal"] in {"favorable", "watch", "cautious"}
    assert result["reason"]


def test_score_indicator_missing_data_degrades():
    indicator = FundIndicator(fund_code="000001", calc_date=date.today())

    result = score_indicator(indicator)

    assert result["total_score"] < 60
    assert result["rating"] == "暂不关注"
    assert result["confidence_level"] == "low"
    assert result["buy_window_signal"] == "cautious"
    assert "数据不足" in result["reason"]


def test_score_indicator_full_data_can_emit_favorable_window():
    indicator = FundIndicator(
        fund_code="000001",
        calc_date=date.today(),
        return_1m=Decimal("0.02"),
        return_3m=Decimal("0.05"),
        return_6m=Decimal("0.12"),
        return_1y=Decimal("0.25"),
        max_drawdown_1y=Decimal("-0.05"),
        volatility_1y=Decimal("0.10"),
        sharpe_1y=Decimal("1.30"),
        win_rate_1y=Decimal("0.60"),
    )
    fund = FundInfo(
        fund_code="000001",
        fund_name="测试基金",
        establish_date=date(2020, 1, 1),
        fund_size=Decimal("30"),
        buy_status="开放申购",
    )

    result = score_indicator(indicator, fund, {"history_days": 500, "latest_nav_date": date.today()})

    assert result["confidence_level"] == "high"
    assert result["buy_window_signal"] == "favorable"


def test_score_indicator_stale_data_blocks_strong_window():
    indicator = FundIndicator(
        fund_code="000001",
        calc_date=date(2026, 1, 1),
        return_1m=Decimal("0.02"),
        return_3m=Decimal("0.05"),
        return_6m=Decimal("0.12"),
        return_1y=Decimal("0.25"),
        max_drawdown_1y=Decimal("-0.05"),
        volatility_1y=Decimal("0.10"),
        sharpe_1y=Decimal("1.30"),
        win_rate_1y=Decimal("0.60"),
    )

    result = score_indicator(indicator, nav_stats={"history_days": 500, "latest_nav_date": date(2026, 1, 1)})

    assert "stale_indicator" in result["risk_flags"]
    assert result["buy_window_signal"] != "favorable"


def test_score_indicator_trade_blocked_signal():
    indicator = FundIndicator(
        fund_code="000001",
        calc_date=date.today(),
        return_1m=Decimal("0.02"),
        return_3m=Decimal("0.05"),
        return_6m=Decimal("0.12"),
        return_1y=Decimal("0.25"),
        max_drawdown_1y=Decimal("-0.05"),
        volatility_1y=Decimal("0.10"),
        sharpe_1y=Decimal("1.30"),
        win_rate_1y=Decimal("0.60"),
    )
    fund = FundInfo(fund_code="000001", fund_name="测试基金", buy_status="暂停申购")

    result = score_indicator(indicator, fund)

    assert result["buy_window_signal"] == "blocked"
    assert "trade_blocked" in result["risk_flags"]
    assert "交易状态受限" in result["risk_flag_labels"]


def test_score_indicator_high_return_deep_drawdown_not_favorable():
    indicator = FundIndicator(
        fund_code="000001",
        calc_date=date.today(),
        return_1m=Decimal("0.03"),
        return_3m=Decimal("0.08"),
        return_6m=Decimal("0.16"),
        return_1y=Decimal("0.35"),
        max_drawdown_1y=Decimal("-0.28"),
        volatility_1y=Decimal("0.20"),
        sharpe_1y=Decimal("1.50"),
        win_rate_1y=Decimal("0.60"),
    )

    result = score_indicator(indicator)

    assert result["buy_window_signal"] != "favorable"


def test_score_payload_weak_market_downgrades_favorable_window(db_session):
    today = date.today()
    db_session.add_all(
        [
            FundInfo(
                fund_code="000001",
                fund_name="测试基金",
                establish_date=date(2020, 1, 1),
                fund_size=Decimal("30"),
                buy_status="开放申购",
            ),
            FundIndicator(
                fund_code="000001",
                calc_date=today,
                return_1m=Decimal("0.02"),
                return_3m=Decimal("0.05"),
                return_6m=Decimal("0.12"),
                return_1y=Decimal("0.25"),
                max_drawdown_1y=Decimal("-0.05"),
                volatility_1y=Decimal("0.10"),
                sharpe_1y=Decimal("1.30"),
                win_rate_1y=Decimal("0.60"),
            ),
            FundScore(fund_code="000001", score_date=today, total_score=Decimal("92"), rating="重点关注"),
            FundNav(fund_code="000001", nav_date=date(2025, 1, 1), unit_nav=Decimal("1.0")),
            FundNav(fund_code="000001", nav_date=today, unit_nav=Decimal("1.3")),
            MarketIndexDaily(index_code="sh000300", index_name="沪深300", trade_date=date(2026, 4, 1), close=Decimal("100")),
            MarketIndexDaily(index_code="sh000300", index_name="沪深300", trade_date=today, close=Decimal("90")),
        ]
    )
    db_session.commit()

    payload = score_payload(db_session, "000001")

    assert payload["market_signal"] == "weak"
    assert payload["buy_window_signal"] != "favorable"
    assert "market_weak" in payload["risk_flags"]
    assert "市场环境偏弱" in payload["risk_flag_labels"]


def test_score_payload_high_pe_percentile_weakens_market_signal(db_session):
    today = date.today()
    db_session.add_all(
        [
            FundInfo(
                fund_code="000001",
                fund_name="测试基金",
                establish_date=date(2020, 1, 1),
                fund_size=Decimal("30"),
                buy_status="开放申购",
            ),
            FundIndicator(
                fund_code="000001",
                calc_date=today,
                return_1m=Decimal("0.02"),
                return_3m=Decimal("0.05"),
                return_6m=Decimal("0.12"),
                return_1y=Decimal("0.25"),
                max_drawdown_1y=Decimal("-0.05"),
                volatility_1y=Decimal("0.10"),
                sharpe_1y=Decimal("1.30"),
                win_rate_1y=Decimal("0.60"),
            ),
            FundScore(fund_code="000001", score_date=today, total_score=Decimal("92"), rating="重点关注"),
            FundNav(fund_code="000001", nav_date=date(2025, 1, 1), unit_nav=Decimal("1.0")),
            FundNav(fund_code="000001", nav_date=today, unit_nav=Decimal("1.3")),
            MarketIndexDaily(index_code="sh000300", index_name="沪深300", trade_date=date(2026, 4, 1), close=Decimal("100")),
            MarketIndexDaily(index_code="sh000300", index_name="沪深300", trade_date=today, close=Decimal("106")),
            MarketValuationDaily(
                index_code="sh000300",
                index_name="沪深300",
                trade_date=today,
                pe_ttm=Decimal("18.50"),
                pe_percentile=Decimal("0.90"),
                source="test",
            ),
        ]
    )
    db_session.commit()

    payload = score_payload(db_session, "000001")

    assert payload["market_signal"] == "weak"
    assert payload["market_pe_percentile"] == 0.9
    assert payload["buy_window_signal"] != "favorable"
    assert "PE 百分位偏高" in payload["market_reason"]
    assert "market_weak" in payload["risk_flags"]


def test_score_payload_portfolio_concentration_downgrades_window(db_session):
    today = date.today()
    db_session.add_all(
        [
            FundInfo(
                fund_code="000001",
                fund_name="测试基金",
                establish_date=date(2020, 1, 1),
                fund_size=Decimal("30"),
                buy_status="开放申购",
            ),
            FundIndicator(
                fund_code="000001",
                calc_date=today,
                return_1m=Decimal("0.02"),
                return_3m=Decimal("0.05"),
                return_6m=Decimal("0.12"),
                return_1y=Decimal("0.25"),
                max_drawdown_1y=Decimal("-0.05"),
                volatility_1y=Decimal("0.10"),
                sharpe_1y=Decimal("1.30"),
                win_rate_1y=Decimal("0.60"),
            ),
            FundScore(fund_code="000001", score_date=today, total_score=Decimal("92"), rating="重点关注"),
            FundNav(fund_code="000001", nav_date=date(2025, 1, 1), unit_nav=Decimal("1.0")),
            FundNav(fund_code="000001", nav_date=today, unit_nav=Decimal("1.3")),
            PortfolioPosition(fund_code="000001", holding_share=Decimal("1000"), holding_amount=Decimal("1000")),
        ]
    )
    db_session.commit()

    payload = score_payload(db_session, "000001")

    assert payload["portfolio_fit_level"] == "low"
    assert payload["buy_window_signal"] == "cautious"
    assert "portfolio_concentration" in payload["risk_flags"]
    assert "持仓集中度偏高" in payload["risk_flag_labels"]


def test_score_payload_low_peer_rank_downgrades_window(db_session):
    today = date.today()
    rows = [
        ("000001", Decimal("0.25"), Decimal("-0.05"), Decimal("0.10"), Decimal("1.30")),
        ("000002", Decimal("0.40"), Decimal("-0.02"), Decimal("0.05"), Decimal("2.00")),
        ("000003", Decimal("0.42"), Decimal("-0.01"), Decimal("0.04"), Decimal("2.20")),
        ("000004", Decimal("0.38"), Decimal("-0.03"), Decimal("0.06"), Decimal("1.90")),
    ]
    for code, ret_1y, drawdown, volatility, sharpe in rows:
        db_session.add_all(
            [
                Watchlist(fund_code=code, fund_name=f"测试{code}", industry="宽基", is_active=True),
                FundInfo(
                    fund_code=code,
                    fund_name=f"测试{code}",
                    establish_date=date(2020, 1, 1),
                    fund_size=Decimal("30"),
                    buy_status="开放申购",
                ),
                FundIndicator(
                    fund_code=code,
                    calc_date=today,
                    return_1m=Decimal("0.02"),
                    return_3m=Decimal("0.05"),
                    return_6m=Decimal("0.12"),
                    return_1y=ret_1y,
                    max_drawdown_1y=drawdown,
                    volatility_1y=volatility,
                    sharpe_1y=sharpe,
                    win_rate_1y=Decimal("0.60"),
                ),
                FundNav(fund_code=code, nav_date=date(2025, 1, 1), unit_nav=Decimal("1.0")),
                FundNav(fund_code=code, nav_date=today, unit_nav=Decimal("1.3")),
            ]
        )
    db_session.add(FundScore(fund_code="000001", score_date=today, total_score=Decimal("92"), rating="重点关注"))
    db_session.commit()

    payload = score_payload(db_session, "000001")

    assert payload["peer_group"] == "宽基"
    assert payload["peer_group_size"] == 4
    assert payload["peer_percentile"] <= 0.30
    assert payload["buy_window_signal"] == "wait_pullback"
    assert "peer_rank_low" in payload["risk_flags"]
    assert "同类排名偏低" in payload["risk_flag_labels"]


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


def test_top_scores_by_strategy_reuses_context(monkeypatch, db_session):
    today = date.today()
    db_session.add_all(
        [
            FundIndicator(fund_code="000001", calc_date=today, return_1y=Decimal("0.20")),
            FundIndicator(fund_code="000002", calc_date=today, return_1y=Decimal("0.18")),
            FundScore(fund_code="000001", score_date=today, total_score=Decimal("80"), rating="可以观察"),
            FundScore(fund_code="000002", score_date=today, total_score=Decimal("75"), rating="可以观察"),
        ]
    )
    db_session.commit()
    calls = {"market": 0, "portfolio": 0, "correlation": 0, "peer": 0}

    def fake_market_context(db):
        calls["market"] += 1
        return []

    def fake_portfolio_overview(db):
        calls["portfolio"] += 1
        return {"total_value": Decimal("0"), "positions": []}

    def fake_high_correlation_pairs(db):
        calls["correlation"] += 1
        return []

    def fake_peer_rows(db):
        calls["peer"] += 1
        return []

    monkeypatch.setattr(score_service.market_service, "latest_market_context", fake_market_context)
    monkeypatch.setattr(score_service.portfolio_service, "portfolio_overview", fake_portfolio_overview)
    monkeypatch.setattr(score_service.correlation_service, "high_correlation_pairs", fake_high_correlation_pairs)
    monkeypatch.setattr(score_service, "_peer_source_rows", fake_peer_rows)

    rows = top_scores_by_strategy(db_session, strategy="default", limit=10)

    assert len(rows) == 2
    assert calls == {"market": 1, "portfolio": 1, "correlation": 1, "peer": 1}
