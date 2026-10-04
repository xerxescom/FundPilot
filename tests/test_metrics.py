"""指标与日志配置：注册表可重置、路由模板标签、业务计数器、数据库 Gauge。"""

import contextlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import generate_latest

from app.core import metrics
from app.core.logging import configure_logging


@pytest.fixture(autouse=True)
def fresh_registry():
    metrics.reset_metrics_for_tests()
    yield
    metrics.reset_metrics_for_tests()


def _scrape() -> str:
    return generate_latest(metrics.get_registry()).decode()


def test_middleware_uses_route_templates_and_skips_probes():
    app = FastAPI()
    app.add_middleware(metrics.PrometheusMiddleware)

    @app.get("/items/{item_id}")
    def read_item(item_id: int):
        return {"id": item_id}

    @app.get("/health")
    def health():
        return {"status": "ok"}

    with TestClient(app) as client:
        assert client.get("/items/42").status_code == 200
        assert client.get("/health").status_code == 200
        assert client.get("/missing").status_code == 404

    text = _scrape()
    # 路由模板而不是原始路径，避免标签基数爆炸
    assert (
        'fundpilot_http_requests_total{method="GET",path="/items/{item_id}",status="200"} 1.0'
        in text
    )
    assert 'path="unmatched"' in text
    assert 'path="/health"' not in text  # 探针不记录
    assert "fundpilot_http_request_duration_seconds_count" in text


def test_task_run_counter_follows_task_log(db_session):
    from app.services import task_log_service

    log = task_log_service.record_task_log(db_session, "sync_watchlist_nav", "success")
    task_log_service.update_task_log(db_session, log.id, "failed")

    text = _scrape()
    assert (
        'fundpilot_task_runs_total{status="success",task_name="sync_watchlist_nav"} 1.0' in text
    )
    assert 'fundpilot_task_runs_total{status="failed",task_name="sync_watchlist_nav"} 1.0' in text


def test_data_source_counter_records_failed_attempts(monkeypatch):
    from app.services import nav_service

    class BrokenSource:
        source_name = "broken"

        def get_fund_nav_history(self, fund_code):
            raise RuntimeError("boom")

    monkeypatch.setattr(nav_service, "_data_sources", lambda: [BrokenSource()])
    with pytest.raises(ValueError):
        nav_service.fetch_nav_with_fallback("000001")

    text = _scrape()
    # 每次尝试各记一次（SOURCE_RETRY_COUNT 次重试）
    assert (
        'fundpilot_data_source_requests_total{operation="fund_nav",source="broken",status="failed"} 2.0'
        in text
    )


def test_batch_item_gauge_reads_database(db_session, monkeypatch):
    import app.db.session as db_session_module
    from app.db.models import TaskBatch, TaskBatchItem

    batch = TaskBatch(batch_type="daily_update", idempotency_key="metrics-gauge", status="running")
    db_session.add(batch)
    db_session.flush()
    db_session.add(
        TaskBatchItem(
            batch_id=batch.id,
            step="sync_nav",
            asset_type="fund",
            asset_code="000001",
            status="success",
            idempotency_key="metrics-gauge-1",
        )
    )
    db_session.add(
        TaskBatchItem(
            batch_id=batch.id,
            step="sync_nav",
            asset_type="fund",
            asset_code="000002",
            status="failed",
            idempotency_key="metrics-gauge-2",
        )
    )
    db_session.commit()

    monkeypatch.setattr(db_session_module, "SessionLocal", lambda: contextlib.nullcontext(db_session))

    text = _scrape()
    assert 'fundpilot_task_batch_items{status="success",step="sync_nav"} 1.0' in text
    assert 'fundpilot_task_batch_items{status="failed",step="sync_nav"} 1.0' in text


def test_gauge_collector_survives_database_errors(monkeypatch):
    import app.db.session as db_session_module

    def broken_session():
        raise RuntimeError("db down")

    monkeypatch.setattr(db_session_module, "SessionLocal", broken_session)

    # 查库失败不能阻断 /metrics，只是没有样本（HELP/TYPE 行仍在，无样本行）
    assert "fundpilot_task_batch_items{" not in _scrape()


def test_real_app_exposes_metrics_endpoint(monkeypatch):
    import importlib

    monkeypatch.setenv("ENABLE_SCHEDULER", "false")
    import app.main as main_module

    main_module = importlib.reload(main_module)
    monkeypatch.setattr(main_module, "init_db", lambda: None)

    with TestClient(main_module.app) as client:
        response = client.get("/metrics")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert "fundpilot_http_requests_total" in response.text


def test_configure_logging_is_idempotent():
    configure_logging()
    configure_logging(level="DEBUG", json_output=True)
    configure_logging()
