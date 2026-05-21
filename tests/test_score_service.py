from datetime import date
from decimal import Decimal

from app.db.models import FundIndicator
from app.services.score_service import score_indicator


def test_score_indicator_high_quality():
    indicator = FundIndicator(
        fund_code="000001",
        calc_date=date.today(),
        return_1y=Decimal("0.25"),
        max_drawdown_1y=Decimal("-0.05"),
        volatility_1y=Decimal("0.10"),
        win_rate_1y=Decimal("0.60"),
    )

    result = score_indicator(indicator)

    assert result["total_score"] >= 85
    assert result["rating"] == "重点关注"
    assert result["reason"]


def test_score_indicator_missing_data_degrades():
    indicator = FundIndicator(fund_code="000001", calc_date=date.today())

    result = score_indicator(indicator)

    assert result["total_score"] < 60
    assert result["rating"] == "暂不关注"
    assert "数据不足" in result["reason"]
