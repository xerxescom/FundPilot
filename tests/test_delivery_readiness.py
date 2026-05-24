import importlib

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.services.task_runner_service import available_tasks


@pytest.fixture(autouse=True)
def clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_scheduler_config_defaults_to_disabled(monkeypatch):
    monkeypatch.delenv("ENABLE_SCHEDULER", raising=False)

    settings = get_settings()

    assert settings.enable_scheduler is False


def test_scheduler_config_can_be_enabled(monkeypatch):
    monkeypatch.setenv("ENABLE_SCHEDULER", "true")

    settings = get_settings()

    assert settings.enable_scheduler is True


def test_task_descriptions_are_readable_chinese():
    descriptions = {item["task_name"]: item["description"] for item in available_tasks()}

    assert descriptions["sync_watchlist_nav"] == "同步全部自选基金净值"
    assert descriptions["generate_daily_report"] == "生成每日基金简报"


def test_app_startup_with_scheduler_disabled_keeps_health_route(monkeypatch):
    monkeypatch.setenv("ENABLE_SCHEDULER", "false")

    import app.main as main_module

    main_module = importlib.reload(main_module)
    monkeypatch.setattr(main_module, "init_db", lambda: None)

    with TestClient(main_module.app) as client:
        response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
