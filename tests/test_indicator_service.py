from datetime import date, timedelta

import pandas as pd
import pytest

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


def test_calculate_indicators_ignores_future_rows():
    rows = [
        {"nav_date": date(2026, 1, 1), "unit_nav": 1.0},
        {"nav_date": date(2026, 2, 1), "unit_nav": 1.1},
    ]
    future_rows = rows + [{"nav_date": date(2026, 3, 1), "unit_nav": 0.55}]

    historical = calculate_indicators_from_nav(pd.DataFrame(rows), calc_date=date(2026, 2, 1))
    with_future = calculate_indicators_from_nav(pd.DataFrame(future_rows), calc_date=date(2026, 2, 1))

    assert historical == with_future
    assert historical["calc_date"] == date(2026, 2, 1)
    assert historical["return_1m"] == pytest.approx(0.1)
    assert historical["max_drawdown_1y"] == 0
    assert historical["volatility_1y"] is None


def test_calculate_indicators_rejects_calc_date_before_history():
    rows = [
        {"nav_date": date(2026, 1, 1), "unit_nav": 1.0},
        {"nav_date": date(2026, 2, 1), "unit_nav": 1.1},
    ]

    with pytest.raises(ValueError, match="计算日期之前"):
        calculate_indicators_from_nav(pd.DataFrame(rows), calc_date=date(2025, 12, 1))
