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


# ---------------------------------------------------------------- 未物化手工持仓


def test_manual_position_without_transactions_appears_in_curve(db_session):
    # 回归：start 恰好等于手工持仓 buy_date 时，此前会被整体漏掉，曲线记 0
    portfolio_service.create_position(
        db_session,
        {
            "fund_code": "000009",
            "holding_amount": Decimal("1000"),
            "holding_share": Decimal("1000"),
            "cost_nav": Decimal("1"),
            "buy_date": date(2026, 1, 1),
        },
    )

    result = account_service.account_performance(db_session, end=date(2026, 1, 3))

    first = result["points"][0]
    assert first["point_date"] == date(2026, 1, 1)
    assert first["market_value"] == Decimal("1000.0000")  # 无行情，按成本估值
    assert first["total_assets"] == Decimal("1000.0000")
    assert first["net_invested"] == Decimal("1000.0000")
    assert first["cumulative_pnl"] == Decimal("0.0000")


def test_manual_position_dated_inside_window_joins_at_its_date(db_session):
    account_service.create_cash_event(
        db_session,
        {"event_date": date(2026, 1, 1), "event_type": "deposit", "amount": Decimal("5000")},
    )
    portfolio_service.create_position(
        db_session,
        {
            "fund_code": "000010",
            "holding_amount": Decimal("1000"),
            "holding_share": Decimal("1000"),
            "cost_nav": Decimal("1"),
            "buy_date": date(2026, 1, 3),
        },
    )

    result = account_service.account_performance(db_session, end=date(2026, 1, 5))
    points = {point["point_date"]: point for point in result["points"]}

    assert points[date(2026, 1, 1)]["market_value"] == Decimal("0.0000")
    assert points[date(2026, 1, 3)]["market_value"] == Decimal("1000.0000")
    assert points[date(2026, 1, 3)]["net_invested"] == Decimal("6000.0000")
    assert result["returns"]["flow_count"] == 1  # 持仓出现算一次外部流入


# ---------------------------------------------------------------- TWR / XIRR


def test_twr_equals_simple_return_without_external_flows(db_session):
    account_service.create_cash_event(
        db_session,
        {"event_date": date(2026, 1, 1), "event_type": "opening_balance", "amount": Decimal("1000")},
    )
    _buy(db_session, "000011", "1000", "10", date(2026, 1, 1))
    _nav(db_session, "000011", date(2026, 1, 1), "10")
    _nav(db_session, "000011", date(2026, 1, 2), "11")
    db_session.commit()

    returns = account_service.account_performance(db_session, end=date(2026, 1, 2))["returns"]

    assert returns["status"] == "ok"
    assert returns["twr"] == Decimal("0.1")
    assert returns["flow_count"] == 0
    # 1 天区间：年化与 XIRR 不输出，但给出可解释的状态
    assert returns["xirr"] is None
    assert returns["xirr_status"] == "short_window"
    assert returns["twr_annualized"] is None
    assert any("short" in note or "不足" in note for note in returns["notes"])


def test_twr_xirr_and_return_rate_diverge_on_deposit_timing(db_session):
    # 期初 1000 买入，半年后追加 1000 闲置现金，期末市值 1200 + 现金 1000
    account_service.create_cash_event(
        db_session,
        {"event_date": date(2025, 1, 1), "event_type": "opening_balance", "amount": Decimal("1000")},
    )
    _buy(db_session, "000012", "1000", "1", date(2025, 1, 1))
    _nav(db_session, "000012", date(2025, 1, 1), "1")
    _nav(db_session, "000012", date(2025, 7, 1), "1.2")
    _nav(db_session, "000012", date(2026, 1, 1), "1.2")
    account_service.create_cash_event(
        db_session,
        {"event_date": date(2025, 7, 1), "event_type": "deposit", "amount": Decimal("1000")},
    )
    db_session.commit()

    result = account_service.account_performance(db_session, end=date(2026, 1, 1))
    returns = result["returns"]
    last = result["points"][-1]

    assert last["total_assets"] == Decimal("2200.0000")
    assert last["return_rate"] == Decimal("0.1")  # 简单口径：累计盈亏/净投入
    assert returns["twr"] == Decimal("0.2")  # 剔除入金时点影响
    assert returns["flow_count"] == 1
    assert returns["twr_annualized"] == Decimal("0.2")
    # 资金加权：晚投入的那笔没赚到收益，XIRR 介于简单口径与 TWR 之间
    assert returns["xirr_status"] == "ok"
    assert Decimal("0.1") < returns["xirr"] < Decimal("0.2")


def test_zero_value_segment_is_skipped_with_note(db_session):
    account_service.create_cash_event(
        db_session, {"event_date": date(2026, 1, 1), "event_type": "deposit", "amount": Decimal("1000")}
    )
    account_service.create_cash_event(
        db_session, {"event_date": date(2026, 1, 2), "event_type": "withdraw", "amount": Decimal("1000")}
    )
    account_service.create_cash_event(
        db_session, {"event_date": date(2026, 1, 3), "event_type": "deposit", "amount": Decimal("500")}
    )

    result = account_service.account_performance(db_session, end=date(2026, 1, 3))
    returns = result["returns"]
    points = {point["point_date"]: point for point in result["points"]}

    assert points[date(2026, 1, 2)]["total_assets"] == Decimal("0.0000")
    assert returns["status"] == "ok"
    assert returns["twr"] == Decimal("0")  # 只有 1/1→1/2 段可计算
    assert [point["index"] for point in returns["twr_index"]] == [Decimal("1"), Decimal("1"), None]
    assert any("跳过" in note for note in returns["notes"])


def test_returns_block_reports_no_data_for_empty_ledger(db_session):
    result = account_service.account_performance(db_session, end=date(2026, 1, 1))

    assert result["returns"]["status"] == "no_data"
    assert result["returns"]["twr"] is None
    assert result["returns"]["xirr"] is None
    assert any("无法计算" in note for note in result["returns"]["notes"])


def test_account_summary_exposes_returns_without_curve_index(db_session):
    account_service.create_cash_event(
        db_session,
        {"event_date": date(2025, 1, 1), "event_type": "opening_balance", "amount": Decimal("1000")},
    )
    _buy(db_session, "000013", "1000", "1", date(2025, 1, 1))
    _nav(db_session, "000013", date(2025, 1, 1), "1")
    _nav(db_session, "000013", date(2026, 1, 1), "1.1")
    db_session.commit()

    summary = account_service.account_summary(db_session)
    returns = summary["returns"]

    assert returns["basis"] == "twr_daily_linked + xirr_newton"
    assert returns["twr"] == Decimal("0.1")
    assert "twr_index" not in returns  # 汇总接口不返回逐点索引
    assert any("returns" in note for note in summary["notes"])
