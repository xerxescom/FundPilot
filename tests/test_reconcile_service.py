from datetime import date

import pandas as pd

from app.services import reconcile_service


class FakeSource:
    def get_fund_nav_history(self, fund_code):
        return pd.DataFrame(
            [
                {
                    "fund_code": fund_code,
                    "nav_date": date(2026, 5, 20),
                    "unit_nav": 1.0,
                    "daily_return": 0.01,
                    "source": "fake",
                }
            ]
        )


class FakeDifferentSource:
    def get_fund_nav_history(self, fund_code):
        return pd.DataFrame(
            [
                {
                    "fund_code": fund_code,
                    "nav_date": date(2026, 5, 20),
                    "unit_nav": 1.1,
                    "daily_return": 0.02,
                    "source": "fake",
                }
            ]
        )


def test_reconcile_fund_nav_detects_value_diff(monkeypatch):
    monkeypatch.setattr(reconcile_service, "AkshareFundDataSource", lambda: FakeSource())
    monkeypatch.setattr(reconcile_service, "EastmoneyFundDataSource", lambda: FakeDifferentSource())

    result = reconcile_service.reconcile_fund_nav("1")

    assert result["fund_code"] == "000001"
    assert result["status"] == "warning"
    assert result["counts"]["unit_nav_diff"] == 1
    assert result["rows"][0]["status"] == "单位净值差异"
