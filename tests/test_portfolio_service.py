from datetime import date
from decimal import Decimal

from app.db.models import FundInfo, FundNav, PortfolioPosition
from app.services.portfolio_service import create_transaction, list_transactions, portfolio_overview, simulate_buy


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
