from datetime import date
from decimal import Decimal

import pytest

from app.db.models import FundNav
from app.services import account_service, portfolio_service


def _seed_reconciliation_scenario(db_session) -> None:
    """手工对账场景：期初现金 + 入金 − 出金，买入/卖出/红利再投/现金分红各一笔。"""
    account_service.create_cash_event(
        db_session,
        {"event_date": date(2026, 1, 1), "event_type": "opening_balance", "amount": Decimal("5000")},
    )
    account_service.create_cash_event(
        db_session,
        {"event_date": date(2026, 1, 2), "event_type": "deposit", "amount": Decimal("10000")},
    )
    account_service.create_cash_event(
        db_session,
        {"event_date": date(2026, 1, 3), "event_type": "withdraw", "amount": Decimal("2000")},
    )
    portfolio_service.create_transaction(
        db_session,
        {
            "fund_code": "000001",
            "trade_date": date(2026, 1, 5),
            "trade_type": "buy",
            "amount": Decimal("1234.50"),
            "nav": Decimal("1.234500"),
            "share": Decimal("1000"),
            "fee": Decimal("5"),
        },
    )
    portfolio_service.create_transaction(
        db_session,
        {
            "fund_code": "000001",
            "trade_date": date(2026, 2, 1),
            "trade_type": "sell",
            "amount": Decimal("600"),
            "nav": Decimal("1.500000"),
            "fee": Decimal("5"),
        },
    )
    portfolio_service.create_transaction(
        db_session,
        {
            "fund_code": "000001",
            "trade_date": date(2026, 3, 1),
            "trade_type": "dividend_reinvest",
            "amount": Decimal("30"),
            "nav": Decimal("1.000000"),
        },
    )
    account_service.create_cash_event(
        db_session,
        {
            "event_date": date(2026, 3, 5),
            "event_type": "dividend",
            "amount": Decimal("20"),
            "asset_type": "fund",
            "asset_code": "000001",
        },
    )
    db_session.add(FundNav(fund_code="000001", nav_date=date(2026, 3, 31), unit_nav=Decimal("1.400000")))
    db_session.commit()


def test_account_summary_hand_computed_reconciliation(db_session):
    _seed_reconciliation_scenario(db_session)

    summary = account_service.account_summary(db_session)

    assert summary["cash_balance"] == Decimal("12375.5000")
    assert summary["market_value"] == Decimal("882.000000")
    assert summary["total_assets"] == Decimal("13257.500000")
    assert summary["initial_investment"] == Decimal("5000")
    assert summary["deposits_total"] == Decimal("10000")
    assert summary["withdrawals_total"] == Decimal("2000")
    assert summary["net_invested"] == Decimal("13000")
    assert summary["realized_pnl_total"] == Decimal("99.2000")
    assert summary["unrealized_pnl_total"] == Decimal("108.300000")
    assert summary["other_income_total"] == Decimal("50.0000")  # 现金分红 20 + 红利再投 30

    # 恒等式：累计盈亏 = 已实现 + 未实现 + 其他收益
    assert summary["cumulative_pnl"] == Decimal("257.500000")
    assert summary["reconciliation_difference"] == Decimal("0.000000")
    assert abs(summary["reconciliation_difference"]) <= account_service.RECONCILIATION_TOLERANCE
    assert summary["return_rate"] == pytest.approx(Decimal("257.5") / Decimal("13000"))
    assert summary["is_complete"] is True


def test_cash_balance_reflects_deletes(db_session):
    event = account_service.create_cash_event(
        db_session,
        {"event_date": date(2026, 1, 1), "event_type": "deposit", "amount": Decimal("1000")},
    )
    assert account_service.cash_balance(db_session) == Decimal("1000.0000")

    assert account_service.delete_cash_event(db_session, event.id) is True
    assert account_service.cash_balance(db_session) == Decimal("0.0000")
    assert account_service.delete_cash_event(db_session, event.id) is False


def test_event_validation_and_sign_canonicalization(db_session):
    with pytest.raises(ValueError, match="金额不能为 0"):
        account_service.create_cash_event(
            db_session,
            {"event_date": date(2026, 1, 1), "event_type": "deposit", "amount": Decimal("0")},
        )

    with pytest.raises(ValueError, match="event_type"):
        account_service.create_cash_event(
            db_session,
            {"event_date": date(2026, 1, 1), "event_type": "unknown", "amount": Decimal("1")},
        )

    withdraw = account_service.create_cash_event(
        db_session,
        {"event_date": date(2026, 1, 2), "event_type": "withdraw", "amount": Decimal("100")},
    )
    assert withdraw.amount == Decimal("-100.0000")

    dividend = account_service.create_cash_event(
        db_session,
        {"event_date": date(2026, 1, 3), "event_type": "dividend", "amount": Decimal("-50")},
    )
    assert dividend.amount == Decimal("50.0000")

    adjustment = account_service.create_cash_event(
        db_session,
        {"event_date": date(2026, 1, 4), "event_type": "adjustment", "amount": Decimal("-8.5")},
    )
    assert adjustment.amount == Decimal("-8.5000")

    account_service.create_cash_event(
        db_session,
        {"event_date": date(2026, 1, 5), "event_type": "opening_balance", "amount": Decimal("1")},
    )
    with pytest.raises(ValueError, match="期初现金只能设置一次"):
        account_service.create_cash_event(
            db_session,
            {"event_date": date(2026, 1, 6), "event_type": "opening_balance", "amount": Decimal("2")},
        )


def test_deposits_do_not_create_profit(db_session):
    account_service.create_cash_event(
        db_session,
        {"event_date": date(2026, 1, 1), "event_type": "deposit", "amount": Decimal("10000")},
    )

    summary = account_service.account_summary(db_session)

    assert summary["cash_balance"] == Decimal("10000.0000")
    assert summary["net_invested"] == Decimal("10000")
    assert summary["cumulative_pnl"] == Decimal("0.000000")


def test_incomplete_valuation_reports_known_values_only(db_session):
    account_service.create_cash_event(
        db_session,
        {"event_date": date(2026, 1, 1), "event_type": "deposit", "amount": Decimal("1000")},
    )
    portfolio_service.create_transaction(
        db_session,
        {
            "fund_code": "000002",
            "trade_date": date(2026, 1, 5),
            "trade_type": "buy",
            "amount": Decimal("500"),
            "nav": Decimal("1.000000"),
        },
    )

    summary = account_service.account_summary(db_session)

    assert summary["market_value"] is None
    assert summary["total_assets"] is None
    assert summary["cumulative_pnl"] is None
    assert summary["return_rate"] is None
    assert summary["unrealized_pnl_total"] is None
    assert summary["reconciliation_difference"] is None
    assert summary["known_total_assets"] == Decimal("500.000000")  # 现金 1000 - 买入 500
    assert summary["missing_price_assets"][0]["asset_code"] == "000002"
    assert any("估值不完整" in note for note in summary["notes"])
