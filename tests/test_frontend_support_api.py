from datetime import date
from decimal import Decimal

from app.api.v1.correlation import correlation_matrix, fund_return_series
from app.api.v1.dashboard import dashboard_overview
from app.api.v1.report import ollama_status
from app.api.v1.research import industry_overview, risk_return_points
from app.db.models import FundIndicator, FundNav, FundScore, Watchlist
from app.services.ai.ollama_client import OllamaClient


def test_dashboard_overview_api_contract(db_session):
    db_session.add(Watchlist(fund_code="000001", fund_name="测试基金", is_active=True))
    db_session.add(
        FundScore(
            fund_code="000001",
            score_date=date(2026, 5, 24),
            total_score=Decimal("88"),
            rating="重点关注",
            reason="近1年收益表现突出",
        )
    )
    db_session.commit()

    payload = dashboard_overview(db_session)

    assert payload["watchlist_count"] == 1
    assert payload["top_scores"][0]["fund_name"] == "测试基金"
    assert "data_health" in payload


def test_research_support_api_contracts(db_session):
    db_session.add(Watchlist(fund_code="000001", fund_name="测试基金", industry="宽基", is_active=True))
    db_session.add(
        FundIndicator(
            fund_code="000001",
            calc_date=date(2026, 5, 24),
            return_1y=Decimal("0.12"),
            volatility_1y=Decimal("0.18"),
        )
    )
    db_session.commit()

    industry = industry_overview(db_session)
    risk_return = risk_return_points(db_session)

    assert industry[0]["industry"] == "宽基"
    assert risk_return[0]["fund_code"] == "000001"


def test_correlation_support_api_contracts(db_session):
    db_session.add_all(
        [
            Watchlist(fund_code="000001", is_active=True),
            Watchlist(fund_code="000002", is_active=True),
            FundNav(fund_code="000001", nav_date=date(2026, 1, 1), daily_return=Decimal("0.01")),
            FundNav(fund_code="000001", nav_date=date(2026, 1, 2), daily_return=Decimal("0.02")),
            FundNav(fund_code="000002", nav_date=date(2026, 1, 1), daily_return=Decimal("0.01")),
            FundNav(fund_code="000002", nav_date=date(2026, 1, 2), daily_return=Decimal("0.02")),
        ]
    )
    db_session.commit()

    matrix = correlation_matrix(db_session)
    returns = fund_return_series("000001", "000002", db=db_session)

    assert "000001" in matrix
    assert len(returns) == 2


def test_ollama_status_api_contract(monkeypatch):
    def fake_status(self):
        return {
            "base_url": "http://localhost:11434",
            "configured_model": "qwen3:14b",
            "timeout_seconds": 180,
            "available_models": ["qwen3:14b"],
            "model_available": True,
        }

    monkeypatch.setattr(OllamaClient, "check_model_available", fake_status)

    assert ollama_status()["model_available"] is True
