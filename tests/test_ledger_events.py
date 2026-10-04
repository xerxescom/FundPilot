from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.models import PortfolioPosition, PortfolioTransaction
from app.services.portfolio_service import (
    AUTO_SUMMARY_NOTE,
    create_transaction,
    delete_transaction,
    list_transactions,
    portfolio_overview,
)


def _position(db_session, code: str = "000001") -> PortfolioPosition:
    return db_session.scalar(
        select(PortfolioPosition).where(
            (PortfolioPosition.asset_code == code)
            | (PortfolioPosition.asset_code.is_(None) & (PortfolioPosition.fund_code == code))
        )
    )


def _buy(db_session, code: str = "000001", amount: str = "1000", price: str = "1", day: date = date(2026, 5, 1)):
    return create_transaction(
        db_session,
        {
            "fund_code": code,
            "trade_date": day,
            "trade_type": "buy",
            "amount": Decimal(amount),
            "nav": Decimal(price),
        },
    )


def test_reinvest_adds_shares_and_cost_without_fee(db_session):
    _buy(db_session)

    create_transaction(
        db_session,
        {
            "fund_code": "000001",
            "trade_date": date(2026, 6, 1),
            "trade_type": "dividend_reinvest",
            "amount": Decimal("60"),
            "nav": Decimal("1.200000"),
        },
    )

    position = _position(db_session)
    assert position.holding_share == Decimal("1050.0000")
    assert position.holding_amount == Decimal("1060.0000")  # 分红 60 被资本化进成本
    assert position.cost_nav == Decimal("1.009524")  # 1060 / 1050


def test_reinvest_rejects_fee(db_session):
    with pytest.raises(ValueError, match="红利再投暂不支持手续费"):
        create_transaction(
            db_session,
            {
                "fund_code": "000001",
                "trade_date": date(2026, 6, 1),
                "trade_type": "dividend_reinvest",
                "amount": Decimal("60"),
                "nav": Decimal("1.200000"),
                "fee": Decimal("1"),
            },
        )


def test_split_changes_only_shares(db_session):
    _buy(db_session)

    create_transaction(
        db_session,
        {
            "fund_code": "000001",
            "trade_date": date(2026, 6, 1),
            "trade_type": "split",
            "amount": Decimal("0"),
            "share": Decimal("1000"),
        },
    )

    position = _position(db_session)
    assert position.holding_share == Decimal("2000.0000")
    assert position.holding_amount == Decimal("1000.0000")  # 成本不变
    assert position.cost_nav == Decimal("0.500000")


def test_split_rejects_amount_and_zero_delta(db_session):
    with pytest.raises(ValueError, match="拆分交易金额必须为 0"):
        create_transaction(
            db_session,
            {
                "fund_code": "000001",
                "trade_date": date(2026, 6, 1),
                "trade_type": "split",
                "amount": Decimal("10"),
                "share": Decimal("100"),
            },
        )
    with pytest.raises(ValueError, match="必须填写份额变动"):
        create_transaction(
            db_session,
            {
                "fund_code": "000001",
                "trade_date": date(2026, 6, 1),
                "trade_type": "split",
                "amount": Decimal("0"),
            },
        )


def test_negative_split_below_zero_is_rejected(db_session):
    _buy(db_session)

    with pytest.raises(ValueError, match="拆分后份额为负"):
        create_transaction(
            db_session,
            {
                "fund_code": "000001",
                "trade_date": date(2026, 6, 1),
                "trade_type": "split",
                "amount": Decimal("0"),
                "share": Decimal("-2000"),
            },
        )


def test_split_then_partial_sell_realized_uses_post_split_cost(db_session):
    _buy(db_session)
    create_transaction(
        db_session,
        {
            "fund_code": "000001",
            "trade_date": date(2026, 6, 1),
            "trade_type": "split",
            "amount": Decimal("0"),
            "share": Decimal("1000"),
        },
    )

    sell = create_transaction(
        db_session,
        {
            "fund_code": "000001",
            "trade_date": date(2026, 6, 2),
            "trade_type": "sell",
            "amount": Decimal("550"),
            "nav": Decimal("1.100000"),
            "share": Decimal("500"),
        },
    )

    # 拆分后均价 0.5：已实现 = 550 - 0.5 × 500 = 300
    assert sell.realized_pnl == Decimal("300.0000")
    position = _position(db_session)
    assert position.holding_share == Decimal("1500.0000")
    assert position.holding_amount == Decimal("750.0000")


def test_sell_all_then_rebuy_keeps_prior_realized(db_session):
    _buy(db_session, amount="100", price="1")
    sell = create_transaction(
        db_session,
        {
            "fund_code": "000001",
            "trade_date": date(2026, 5, 2),
            "trade_type": "sell",
            "amount": Decimal("120"),
            "nav": Decimal("1.200000"),
        },
    )
    assert sell.realized_pnl == Decimal("20.0000")
    position = _position(db_session)
    assert position.holding_share == Decimal("0.0000")
    assert position.holding_amount == Decimal("0.0000")

    _buy(db_session, amount="200", price="2", day=date(2026, 5, 3))
    refreshed = db_session.get(PortfolioTransaction, sell.id)
    assert refreshed.realized_pnl == Decimal("20.0000")  # 清仓再买入不改变历史已实现
    position = _position(db_session)
    assert position.holding_share == Decimal("100.0000")
    assert position.holding_amount == Decimal("200.0000")


def test_realized_recomputed_after_backdated_insert_and_delete(db_session):
    _buy(db_session, amount="100", price="1")  # 2026-05-10 → 用默认 5-01
    sell = create_transaction(
        db_session,
        {
            "fund_code": "000001",
            "trade_date": date(2026, 5, 11),
            "trade_type": "sell",
            "amount": Decimal("75"),
            "nav": Decimal("1.500000"),
            "share": Decimal("50"),
        },
    )
    assert sell.realized_pnl == Decimal("25.0000")  # 均价 1：75 - 50

    backdated = _buy(db_session, amount="300", price="3", day=date(2026, 4, 1))
    refreshed = db_session.get(PortfolioTransaction, sell.id)
    # 均价变为 (100+300)/200 = 2：75 - 100 = -25
    assert refreshed.realized_pnl == Decimal("-25.0000")

    delete_transaction(db_session, backdated.id)
    refreshed = db_session.get(PortfolioTransaction, sell.id)
    assert refreshed.realized_pnl == Decimal("25.0000")  # 删除后确定性重算


def test_opening_then_reinvest_same_day_follows_insertion_order(db_session):
    position = PortfolioPosition(
        fund_code="000001",
        holding_amount=Decimal("1000"),
        holding_share=Decimal("1000"),
        cost_nav=Decimal("1.000000"),
        buy_date=date(2026, 1, 1),
        note="由中信证券持仓截图导入（2026-01-01）",
    )
    db_session.add(position)
    db_session.commit()

    create_transaction(
        db_session,
        {
            "fund_code": "000001",
            "trade_date": date(2026, 1, 1),  # 与期初同一天：按 id 顺序，期初在前
            "trade_type": "dividend_reinvest",
            "amount": Decimal("50"),
            "nav": Decimal("1.000000"),
        },
    )

    transactions = list_transactions(db_session)
    assert [item.trade_type for item in transactions] == ["dividend_reinvest", "opening"]
    refreshed = _position(db_session)
    assert refreshed.holding_share == Decimal("1050.0000")
    assert refreshed.holding_amount == Decimal("1050.0000")
    assert refreshed.note == AUTO_SUMMARY_NOTE


def test_overview_still_uses_market_value_and_cost_only(db_session):
    _buy(db_session, amount="100", price="1")
    create_transaction(
        db_session,
        {
            "fund_code": "000001",
            "trade_date": date(2026, 5, 2),
            "trade_type": "sell",
            "amount": Decimal("120"),
            "nav": Decimal("1.200000"),
            "share": Decimal("100"),
        },
    )
    _buy(db_session, amount="250", price="2.5", day=date(2026, 5, 3))

    overview = portfolio_overview(db_session)
    position = overview["positions"][0]["position"]
    # 盈亏口径不变：持仓成本 250；已实现另有账户口径，不进入 portfolio_overview
    assert position.holding_amount == Decimal("250.0000")
    assert position.holding_share == Decimal("100.0000")
