from datetime import date

import pandas as pd

from app.services import nav_service


class FailingSource:
    source_name = "failing"

    def get_fund_nav_history(self, fund_code):
        raise ValueError("temporary failure")


class ValidSource:
    source_name = "valid"

    def get_fund_nav_history(self, fund_code):
        return pd.DataFrame(
            [
                {
                    "fund_code": fund_code,
                    "nav_date": date(2026, 5, 20),
                    "unit_nav": 1.0,
                    "daily_return": 0.01,
                    "source": self.source_name,
                }
            ]
        )


def test_fetch_nav_with_fallback_records_attempts(monkeypatch):
    monkeypatch.setattr(nav_service, "_data_sources", lambda: [FailingSource(), ValidSource()])

    rows, diagnostics = nav_service.fetch_nav_with_fallback("1")

    assert len(rows) == 1
    assert diagnostics["source"] == "valid"
    assert diagnostics["attempts"][0]["status"] == "failed"
    assert diagnostics["attempts"][-1]["status"] == "success"


def test_validate_nav_rows_reports_quality_issues():
    rows = pd.DataFrame(
        [
            {"fund_code": "000001", "nav_date": date(2026, 5, 20), "unit_nav": 1.0},
            {"fund_code": "000001", "nav_date": date(2026, 5, 20), "unit_nav": 1.0},
        ]
    )

    quality = nav_service.validate_nav_rows(rows, "000001")

    assert quality["valid"] is True
    assert quality["duplicate_count"] == 1
    assert "缺少日涨跌幅" in "；".join(quality["issues"])
