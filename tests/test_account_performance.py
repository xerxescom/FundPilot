from datetime import date, timedelta
from decimal import Decimal

from app.db.models import FundNav
from app.services import account_service, portfolio_service


def _buy(db_session, code: str, amount: str, price: str, day: date, fee: str | None = None) -> None:
    data = {
        "fund_code": code,
        "trade_date": day,
        "trade_type": "buy",
        "amount": Decimal(amount),
        "nav": Decimal(price),
    }
    if fee is not None:
        data["fee"] = Decimal(fee)
    portfolio_service.create_transaction(db_session, data)


def _nav(db_session, code: str, day: date, price: str) -> None:
    db_session.add(FundNav(fund_code=code, nav_date=day, unit_nav=Decimal(price)))


def test_curve_starts_at_first_event_and_tracks_deposits(db_session):
    account_service.create_cash_event(
        db_session,
        {"event_date": date(2026, 1, 1), "event_type": "opening_balance", "amount": Decimal("1000")},
    )
    _buy(db_session, "000001", "1000", "10", date(2026, 1, 2))
    account_service.create_cash_event(
        db_session,
        {"event_date": date(2026, 1, 3), "event_type": "withdraw", "amount": Decimal("500")},
    )
    _nav(db_session, "000001", date(2026, 1, 2), "10")
    _nav(db_session, "000001", date(2026, 1, 3), "11")
    _nav(db_session, "000001", date(2026, 1, 4), "12")
    db_session.commit()

    result = account_service.account_performance(db_session, end=date(2026, 1, 4))
    points = {point["point_date"]: point for point in result["points"]}

    assert result["coverage"]["start_date"] == "2026-01-01"  # 曲线从最早事件日开始
    assert points[date(2026, 1, 1)]["total_assets"] == Decimal("1000.0000")
    assert points[date(2026, 1, 1)]["cumulative_pnl"] == Decimal("0.0000")
    assert points[date(2026, 1, 2)]["market_value"] == Decimal("1000.0000")
    assert points[date(2026, 1, 2)]["cumulative_pnl"] == Decimal("0.0000")
    # 出金 500：总资产 600，净投入 500（出金不产生盈亏）
    assert points[date(2026, 1, 3)]["cash"] == Decimal("-500.0000")
    assert points[date(2026, 1, 3)]["net_invested"] == Decimal("500.0000")
    assert points[date(2026, 1, 3)]["cumulative_pnl"] == Decimal("100.0000")
    assert points[date(2026, 1, 4)]["cumulative_pnl"] == Decimal("200.0000")
    assert result["is_complete"] is True


def test_pre_price_days_fall_back_to_cost_and_mark_incomplete(db_session):
    _buy(db_session, "000002", "1000", "10", date(2026, 1, 1))
    _nav(db_session, "000002", date(2026, 1, 3), "12")
    db_session.commit()

    result = account_service.account_performance(db_session, end=date(2026, 1, 3))
    first = result["points"][0]

    assert first["point_date"] == date(2026, 1, 1)
    assert first["market_value"] == Decimal("1000.0000")  # 尚无行情：按成本 10 × 100 份估值
    assert result["coverage"]["cost_fallback_days"] == 1
    assert result["is_complete"] is False
    assert any("缺少持仓行情" in note for note in result["notes"])


def test_asset_without_any_price_is_excluded_and_falls_back(db_session):
    _buy(db_session, "000003", "500", "1", date(2026, 1, 1))
    db_session.commit()

    result = account_service.account_performance(db_session, end=date(2026, 1, 5))

    assert result["coverage"]["excluded_assets"] == ["000003"]
    assert result["coverage"]["excluded_assets"] == result["coverage"]["missing_price_assets"]
    assert result["is_complete"] is False
    assert any("没有任何行情" in note for note in result["notes"])


def test_range_is_clamped_to_max_days(db_session):
    account_service.create_cash_event(
        db_session,
        {"event_date": date(2020, 1, 1), "event_type": "deposit", "amount": Decimal("100")},
    )

    result = account_service.account_performance(db_session, end=date(2026, 1, 1))

    coverage = result["coverage"]
    assert coverage["start_date"] == (date(2026, 1, 1) - timedelta(days=account_service.MAX_PERFORMANCE_DAYS)).isoformat()
    assert any("已截断" in note for note in result["notes"])


def test_empty_ledger_returns_empty_curve(db_session):
    result = account_service.account_performance(db_session, end=date(2026, 1, 1))

    assert result["points"] == []
    assert result["coverage"]["points"] == 0
    assert any("暂无任何事件" in note for note in result["notes"])
