from datetime import date, timedelta

import pandas as pd

from app.services.market_service import DEFAULT_MARKET_INDEXES, upsert_market_rows, latest_market_context


def test_market_context_empty_database(db_session):
    context = latest_market_context(db_session)

    assert len(context) == len(DEFAULT_MARKET_INDEXES)
    assert context[0]["close"] is None


def test_upsert_market_rows_and_calculate_context(db_session):
    rows = pd.DataFrame(
        [
            {
                "index_code": "sh000300",
                "trade_date": date.today() - timedelta(days=30),
                "close": 100,
                "daily_return": 0.01,
                "source": "test",
            },
            {
                "index_code": "sh000300",
                "trade_date": date.today(),
                "close": 110,
                "daily_return": 0.02,
                "source": "test",
            },
        ]
    )

    assert upsert_market_rows(db_session, "沪深300", rows) == 2
    item = next(item for item in latest_market_context(db_session) if item["index_code"] == "sh000300")

    assert item["daily_return"] == 0.02
    assert round(item["return_1m"], 4) == 0.1
