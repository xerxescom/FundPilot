from types import SimpleNamespace

from app.services import fund_analysis_service


def test_analyze_fund_skips_report_by_default(monkeypatch, db_session):
    report_called = False

    def fake_generate_report(db, fund_code):
        nonlocal report_called
        report_called = True
        return SimpleNamespace(id=1)

    monkeypatch.setattr(
        fund_analysis_service.nav_service,
        "sync_fund_nav_detailed",
        lambda db, fund_code: {
            "fund_code": fund_code.zfill(6),
            "synced_rows": 1,
            "source": "akshare",
            "attempts": [],
            "quality": {"valid": True, "issues": [], "row_count": 1, "duplicate_count": 0, "missing_daily_return_count": 0},
        },
    )
    monkeypatch.setattr(
        fund_analysis_service.indicator_service,
        "calculate_and_save_indicators",
        lambda db, fund_code: SimpleNamespace(calc_date="2026-05-25"),
    )
    monkeypatch.setattr(
        fund_analysis_service.score_service,
        "calculate_and_save_score",
        lambda db, fund_code: SimpleNamespace(total_score=80),
    )
    monkeypatch.setattr(fund_analysis_service, "generate_fund_explanation", fake_generate_report)
    monkeypatch.setattr(fund_analysis_service, "analysis_status", lambda db, fund_code: {"status": "score_ready"})

    result = fund_analysis_service.analyze_fund(db_session, "1")

    assert report_called is False
    assert result["steps"][-1]["status"] == "skipped"


def test_analyze_fund_can_generate_report(monkeypatch, db_session):
    monkeypatch.setattr(
        fund_analysis_service.nav_service,
        "sync_fund_nav_detailed",
        lambda db, fund_code: {
            "fund_code": fund_code.zfill(6),
            "synced_rows": 1,
            "source": "akshare",
            "attempts": [],
            "quality": {"valid": True, "issues": [], "row_count": 1, "duplicate_count": 0, "missing_daily_return_count": 0},
        },
    )
    monkeypatch.setattr(
        fund_analysis_service.indicator_service,
        "calculate_and_save_indicators",
        lambda db, fund_code: SimpleNamespace(calc_date="2026-05-25"),
    )
    monkeypatch.setattr(
        fund_analysis_service.score_service,
        "calculate_and_save_score",
        lambda db, fund_code: SimpleNamespace(total_score=80),
    )
    monkeypatch.setattr(
        fund_analysis_service,
        "generate_fund_explanation",
        lambda db, fund_code: SimpleNamespace(id=99),
    )
    monkeypatch.setattr(fund_analysis_service, "analysis_status", lambda db, fund_code: {"status": "complete"})

    result = fund_analysis_service.analyze_fund(db_session, "1", generate_report=True)

    assert result["steps"][-1]["status"] == "success"
    assert result["steps"][-1]["result"] == 99
