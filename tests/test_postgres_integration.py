"""PostgreSQL 集成测试：在由 Alembic 迁移建出的库上验证核心链路。

默认跳过；设置 FUNDPILOT_TEST_POSTGRES_URL 指向维护库后运行：

    FUNDPILOT_TEST_POSTGRES_URL=postgresql+psycopg2://postgres:postgres@localhost:5432/postgres \
        pytest -m postgres -q

脚本会创建独立的临时库并跑完整迁移，结束后删除，不影响其他数据库。
"""

from __future__ import annotations

import os
import subprocess
import sys
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine, inspect, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import NullPool

pytestmark = pytest.mark.postgres

ROOT = Path(__file__).resolve().parents[1]
ADMIN_URL = os.environ.get("FUNDPILOT_TEST_POSTGRES_URL")

if not ADMIN_URL:
    pytest.skip(
        "未设置 FUNDPILOT_TEST_POSTGRES_URL，跳过 PostgreSQL 集成测试",
        allow_module_level=True,
    )


@pytest.fixture(scope="module")
def pg_session_factory():
    admin_engine = create_engine(ADMIN_URL, isolation_level="AUTOCOMMIT", poolclass=NullPool)
    try:
        with admin_engine.connect():
            pass
    except Exception as exc:  # noqa: BLE001 - any connection failure means skip
        pytest.skip(f"无法连接 PostgreSQL：{exc}")

    database = f"fundpilot_it_{uuid.uuid4().hex[:8]}"
    with admin_engine.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{database}"'))
    url = make_url(ADMIN_URL).set(database=database).render_as_string(hide_password=False)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=ROOT,
        env={**os.environ, "DATABASE_URL": url},
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        with admin_engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)'))
        pytest.fail(f"alembic upgrade head 失败：{result.stderr[-500:]}")

    engine = create_engine(url, poolclass=NullPool)
    factory = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    try:
        yield factory
    finally:
        engine.dispose()
        with admin_engine.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)'))
        admin_engine.dispose()


@pytest.fixture
def pg_session(pg_session_factory):
    with pg_session_factory() as session:
        yield session


def _position_by_code(overview: dict, asset_code: str) -> dict:
    return next(item for item in overview["positions"] if item["asset_code"] == asset_code)


def test_schema_comes_from_migrations(pg_session):
    inspector = inspect(pg_session.bind)
    columns = {item["name"] for item in inspector.get_columns("task_run_log")}
    assert "result_json" in columns
    assert "batch_id" in columns
    tables = set(inspector.get_table_names())
    assert {"task_batch", "task_batch_item", "trade_calendar"} <= tables
    report_columns = {item["name"] for item in inspector.get_columns("ai_report")}
    assert {"batch_id", "trade_date"} <= report_columns


def test_concurrent_item_claim_only_one_wins(pg_session_factory, pg_session):
    from app.db.models import TaskBatchItem
    from app.services import batch_worker_service, daily_batch_service

    batch, _ = daily_batch_service.create_or_get_daily_batch(pg_session, trade_date=date(2026, 10, 10))
    item = pg_session.scalar(
        select(TaskBatchItem).where(TaskBatchItem.batch_id == batch.id, TaskBatchItem.step == "market")
    )
    now = datetime(2026, 10, 10, 18, 0)

    with pg_session_factory() as other_session:
        first = batch_worker_service.claim_item(pg_session, item.id, "worker-a", now)
        second = batch_worker_service.claim_item(other_session, item.id, "worker-b", now)

    assert first is True
    assert second is False
    # 释放领取，避免过期租约影响后续用例
    item.status = "queued"
    item.lease_owner = None
    item.lease_expires_at = None
    pg_session.commit()


def test_duplicate_daily_report_for_same_batch_is_rejected(pg_session):
    from app.db.models import AIReport

    pg_session.add(AIReport(report_type="daily", batch_id=999001, content="第一版"))
    pg_session.commit()
    pg_session.add(AIReport(report_type="daily", batch_id=999001, content="重复版本"))

    with pytest.raises(IntegrityError):
        pg_session.commit()
    pg_session.rollback()


def test_expired_lease_recovery_across_sessions(pg_session_factory, pg_session):
    from app.db.models import TaskBatchItem
    from app.services import batch_worker_service, daily_batch_service

    batch, _ = daily_batch_service.create_or_get_daily_batch(pg_session, trade_date=date(2026, 10, 11))
    item = pg_session.scalar(
        select(TaskBatchItem).where(TaskBatchItem.batch_id == batch.id, TaskBatchItem.step == "market")
    )
    now = datetime(2026, 10, 11, 18, 0)
    item.status = "running"
    item.lease_owner = "dead-worker"
    item.lease_expires_at = now - timedelta(seconds=30)
    pg_session.commit()

    with pg_session_factory() as other_session:
        recovered = batch_worker_service.recover_expired_leases(other_session, now)

    assert recovered == {"interrupted": 1}
    pg_session.expire_all()
    refreshed = pg_session.get(TaskBatchItem, item.id)
    assert refreshed.status == "interrupted"
    assert refreshed.error_class == "lease_expired"


def test_manual_position_plus_buy_keeps_shares_on_postgres(pg_session):
    from app.db.models import PortfolioPosition
    from app.services.portfolio_service import create_transaction, list_transactions, portfolio_overview

    pg_session.add(
        PortfolioPosition(
            fund_code="000010",
            asset_type="fund",
            asset_code="000010",
            holding_amount=Decimal("1000"),
            holding_share=Decimal("1000"),
            cost_nav=Decimal("1"),
            buy_date=date(2026, 1, 1),
            note="由中信证券持仓截图导入（2026-01-01）",
        )
    )
    pg_session.commit()

    create_transaction(
        pg_session,
        {
            "fund_code": "000010",
            "trade_date": date(2026, 5, 1),
            "trade_type": "buy",
            "amount": Decimal("100"),
            "nav": Decimal("1.000000"),
        },
    )

    position = _position_by_code(portfolio_overview(pg_session), "000010")["position"]
    assert position.holding_share == Decimal("1100.0000")
    assert any(item.trade_type == "opening" for item in list_transactions(pg_session, "000010"))


def test_backdated_sell_rolls_back_on_postgres(pg_session):
    from app.services.portfolio_service import create_transaction, list_transactions

    create_transaction(
        pg_session,
        {
            "fund_code": "000011",
            "trade_date": date(2026, 5, 10),
            "trade_type": "buy",
            "amount": Decimal("100"),
            "nav": Decimal("1.000000"),
        },
    )

    with pytest.raises(ValueError, match="可用持仓"):
        create_transaction(
            pg_session,
            {
                "fund_code": "000011",
                "trade_date": date(2026, 5, 1),
                "trade_type": "sell",
                "amount": Decimal("50"),
                "nav": Decimal("1.000000"),
            },
        )

    assert len(list_transactions(pg_session, "000011")) == 1


def test_task_result_json_round_trip_and_health(pg_session):
    from app.db.models import Watchlist
    from app.services.data_health_service import fund_data_health
    from app.services.task_log_service import latest_task_logs, record_task_log

    pg_session.add(Watchlist(fund_code="000012", fund_name="测试基金", is_active=True))
    pg_session.commit()
    payload = {"000012": {"status": "failed", "quality": {"issues": ["全部数据源同步失败"]}}}

    record_task_log(
        pg_session,
        task_name="queued_sync_watchlist_nav",
        status="failed",
        success_count=0,
        failure_count=1,
        message=str(payload)[:2000],
        result_json=payload,
    )

    assert latest_task_logs(pg_session)[0].result_json == payload
    health = fund_data_health(pg_session, "000012", today=date(2026, 5, 25))
    assert health["latest_sync_status"] == "failed"
    assert "全部数据源同步失败" in health["latest_failure_reason"]
