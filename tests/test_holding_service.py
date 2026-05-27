from datetime import date

import pandas as pd

from app.services.holding_service import (
    latest_holding_industries,
    latest_holding_stocks,
    upsert_fund_holding_industry_rows,
    upsert_fund_holding_stock_rows,
)


def test_upsert_fund_holding_industry_rows(db_session):
    rows = pd.DataFrame(
        [
            {
                "fund_code": "000001",
                "report_date": date(2026, 3, 31),
                "industry": "科技",
                "weight": 0.45,
                "source": "test",
            },
            {
                "fund_code": "000001",
                "report_date": date(2026, 3, 31),
                "industry": "消费",
                "weight": 0.25,
                "source": "test",
            },
        ]
    )

    assert upsert_fund_holding_industry_rows(db_session, "000001", rows) == 2
    holdings = latest_holding_industries(db_session, "000001")

    assert [item.industry for item in holdings] == ["科技", "消费"]
    assert float(holdings[0].weight) == 0.45


def test_upsert_fund_holding_stock_rows(db_session):
    rows = pd.DataFrame(
        [
            {
                "fund_code": "000001",
                "report_date": date(2026, 3, 31),
                "stock_code": "600519",
                "stock_name": "贵州茅台",
                "industry": "消费",
                "weight": 0.08,
                "source": "test",
            },
            {
                "fund_code": "000001",
                "report_date": date(2026, 3, 31),
                "stock_code": "300750",
                "stock_name": "宁德时代",
                "industry": "新能源",
                "weight": 0.06,
                "source": "test",
            },
        ]
    )

    assert upsert_fund_holding_stock_rows(db_session, "000001", rows) == 2
    holdings = latest_holding_stocks(db_session, "000001")

    assert [item.stock_code for item in holdings] == ["600519", "300750"]
    assert holdings[0].stock_name == "贵州茅台"
    assert float(holdings[0].weight) == 0.08
