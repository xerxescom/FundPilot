from datetime import date
from decimal import Decimal

from app.db.models import AssetInfo, AssetPriceDaily
from app.services.portfolio_service import create_transaction, portfolio_overview


def test_stock_transaction_uses_latest_stock_price(db_session):
    db_session.add(
        AssetInfo(
            asset_code="600519",
            asset_type="stock",
            asset_name="贵州茅台",
            market="SH",
            currency="CNY",
            source="test",
        )
    )
    db_session.add(
        AssetPriceDaily(
            asset_code="600519",
            price_date=date.today(),
            close=Decimal("1600"),
            daily_return=Decimal("0.01"),
            source="test",
        )
    )
    db_session.commit()

    create_transaction(
        db_session,
        {
            "asset_type": "stock",
            "asset_code": "600519",
            "trade_date": date.today(),
            "trade_type": "buy",
            "amount": Decimal("15000"),
            "nav": Decimal("1500"),
            "share": Decimal("10"),
        },
    )

    overview = portfolio_overview(db_session)
    summary = overview["positions"][0]

    assert summary["asset_type"] == "stock"
    assert summary["asset_name"] == "贵州茅台"
    assert summary["latest_price"] == Decimal("1600")
    assert summary["current_value"] == Decimal("16000")
    assert summary["profit_amount"] == Decimal("1000")


def test_stock_sell_rebuilds_remaining_cost(db_session):
    create_transaction(
        db_session,
        {
            "asset_type": "stock",
            "asset_code": "600519",
            "trade_date": date(2026, 8, 1),
            "amount": Decimal("15000"),
            "nav": Decimal("1500"),
            "share": Decimal("10"),
        },
    )
    create_transaction(
        db_session,
        {
            "asset_type": "stock",
            "asset_code": "600519",
            "trade_date": date(2026, 8, 2),
            "trade_type": "sell",
            "amount": Decimal("3200"),
            "nav": Decimal("1600"),
            "share": Decimal("2"),
        },
    )

    position = portfolio_overview(db_session)["positions"][0]["position"]

    assert position.holding_share == Decimal("8.0000")
    assert position.holding_amount == Decimal("12000.0000")
