from datetime import date, timedelta
from decimal import Decimal

import pytest
from fastapi import HTTPException

from app.api.v1.portfolio import delete_transaction as delete_transaction_route
from app.db.models import AssetInfo, AssetPriceDaily, FundInfo, FundNav, PortfolioPosition
from app.services.portfolio_service import (
    AUTO_SUMMARY_NOTE,
    create_transaction,
    delete_transaction,
    list_transactions,
    portfolio_drawdown_detail,
    portfolio_overview,
    simulate_buy,
    update_position,
)


def _add_manual_position(db_session, **overrides):
    values = {
        "fund_code": "000001",
        "holding_amount": Decimal("1000"),
        "holding_share": Decimal("1000"),
        "cost_nav": Decimal("1.000000"),
    }
    values.update(overrides)
    position = PortfolioPosition(**values)
    db_session.add(position)
    db_session.commit()
    return position


def test_portfolio_overview_calculates_profit(db_session):
    db_session.add(
        FundNav(
            fund_code="000001",
            nav_date=date.today(),
            unit_nav=Decimal("1.200000"),
            accumulated_nav=Decimal("1.200000"),
            daily_return=Decimal("0.010000"),
            source="test",
        )
    )
    db_session.add(
        PortfolioPosition(
            fund_code="000001",
            holding_amount=Decimal("1000"),
            holding_share=Decimal("1000"),
            cost_nav=Decimal("1.000000"),
        )
    )
    db_session.commit()

    overview = portfolio_overview(db_session)

    assert overview["total_value"] == Decimal("1200.0000000000")
    assert overview["profit_amount"] == Decimal("200.0000000000")
    assert overview["profit_rate"] == Decimal("0.2000000000")


def test_transactions_rebuild_position_cost(db_session):
    create_transaction(
        db_session,
        {
            "fund_code": "1",
            "trade_date": date(2026, 5, 1),
            "amount": Decimal("1000"),
            "nav": Decimal("1.0000"),
        },
    )
    create_transaction(
        db_session,
        {
            "fund_code": "1",
            "trade_date": date(2026, 5, 2),
            "amount": Decimal("1200"),
            "nav": Decimal("1.2000"),
        },
    )

    transactions = list_transactions(db_session, "000001")
    overview = portfolio_overview(db_session)
    position = overview["positions"][0]["position"]

    assert len(transactions) == 2
    assert position.fund_code == "000001"
    assert position.holding_amount == Decimal("2200.0000")
    assert position.holding_share == Decimal("2000.0000")
    assert position.cost_nav == Decimal("1.100000")


def test_simulate_buy_reports_concentration_and_correlation(db_session):
    db_session.add_all(
        [
            FundInfo(fund_code="000001", fund_name="已有基金", fund_type="指数", source="test"),
            FundInfo(fund_code="000002", fund_name="目标基金", fund_type="指数", source="test"),
            PortfolioPosition(
                fund_code="000001",
                holding_amount=Decimal("1000"),
                holding_share=Decimal("1000"),
                cost_nav=Decimal("1.000000"),
            ),
        ]
    )
    for day in range(1, 8):
        daily_return = Decimal("0.010000") if day % 2 else Decimal("-0.005000")
        db_session.add_all(
            [
                FundNav(
                    fund_code="000001",
                    nav_date=date(2026, 1, day),
                    unit_nav=Decimal("1.000000"),
                    daily_return=daily_return,
                ),
                FundNav(
                    fund_code="000002",
                    nav_date=date(2026, 1, day),
                    unit_nav=Decimal("1.000000"),
                    daily_return=daily_return,
                ),
            ]
        )
    db_session.commit()

    payload = simulate_buy(db_session, "000002", Decimal("1000"))

    assert payload["target_weight_after"] == Decimal("0.5")
    assert payload["max_weight_after"] == Decimal("0.5")
    assert payload["max_correlation"] == Decimal("1.0000")
    assert payload["high_correlation_positions"][0]["fund_code"] == "000001"
    assert any(item["title"] == "与现有持仓相关性偏高" for item in payload["risk_items"])


def test_portfolio_overview_missing_price_is_incomplete_not_loss(db_session):
    _add_manual_position(db_session)

    overview = portfolio_overview(db_session)

    assert overview["total_value"] is None
    assert overview["profit_amount"] is None
    assert overview["profit_rate"] is None
    assert overview["is_complete"] is False
    assert overview["valuation_status"] == "partial"
    assert overview["known_value"] == Decimal("0")
    assert overview["priced_position_count"] == 0
    assert overview["total_cost"] == Decimal("1000")
    assert overview["max_weight"] is None
    assert overview["as_of"] == date.today()
    assert overview["missing_price_assets"] == [
        {"asset_type": "fund", "asset_code": "000001", "asset_name": None, "reason": "缺少最新净值"}
    ]
    assert overview["positions"][0]["missing_reason"] == "缺少最新净值"
    assert overview["positions"][0]["current_value"] is None


def test_portfolio_overview_complete_reports_price_date_and_status(db_session):
    _add_manual_position(db_session)
    db_session.add(
        FundNav(
            fund_code="000001",
            nav_date=date(2026, 5, 20),
            unit_nav=Decimal("1.200000"),
            source="eastmoney",
        )
    )
    db_session.commit()

    overview = portfolio_overview(db_session)

    assert overview["is_complete"] is True
    assert overview["valuation_status"] == "complete"
    assert overview["total_value"] == Decimal("1200.000000")
    assert overview["known_value"] == Decimal("1200.000000")
    assert overview["profit_amount"] == Decimal("200.000000")
    assert overview["price_as_of"] == date(2026, 5, 20)
    assert overview["positions"][0]["price_date"] == date(2026, 5, 20)
    assert overview["positions"][0]["price_source"] == "eastmoney"
    assert overview["positions"][0]["missing_reason"] is None
    assert overview["missing_price_assets"] == []


def test_zero_share_position_is_complete_with_zero_value(db_session):
    _add_manual_position(
        db_session,
        holding_amount=Decimal("0"),
        holding_share=Decimal("0"),
        cost_nav=None,
    )

    overview = portfolio_overview(db_session)

    assert overview["is_complete"] is True
    assert overview["total_value"] == Decimal("0")
    assert overview["missing_price_assets"] == []
    assert overview["positions"][0]["current_value"] == Decimal("0")
    assert overview["positions"][0]["missing_reason"] is None


def test_missing_cost_marks_profit_unknown_but_keeps_value(db_session):
    _add_manual_position(db_session, holding_amount=None, cost_nav=None)
    db_session.add(
        FundNav(fund_code="000001", nav_date=date(2026, 5, 20), unit_nav=Decimal("1.200000"))
    )
    db_session.commit()

    overview = portfolio_overview(db_session)

    assert overview["is_complete"] is True
    assert overview["total_value"] == Decimal("1200.000000")
    assert overview["profit_amount"] is None
    assert overview["profit_rate"] is None
    assert overview["missing_cost_assets"] == [
        {"asset_type": "fund", "asset_code": "000001", "asset_name": None, "reason": "缺少成本信息"}
    ]
    assert overview["positions"][0]["profit_amount"] is None


def test_manual_position_plus_buy_rebuilds_to_1100(db_session):
    _add_manual_position(
        db_session,
        buy_date=date(2026, 1, 1),
        note="由中信证券持仓截图导入（2026-01-01）",
    )

    create_transaction(
        db_session,
        {
            "fund_code": "000001",
            "trade_date": date(2026, 5, 1),
            "trade_type": "buy",
            "amount": Decimal("100"),
            "nav": Decimal("1.000000"),
        },
    )

    transactions = list_transactions(db_session)
    assert len(transactions) == 2
    openings = [item for item in transactions if item.trade_type == "opening"]
    assert len(openings) == 1
    assert openings[0].trade_date == date(2026, 1, 1)
    assert openings[0].share == Decimal("1000.0000")
    assert openings[0].nav == Decimal("1.000000")
    assert openings[0].amount == Decimal("1000.0000")
    assert "期初持仓" in openings[0].note
    assert "由中信证券持仓截图导入" in openings[0].note

    position = portfolio_overview(db_session)["positions"][0]["position"]
    assert position.holding_share == Decimal("1100.0000")
    assert position.holding_amount == Decimal("1100.0000")
    assert position.cost_nav == Decimal("1.000000")
    assert position.note == AUTO_SUMMARY_NOTE

    create_transaction(
        db_session,
        {
            "fund_code": "000001",
            "trade_date": date(2026, 6, 1),
            "trade_type": "buy",
            "amount": Decimal("100"),
            "nav": Decimal("1.000000"),
        },
    )
    position = portfolio_overview(db_session)["positions"][0]["position"]
    assert position.holding_share == Decimal("1200.0000")
    assert position.holding_amount == Decimal("1200.0000")
    assert len(list_transactions(db_session)) == 3


def test_explicit_opening_is_accepted_and_not_duplicated(db_session):
    create_transaction(
        db_session,
        {
            "fund_code": "000002",
            "trade_date": date(2026, 1, 1),
            "trade_type": "opening",
            "amount": Decimal("1000"),
            "nav": Decimal("1.000000"),
        },
    )
    position = portfolio_overview(db_session)["positions"][0]["position"]
    assert position.holding_share == Decimal("1000.0000")

    with pytest.raises(ValueError, match="已存在期初持仓记录"):
        create_transaction(
            db_session,
            {
                "fund_code": "000002",
                "trade_date": date(2026, 1, 2),
                "trade_type": "opening",
                "amount": Decimal("500"),
                "nav": Decimal("1.000000"),
            },
        )

    _add_manual_position(db_session, fund_code="000003")
    with pytest.raises(ValueError, match="已有手工或截图持仓"):
        create_transaction(
            db_session,
            {
                "fund_code": "000003",
                "trade_date": date(2026, 1, 2),
                "trade_type": "opening",
                "amount": Decimal("500"),
                "nav": Decimal("1.000000"),
            },
        )


def test_manual_position_without_cost_rejects_trade_instead_of_wiping(db_session):
    _add_manual_position(db_session, holding_amount=None, cost_nav=None)

    with pytest.raises(ValueError, match="缺少成本信息"):
        create_transaction(
            db_session,
            {
                "fund_code": "000001",
                "trade_date": date(2026, 5, 1),
                "trade_type": "buy",
                "amount": Decimal("100"),
                "nav": Decimal("1.000000"),
            },
        )

    assert list_transactions(db_session) == []
    position = portfolio_overview(db_session)["positions"][0]["position"]
    assert position.holding_share == Decimal("1000.0000")


def test_backdated_sell_rolls_back_transaction(db_session):
    create_transaction(
        db_session,
        {
            "fund_code": "000004",
            "trade_date": date(2026, 5, 10),
            "trade_type": "buy",
            "amount": Decimal("100"),
            "nav": Decimal("1.000000"),
        },
    )

    with pytest.raises(ValueError, match="可用持仓") as excinfo:
        create_transaction(
            db_session,
            {
                "fund_code": "000004",
                "trade_date": date(2026, 5, 1),
                "trade_type": "sell",
                "amount": Decimal("50"),
                "nav": Decimal("1.000000"),
            },
        )
    assert "2026-05-01" in str(excinfo.value)

    assert len(list_transactions(db_session)) == 1
    position = portfolio_overview(db_session)["positions"][0]["position"]
    assert position.holding_share == Decimal("100.0000")


def test_delete_transaction_rolls_back_when_rebuild_fails(db_session):
    create_transaction(
        db_session,
        {
            "fund_code": "000005",
            "trade_date": date(2026, 5, 10),
            "trade_type": "buy",
            "amount": Decimal("100"),
            "nav": Decimal("1.000000"),
        },
    )
    buy_id = list_transactions(db_session)[0].id
    create_transaction(
        db_session,
        {
            "fund_code": "000005",
            "trade_date": date(2026, 5, 11),
            "trade_type": "sell",
            "amount": Decimal("40"),
            "nav": Decimal("1.000000"),
        },
    )

    with pytest.raises(ValueError, match="可用持仓"):
        delete_transaction(db_session, buy_id)

    assert len(list_transactions(db_session)) == 2
    position = portfolio_overview(db_session)["positions"][0]["position"]
    assert position.holding_share == Decimal("60.0000")


def test_delete_transaction_endpoint_returns_400_on_replay_failure(db_session):
    create_transaction(
        db_session,
        {
            "fund_code": "000006",
            "trade_date": date(2026, 5, 10),
            "trade_type": "buy",
            "amount": Decimal("100"),
            "nav": Decimal("1.000000"),
        },
    )
    buy_id = list_transactions(db_session)[0].id
    create_transaction(
        db_session,
        {
            "fund_code": "000006",
            "trade_date": date(2026, 5, 11),
            "trade_type": "sell",
            "amount": Decimal("40"),
            "nav": Decimal("1.000000"),
        },
    )

    with pytest.raises(HTTPException) as excinfo:
        delete_transaction_route(buy_id, db_session)

    assert excinfo.value.status_code == 400
    assert len(list_transactions(db_session)) == 2


def test_update_position_rejects_ledger_managed_fields(db_session):
    create_transaction(
        db_session,
        {
            "fund_code": "000007",
            "trade_date": date(2026, 5, 10),
            "trade_type": "buy",
            "amount": Decimal("100"),
            "nav": Decimal("1.000000"),
        },
    )
    position = portfolio_overview(db_session)["positions"][0]["position"]

    with pytest.raises(ValueError, match="交易流水管理"):
        update_position(db_session, position.id, {"holding_share": Decimal("5")})

    updated = update_position(db_session, position.id, {"note": "我的备注"})
    assert updated.note == "我的备注"
    assert updated.holding_share == Decimal("100.0000")


def test_drawdown_aligns_common_dates_without_fake_drop(db_session):
    db_session.add_all(
        [
            PortfolioPosition(
                fund_code="000001", holding_share=Decimal("10"), holding_amount=Decimal("1000"), cost_nav=Decimal("100")
            ),
            PortfolioPosition(
                fund_code="000002", holding_share=Decimal("10"), holding_amount=Decimal("1000"), cost_nav=Decimal("100")
            ),
        ]
    )
    start = date(2026, 4, 1)
    for offset in range(40):
        day = start + timedelta(days=offset)
        db_session.add(FundNav(fund_code="000001", nav_date=day, unit_nav=Decimal("100")))
        if offset < 5 or offset >= 35:
            db_session.add(FundNav(fund_code="000002", nav_date=day, unit_nav=Decimal("100")))
    db_session.commit()

    detail = portfolio_drawdown_detail(db_session)

    assert detail["drawdown_1m"] == Decimal("0.000000")
    assert detail["basis"]["aligned_days"] == 10
    assert detail["basis"]["included_asset_count"] == 2
    assert detail["basis"]["excluded_asset_codes"] == []
    assert detail["basis"]["label"] == "当前持仓历史模拟"


def test_drawdown_reports_insufficient_and_excluded_assets(db_session):
    db_session.add_all(
        [
            PortfolioPosition(
                fund_code="000001", holding_share=Decimal("10"), holding_amount=Decimal("1000"), cost_nav=Decimal("100")
            ),
            PortfolioPosition(
                fund_code="000002", holding_share=Decimal("10"), holding_amount=Decimal("1000"), cost_nav=Decimal("100")
            ),
        ]
    )
    db_session.add(FundNav(fund_code="000001", nav_date=date(2026, 4, 1), unit_nav=Decimal("100")))
    db_session.commit()

    detail = portfolio_drawdown_detail(db_session)

    assert detail["drawdown_1m"] is None
    assert detail["basis"]["aligned_days"] == 1
    assert detail["basis"]["included_asset_count"] == 1
    assert detail["basis"]["excluded_asset_codes"] == ["000002"]


def test_stock_position_reports_price_date_and_source(db_session):
    db_session.add(
        AssetInfo(asset_code="600519", asset_type="stock", asset_name="贵州茅台", source="manual")
    )
    db_session.add(
        AssetPriceDaily(
            asset_code="600519",
            price_date=date(2026, 5, 20),
            close=Decimal("10"),
            source="akshare",
        )
    )
    db_session.add(
        PortfolioPosition(
            fund_code="600519",
            asset_type="stock",
            asset_code="600519",
            holding_share=Decimal("100"),
            holding_amount=Decimal("900"),
            cost_nav=Decimal("9"),
        )
    )
    db_session.commit()

    overview = portfolio_overview(db_session)

    assert overview["is_complete"] is True
    assert overview["total_value"] == Decimal("1000.000000")
    assert overview["positions"][0]["asset_name"] == "贵州茅台"
    assert overview["positions"][0]["price_date"] == date(2026, 5, 20)
    assert overview["positions"][0]["price_source"] == "akshare"


def test_drawdown_ignores_missing_and_zero_share_positions(db_session):
    db_session.add(
        PortfolioPosition(
            fund_code="000009", holding_share=Decimal("0"), holding_amount=Decimal("0"), cost_nav=None
        )
    )
    db_session.add(FundNav(fund_code="000009", nav_date=date(2026, 4, 1), unit_nav=Decimal("1")))
    db_session.add(FundNav(fund_code="000009", nav_date=date(2026, 4, 2), unit_nav=Decimal("2")))
    db_session.commit()

    detail = portfolio_drawdown_detail(db_session)

    assert detail["drawdown_1m"] is None
    assert detail["basis"]["included_asset_count"] == 0
    assert detail["basis"]["excluded_asset_codes"] == []
