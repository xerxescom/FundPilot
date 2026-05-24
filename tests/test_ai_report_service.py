from datetime import date
from decimal import Decimal

from app.db.models import FundScore, Watchlist
from app.services.ai import report_service
from app.services.ai.report_service import _sanitize, collect_daily_report_data


def test_sanitize_removes_forbidden_terms():
    content = "这只基金可以立即买入，并且保证收益。"

    cleaned = _sanitize(content)

    assert "立即买入" not in cleaned
    assert "保证收益" not in cleaned


def test_daily_report_data_includes_fund_name(db_session):
    db_session.add(Watchlist(fund_code="000001", fund_name="测试基金", is_active=True))
    db_session.add(
        FundScore(
            fund_code="000001",
            score_date=date.today(),
            total_score=Decimal("80"),
            rating="可以观察",
        )
    )
    db_session.commit()

    data = collect_daily_report_data(db_session)

    assert data["top_scores"][0]["fund_code"] == "000001"
    assert data["top_scores"][0]["fund_name"] == "测试基金"


def test_daily_report_fallback_records_metadata(monkeypatch, db_session):
    def fake_generate(self, prompt):
        return "建议立即买入并保证收益"

    monkeypatch.setattr(report_service.OllamaClient, "generate", fake_generate)

    report = report_service.generate_daily_report(db_session)

    assert report.model_name == "rule-fallback"
    assert report.is_fallback is True
    assert report.fallback_reason
    assert "立即买入" not in report.content
    assert report.input_snapshot
