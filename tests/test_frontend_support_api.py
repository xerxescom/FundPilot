from datetime import date
from decimal import Decimal

from app.api.v1.alert import update_alert
from app.api.v1.correlation import correlation_matrix, fund_return_series
from app.api.v1.dashboard import dashboard_overview, dashboard_today
from app.api.v1 import fund as fund_api
from app.api.v1.fund import get_analysis_status, get_holding_stocks
from app.api.v1.portfolio import portfolio_diagnosis, simulate_buy
from app.api.v1.report import latest_fund_report, ollama_status
from app.api.v1.score import score_signal_summary, score_strategies, top_scores_by_strategy
from app.api.v1.research import industry_overview, risk_return_points
from app.db.models import AlertEvent, FundHoldingStock, FundIndicator, FundInfo, FundNav, FundScore, PortfolioPosition, Watchlist
from app.schemas.alert import AlertUpdate
from app.schemas.portfolio import PortfolioBuySimulationIn
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

    assert "000001" in matrix["matrix"]
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


def test_latest_fund_report_empty_contract(db_session):
    assert latest_fund_report("000001", db_session) is None


def test_dashboard_today_api_contract(db_session):
    db_session.add(Watchlist(fund_code="000001", fund_name="测试基金", is_active=True))
    db_session.add(FundNav(fund_code="000001", nav_date=date(2026, 5, 24), unit_nav=Decimal("1.0")))
    db_session.add(FundIndicator(fund_code="000001", calc_date=date(2026, 5, 24)))
    db_session.add(AlertEvent(alert_type="drawdown", fund_code="000001", title="回撤提醒", is_read=False))
    db_session.commit()

    payload = dashboard_today(db_session)

    assert payload["watchlist_count"] == 1
    assert payload["todos"]
    assert any(item["key"] == "score" for item in payload["todos"])
    assert payload["unread_alerts"][0]["title"] == "回撤提醒"
    assert "portfolio_diagnosis" in payload
    assert "score_summary" in payload
    assert "pe_percentile" in payload["market_context"][0]


def test_analysis_status_api_contract(db_session):
    db_session.add(Watchlist(fund_code="000001", fund_name="测试基金", is_active=True))
    db_session.add(FundNav(fund_code="000001", nav_date=date(2026, 5, 24), unit_nav=Decimal("1.0")))
    db_session.add(FundIndicator(fund_code="000001", calc_date=date(2026, 5, 24)))
    db_session.add(FundScore(fund_code="000001", score_date=date(2026, 5, 24), total_score=Decimal("80"), rating="稳健观察"))
    db_session.commit()

    payload = get_analysis_status("000001", db_session)

    assert payload["status"] == "score_ready"
    assert payload["steps"][0]["done"] is True
    assert payload["rating"] == "稳健观察"


def test_holding_stocks_api_contract(db_session):
    db_session.add(
        FundHoldingStock(
            fund_code="000001",
            report_date=date(2026, 3, 31),
            stock_code="600519",
            stock_name="贵州茅台",
            weight=Decimal("0.08"),
            source="test",
        )
    )
    db_session.commit()

    rows = get_holding_stocks("000001", db_session)

    assert rows[0].stock_code == "600519"
    assert rows[0].stock_name == "贵州茅台"


def test_sync_nav_api_returns_diagnostics(monkeypatch, db_session):
    def fake_sync_fund_nav_detailed(db, fund_code):
        assert db is db_session
        return {
            "fund_code": fund_code.zfill(6),
            "synced_rows": 3,
            "source": "akshare",
            "attempts": [{"source": "akshare", "attempt": 1, "status": "success", "row_count": 3, "issues": []}],
            "quality": {"valid": True, "issues": [], "row_count": 3, "duplicate_count": 0, "missing_daily_return_count": 0},
        }

    monkeypatch.setattr(fund_api.nav_service, "sync_fund_nav_detailed", fake_sync_fund_nav_detailed)

    payload = fund_api.sync_nav("1", db_session)

    assert payload["fund_code"] == "000001"
    assert payload["source"] == "akshare"
    assert payload["quality"]["valid"] is True


def test_portfolio_diagnosis_api_contract(db_session):
    db_session.add(
        PortfolioPosition(
            fund_code="000001",
            holding_amount=Decimal("1000"),
            holding_share=Decimal("1000"),
            cost_nav=Decimal("1"),
        )
    )
    db_session.commit()

    payload = portfolio_diagnosis(db_session)

    assert payload["summary"]["position_count"] == 1
    assert payload["risk_items"]
    assert "不构成买入或卖出建议" in payload["observation"]


def test_portfolio_buy_simulation_api_contract(db_session):
    db_session.add(FundInfo(fund_code="000001", fund_name="目标基金", fund_type="指数", source="test"))
    db_session.commit()

    payload = simulate_buy(PortfolioBuySimulationIn(fund_code="000001", amount=Decimal("1000")), db_session)

    assert payload["fund_code"] == "000001"
    assert "target_weight_after" in payload
    assert "high_correlation_positions" in payload
    assert "不构成买入或卖出建议" in payload["observation"]


def test_alert_status_update_api_contract(db_session):
    alert = AlertEvent(alert_type="score_drop", fund_code="000001", title="评分下降", is_read=False)
    db_session.add(alert)
    db_session.commit()

    updated = update_alert(alert.id, AlertUpdate(status="handled"), db_session)

    assert updated.status == "handled"
    assert updated.is_read is True


def test_score_strategy_api_contract(db_session):
    db_session.add(
        FundIndicator(
            fund_code="000001",
            calc_date=date(2026, 5, 24),
            return_1y=Decimal("0.20"),
            max_drawdown_1y=Decimal("-0.08"),
            volatility_1y=Decimal("0.12"),
            win_rate_1y=Decimal("0.56"),
        )
    )
    db_session.commit()

    strategies = score_strategies()
    rows = top_scores_by_strategy("steady", limit=100, db=db_session)

    assert strategies[0]["name"] == "默认策略"
    assert rows[0]["strategy_name"] == "稳健型"
    assert "confidence_score" in rows[0]
    assert "buy_window_signal" in rows[0]
    assert "risk_flags" in rows[0]
    assert "risk_flag_labels" in rows[0]
    assert "market_pe_percentile" in rows[0]
    assert "valuation_index_name" in rows[0]
    assert "industry_exposure_source" in rows[0]
    assert "market_fit_level" in rows[0]
    assert "market_fit_reason" in rows[0]
    assert "peer_group" in rows[0]
    assert "peer_metric_percentiles" in rows[0]
    assert "peer_reason" in rows[0]


def test_score_summary_api_contract(db_session):
    db_session.add(
        FundIndicator(
            fund_code="000001",
            calc_date=date.today(),
            return_1m=Decimal("0.02"),
            return_3m=Decimal("0.05"),
            return_6m=Decimal("0.12"),
            return_1y=Decimal("0.20"),
            max_drawdown_1y=Decimal("-0.08"),
            volatility_1y=Decimal("0.12"),
            sharpe_1y=Decimal("1.2"),
            win_rate_1y=Decimal("0.56"),
        )
    )
    db_session.add(FundScore(fund_code="000001", score_date=date.today(), total_score=Decimal("85"), rating="重点关注"))
    db_session.commit()

    payload = score_signal_summary(db_session)

    assert payload["total_scored"] == 1
    assert "signal_counts" in payload
    assert "confidence_counts" in payload
    assert "top_risks" in payload


def test_cash_event_and_account_api_contract(db_session):
    from app.api.v1.portfolio import (
        account_performance,
        account_summary,
        create_cash_event,
        delete_cash_event,
        list_cash_events,
    )
    from app.schemas.portfolio import CashEventCreateIn

    created = create_cash_event(
        CashEventCreateIn(event_date=date(2026, 1, 1), event_type="deposit", amount=Decimal("1000")),
        db_session,
    )
    assert created["event_type_label"] == "入金"
    assert created["amount"] == Decimal("1000.0000")
    assert created["source"] == "manual"

    events = list_cash_events(None, None, 500, db_session)
    assert len(events) == 1
    assert events[0]["event_type"] == "deposit"

    summary = account_summary(db_session)
    assert summary["cash_balance"] == Decimal("1000.0000")
    assert summary["net_invested"] == Decimal("1000")
    assert summary["cumulative_pnl"] == Decimal("0.000000")

    performance = account_performance(None, None, db_session)
    assert performance["coverage"]["points"] >= 1
    assert performance["basis"] == "account_balance_replay"

    assert delete_cash_event(created["id"], db_session) == {"detail": "deleted"}
    assert list_cash_events(None, None, 500, db_session) == []


def test_import_preview_commit_and_trace_api_contract(db_session):
    import asyncio
    import io

    from fastapi import UploadFile

    from app.api.v1.portfolio import (
        commit_portfolio_import,
        get_portfolio_import,
        list_portfolio_imports,
        preview_portfolio_import,
    )
    from app.schemas.portfolio import ImportCommitIn, ImportCommitRowIn

    content = (
        "成交日期,证券代码,证券名称,业务名称,成交价格,成交数量,成交金额,手续费,成交编号\n"
        "2026-01-05,600519,贵州茅台,证券买入,1500,10,15000,5,API001\n"
    ).encode("utf-8")
    upload = UploadFile(filename="delivery.csv", file=io.BytesIO(content))

    preview = asyncio.run(
        preview_portfolio_import(
            file=upload,
            source_kind=None,
            mapping_json=None,
            header_row=None,
            default_asset_type="auto",
            db=db_session,
        )
    )

    assert preview["detected"]["source_kind"] == "citic_delivery"
    assert preview["counts"]["importable"] == 1

    rows = [ImportCommitRowIn(**row) for row in preview["rows"] if row["status"] == "ok"]
    committed = commit_portfolio_import(
        ImportCommitIn(batch_id=preview["batch_id"], rows=rows), db_session
    )

    assert committed["counts"]["imported"] == 1
    assert committed["position_effects"][0]["asset_code"] == "600519"

    batches = list_portfolio_imports(20, db_session)
    assert batches[0].id == preview["batch_id"]
    assert batches[0].status == "committed"

    detail = get_portfolio_import(preview["batch_id"], db_session)
    assert detail.id == preview["batch_id"]
