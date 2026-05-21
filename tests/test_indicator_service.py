from datetime import date, timedelta

import pandas as pd

from app.services.indicator_service import calculate_indicators_from_nav


def test_calculate_indicators_from_nav_with_full_data():
    start = date(2024, 1, 1)
    rows = [
        {"nav_date": start + timedelta(days=i), "unit_nav": 1 + i * 0.001}
        for i in range(400)
    ]

    result = calculate_indicators_from_nav(pd.DataFrame(rows))

    assert result["return_1m"] is not None
    assert result["return_1y"] is not None
    assert result["max_drawdown_1y"] <= 0
    assert result["volatility_1y"] is not None
    assert result["win_rate_1y"] == 1


def test_calculate_indicators_allows_short_history():
    rows = [
        {"nav_date": date(2025, 1, 1), "unit_nav": 1.0},
        {"nav_date": date(2025, 1, 2), "unit_nav": 1.1},
    ]

    result = calculate_indicators_from_nav(pd.DataFrame(rows))

    assert result["return_1w"] is None
    assert result["max_drawdown_1y"] == 0
    assert result["win_rate_1y"] == 1
