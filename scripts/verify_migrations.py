"""Verify Alembic migrations against PostgreSQL on throwaway databases.

Runs both the fresh-install path and the legacy-upgrade path (a database without
``task_run_log.result_json``), checks the resulting schema and version, and tests
that downgrade + re-upgrade is idempotent. Scratch databases are dropped afterwards.

Usage:
    python scripts/verify_migrations.py
    FUNDPILOT_TEST_POSTGRES_URL=postgresql+psycopg2://user:pass@host:5432/postgres \
        python scripts/verify_migrations.py

The URL must point at a maintenance database (e.g. ``postgres``) on the target
server; the script creates and drops its own databases and never touches others.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_POSTGRES_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/postgres"
FRESH_DB = "fundpilot_mig_fresh"
LEGACY_DB = "fundpilot_mig_legacy"
HEAD_REVISION = "0008_task_batch"
BATCH_TABLES = ("task_batch", "task_batch_item", "trade_calendar")

results: list[tuple[bool, str]] = []


def check(condition: bool, label: str, detail: str = "") -> None:
    results.append((condition, label))
    mark = "OK  " if condition else "FAIL"
    print(f"[{mark}] {label}" + (f"  {detail}" if detail and not condition else ""))


def scratch_url(admin_url: str, database: str) -> str:
    return make_url(admin_url).set(database=database).render_as_string(hide_password=False)


def recreate_database(admin_engine, database: str) -> None:
    with admin_engine.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)'))
        conn.execute(text(f'CREATE DATABASE "{database}"'))


def drop_database(admin_engine, database: str) -> None:
    with admin_engine.connect() as conn:
        conn.execute(text(f'DROP DATABASE IF EXISTS "{database}" WITH (FORCE)'))


def run_alembic(database_url: str, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ, "DATABASE_URL": database_url}
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
    )


def column_exists(engine, table: str, column: str) -> bool:
    with engine.connect() as conn:
        if table not in set(inspect(conn).get_table_names()):
            return False
        columns = {item["name"] for item in inspect(conn).get_columns(table)}
    return column in columns


def table_exists(engine, table: str) -> bool:
    with engine.connect() as conn:
        return table in set(inspect(conn).get_table_names())


def current_revision(engine) -> str | None:
    with engine.connect() as conn:
        return conn.execute(text("SELECT version_num FROM alembic_version")).scalar()


def verify_fresh(admin_engine, admin_url: str) -> None:
    print(f"\n== 全新库路径：{FRESH_DB} ==")
    recreate_database(admin_engine, FRESH_DB)
    url = scratch_url(admin_url, FRESH_DB)
    result = run_alembic(url, "upgrade", "head")
    check(result.returncode == 0, "全新库 alembic upgrade head 成功", result.stderr[-400:])
    engine = create_engine(url, poolclass=NullPool)
    try:
        check(column_exists(engine, "task_run_log", "result_json"), "全新库存在 result_json 列")
        for table in BATCH_TABLES:
            check(table_exists(engine, table), f"全新库存在 {table} 表")
        check(column_exists(engine, "task_run_log", "batch_id"), "全新库存在 task_run_log.batch_id")
        check(column_exists(engine, "ai_report", "batch_id"), "全新库存在 ai_report.batch_id")
        check(column_exists(engine, "ai_report", "trade_date"), "全新库存在 ai_report.trade_date")
        check(current_revision(engine) == HEAD_REVISION, "全新库版本为 head", str(current_revision(engine)))
    finally:
        engine.dispose()


def verify_legacy(admin_engine, admin_url: str) -> None:
    print(f"\n== 旧库升级路径：{LEGACY_DB} ==")
    recreate_database(admin_engine, LEGACY_DB)
    url = scratch_url(admin_url, LEGACY_DB)
    result = run_alembic(url, "upgrade", "0006_unified_assets")
    check(result.returncode == 0, "旧库升级到 0006 成功", result.stderr[-400:])

    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.begin() as conn:
            # Simulate a pre-0007/pre-0008 database (0001's create_all uses current models)
            # and seed legacy rows that must survive the upgrade.
            conn.execute(text("ALTER TABLE task_run_log DROP COLUMN IF EXISTS result_json"))
            conn.execute(text("ALTER TABLE task_run_log DROP COLUMN IF EXISTS batch_id"))
            conn.execute(text("ALTER TABLE ai_report DROP COLUMN IF EXISTS batch_id"))
            conn.execute(text("ALTER TABLE ai_report DROP COLUMN IF EXISTS trade_date"))
            conn.execute(text("ALTER TABLE ai_report DROP CONSTRAINT IF EXISTS uq_ai_report_batch_daily"))
            conn.execute(text("DROP TABLE IF EXISTS task_batch_item"))
            conn.execute(text("DROP TABLE IF EXISTS task_batch"))
            conn.execute(text("DROP TABLE IF EXISTS trade_calendar"))
            conn.execute(
                text(
                    "INSERT INTO task_run_log (task_name, status, message) "
                    "VALUES ('update_fund_nav', 'success', '{}')"
                )
            )
            conn.execute(
                text(
                    "INSERT INTO portfolio_position "
                    "(fund_code, asset_type, asset_code, holding_amount, holding_share, cost_nav, buy_date) "
                    "VALUES ('000001', 'fund', '000001', 1000, 1000, 1, '2026-01-01')"
                )
            )
        check(not column_exists(engine, "task_run_log", "result_json"), "旧库模拟：result_json 列已移除")
        check(not table_exists(engine, "task_batch"), "旧库模拟：task_batch 表已移除")

        result = run_alembic(url, "upgrade", "head")
        check(result.returncode == 0, "旧库升级到 head 成功", result.stderr[-400:])
        check(column_exists(engine, "task_run_log", "result_json"), "升级后存在 result_json 列")
        for table in BATCH_TABLES:
            check(table_exists(engine, table), f"升级后存在 {table} 表")
        check(column_exists(engine, "task_run_log", "batch_id"), "升级后存在 task_run_log.batch_id")
        check(column_exists(engine, "ai_report", "batch_id"), "升级后存在 ai_report.batch_id")
        check(column_exists(engine, "ai_report", "trade_date"), "升级后存在 ai_report.trade_date")
        with engine.connect() as conn:
            log_count = conn.execute(text("SELECT count(*) FROM task_run_log")).scalar()
            position_share = conn.execute(text("SELECT holding_share FROM portfolio_position")).scalar()
        check(log_count == 1, "旧库任务日志行保留", str(log_count))
        check(str(position_share) == "1000.0000", "旧库持仓行保留", str(position_share))

        with engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO task_batch (batch_type, idempotency_key, status) "
                    "VALUES ('daily_update', 'legacy-idempotency', 'queued')"
                )
            )
        result = run_alembic(url, "downgrade", "-1")
        check(result.returncode == 0, "downgrade -1 成功", result.stderr[-400:])
        check(not table_exists(engine, "task_batch"), "降级后 task_batch 表已移除")
        result = run_alembic(url, "upgrade", "head")
        check(result.returncode == 0, "重复 upgrade 到 head 成功（幂等）", result.stderr[-400:])
        check(table_exists(engine, "task_batch"), "重新升级后 task_batch 表重建")
        check(current_revision(engine) == HEAD_REVISION, "旧库升级后版本为 head", str(current_revision(engine)))
    finally:
        engine.dispose()


def main() -> int:
    admin_url = os.environ.get("FUNDPILOT_TEST_POSTGRES_URL", DEFAULT_POSTGRES_URL)
    print(f"维护库：{make_url(admin_url).render_as_string(hide_password=True)}")
    try:
        admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT", poolclass=NullPool)
        with admin_engine.connect():
            pass
    except Exception as exc:  # noqa: BLE001 - report any connection failure the same way
        print(f"无法连接 PostgreSQL：{exc}")
        print("请先启动数据库（docker compose up -d postgres）或设置 FUNDPILOT_TEST_POSTGRES_URL。")
        return 2

    heads = run_alembic(admin_url, "heads")
    check(heads.returncode == 0 and len(heads.stdout.strip().splitlines()) == 1, "alembic 只有一个 head", heads.stdout)

    try:
        verify_fresh(admin_engine, admin_url)
        verify_legacy(admin_engine, admin_url)
    finally:
        for database in (FRESH_DB, LEGACY_DB):
            try:
                drop_database(admin_engine, database)
            except Exception as exc:  # noqa: BLE001 - cleanup must not mask results
                print(f"清理 {database} 失败：{exc}")
        admin_engine.dispose()

    failed = [label for ok, label in results if not ok]
    print()
    if failed:
        print(f"迁移验证失败 {len(failed)} 项：")
        for label in failed:
            print(f"  - {label}")
        return 1
    print(f"迁移验证全部通过（{len(results)} 项检查）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
