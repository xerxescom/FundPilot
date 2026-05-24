from datetime import date
from decimal import Decimal

from app.db.models import FundNav, PortfolioPosition
from app.services.portfolio_service import portfolio_overview


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
