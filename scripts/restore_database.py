"""把备份恢复到独立测试库，并逐项核对行数与持仓合计。

默认恢复到独立库（<库名>_restore_test），绝不覆盖 DATABASE_URL 指向的库；
只有同时给出 --target-live 和 --yes 才允许覆盖当前库（危险操作，谨慎使用）。

Run:
    python scripts/restore_database.py backups/fund_watcher_20261004T120000Z.dump
    python scripts/restore_database.py <dump> --target fund_watcher_restore_test
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from decimal import Decimal
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

DEFAULT_CONTAINER = "fundpilot_postgres"
CHECK_TABLES = ("portfolio_position", "portfolio_transaction", "fund_nav", "fund_score", "ai_report", "task_batch")


def _parse_args() -> argparse.Namespace:
    url = make_url(get_settings().database_url)
    parser = argparse.ArgumentParser(description="恢复备份到独立测试库并核对")
    parser.add_argument("dump", help="backup_database.py 生成的 .dump 文件")
    parser.add_argument("--container", default=DEFAULT_CONTAINER, help="PostgreSQL 容器名")
    parser.add_argument("--source-db", default=url.database or "fund_watcher", help="备份来源库（核对基准）")
    parser.add_argument("--user", default=url.username or "postgres", help="数据库用户")
    parser.add_argument("--target", default=None, help="恢复目标库（默认 <来源库>_restore_test）")
    parser.add_argument("--target-live", action="store_true", help="允许目标库等于当前库（需与 --yes 同用）")
    parser.add_argument("--yes", action="store_true", help="确认已理解覆盖风险")
    parser.add_argument("--keep-target", action="store_true", help="保留恢复后的库以便人工检查")
    return parser.parse_args()


def _psql(container: str, database: str, user: str, sql: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["docker", "exec", container, "psql", "-U", user, "-d", database, "-c", sql],
        capture_output=True,
        text=True,
    )


def _engine(container_url: str):
    return create_engine(container_url, poolclass=NullPool)


def _table_stats(engine, table: str) -> dict | None:
    try:
        with engine.connect() as conn:
            count = conn.execute(text(f"SELECT count(*) FROM {table}")).scalar()
        return {"count": int(count or 0)}
    except Exception:
        return None


def _holdings_totals(engine) -> tuple[Decimal, Decimal] | None:
    try:
        with engine.connect() as conn:
            row = conn.execute(
                text("SELECT COALESCE(SUM(holding_share),0), COALESCE(SUM(holding_amount),0) FROM portfolio_position")
            ).first()
        return (Decimal(str(row[0])), Decimal(str(row[1])))
    except Exception:
        return None


def _reconcile(source_url: str, target_url: str) -> bool:
    print("\n== 核对结果（来源库 vs 恢复库）==")
    source, target = _engine(source_url), _engine(target_url)
    ok = True
    try:
        for table in CHECK_TABLES:
            left = _table_stats(source, table)
            right = _table_stats(target, table)
            if left is None and right is None:
                continue
            match = bool(left and right and left["count"] == right["count"])
            ok = ok and match
            mark = "OK  " if match else "FAIL"
            print(f"[{mark}] {table}: {left['count'] if left else '-'} vs {right['count'] if right else '-'}")

        left_totals = _holdings_totals(source)
        right_totals = _holdings_totals(target)
        if left_totals and right_totals:
            match = left_totals == right_totals
            ok = ok and match
            mark = "OK  " if match else "FAIL"
            print(f"[{mark}] 持仓合计（份额/成本）: {left_totals} vs {right_totals}")
    finally:
        source.dispose()
        target.dispose()
    return ok


def main() -> int:
    args = _parse_args()
    url = make_url(get_settings().database_url)
    dump = Path(args.dump)
    if not dump.exists():
        print(f"找不到备份文件：{dump}")
        return 2

    target_db = args.target or f"{args.source_db}_restore_test"
    if target_db == args.source_db and not (args.target_live and args.yes):
        print(f"拒绝覆盖当前库 {target_db}；默认恢复到独立测试库，或显式 --target-live --yes。")
        return 2

    print(f"恢复 {dump.name} → {target_db}（容器 {args.container}）")
    drop = _psql(args.container, "postgres", args.user, f'DROP DATABASE IF EXISTS "{target_db}" WITH (FORCE)')
    create = _psql(args.container, "postgres", args.user, f'CREATE DATABASE "{target_db}"')
    if drop.returncode != 0 or create.returncode != 0:
        print(f"准备目标库失败：{drop.stderr.strip()} {create.stderr.strip()}")
        return 1

    with dump.open("rb") as handle:
        restore = subprocess.run(
            ["docker", "exec", "-i", args.container, "pg_restore", "-U", args.user, "-d", target_db, "--no-owner"],
            stdin=handle,
            capture_output=True,
        )
    if restore.returncode != 0:
        print(f"恢复失败（exit {restore.returncode}）")
        if restore.stderr:
            print(restore.stderr.decode("utf-8", errors="replace")[-500:])
        return 1

    target_url = url.set(database=target_db).render_as_string(hide_password=False)
    source_url = url.render_as_string(hide_password=False)
    reconciled = _reconcile(source_url, target_url)

    if not args.keep_target:
        _psql(args.container, "postgres", args.user, f'DROP DATABASE IF EXISTS "{target_db}" WITH (FORCE)')
        print(f"\n已清理恢复库 {target_db}（--keep-target 可保留）。")
    if reconciled:
        print("恢复演练通过：行数与持仓合计一致。")
        return 0
    print("恢复演练失败：存在不一致，请保留备份并人工排查。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
