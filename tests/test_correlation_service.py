from datetime import date, timedelta
from decimal import Decimal

from app.db.models import FundNav, Watchlist
from app.services.correlation_service import high_correlation_pairs


def test_high_correlation_pairs_aligns_overlapping_dates(db_session):
    db_session.add_all(
        [
            Watchlist(fund_code="000001", fund_name="A", group_name="default", is_active=True),
            Watchlist(fund_code="000002", fund_name="B", group_name="default", is_active=True),
        ]
    )
    start = date.today() - timedelta(days=30)
    for i in range(25):
        db_session.add(
            FundNav(
                fund_code="000001",
                nav_date=start + timedelta(days=i),
                unit_nav=Decimal("1"),
                daily_return=Decimal(str(0.001 * i)),
                source="test",
            )
        )
        db_session.add(
            FundNav(
                fund_code="000002",
                nav_date=start + timedelta(days=i),
                unit_nav=Decimal("1"),
                daily_return=Decimal(str(0.001 * i)),
                source="test",
            )
        )
    db_session.commit()

    pairs = high_correlation_pairs(db_session)

    assert pairs
    assert pairs[0]["fund_a"] == "000001"
    assert pairs[0]["fund_b"] == "000002"
