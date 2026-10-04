"""Materialize manual/screenshot holdings as dated opening ledger events.

Existing positions without transactions become one ``opening`` ledger event dated
``buy_date`` (or the position's creation date), so later trades accumulate on top
of them instead of overwriting them. The script never invents buy/sell history:
positions without cost information are reported and left untouched.

Default is a dry-run preview that writes nothing:
    python scripts/backfill_opening_holdings.py
Apply only after reviewing the preview and backing up the database:
    docker exec fundpilot_postgres pg_dump -U postgres fund_watcher > fund_watcher_backup.sql
    python scripts/backfill_opening_holdings.py --apply --yes
"""

from __future__ import annotations

import argparse
import sys
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.engine import make_url

from app.core.config import get_settings
from app.db.models import PortfolioPosition
from app.db.session import SessionLocal
from app.services.portfolio_service import (
    AUTO_SUMMARY_NOTE,
    _asset_transactions,
    _build_opening_transaction,
    _identity,
    _position_row,
    _rebuild_position_from_transactions,
    _replay_transactions,
    ensure_opening_transaction,
)

SHARE_TOLERANCE = Decimal("0.0001")
AMOUNT_TOLERANCE = Decimal("0.01")


def _masked_database_url() -> str:
    try:
        return make_url(get_settings().database_url).render_as_string(hide_password=True)
    except Exception:
        return "<无法解析 DATABASE_URL>"


def _asset_label(position: PortfolioPosition) -> str:
    asset_type, asset_code = _identity(position)
    return f"{asset_code}({asset_type})"


def _collect_candidates(db):
    positions = [
        item
        for item in db.scalars(select(PortfolioPosition).order_by(PortfolioPosition.id))
        if item.holding_share is not None and Decimal(item.holding_share) > 0
    ]
    ready: list[PortfolioPosition] = []
    skipped: list[tuple[PortfolioPosition, str]] = []
    for position in positions:
        asset_type, asset_code = _identity(position)
        if _asset_transactions(db, asset_type, asset_code):
            skipped.append((position, "已有流水，跳过"))
            continue
        if position.note == AUTO_SUMMARY_NOTE:
            skipped.append((position, "已标记自动汇总但无流水，需人工核对"))
            continue
        if _build_opening_transaction(position) is None:
            skipped.append((position, "缺少成本信息，需人工补全后重跑"))
            continue
        ready.append(position)
    return ready, skipped


def _print_preview(ready, skipped) -> None:
    print("=" * 96)
    print(f"数据库：{_masked_database_url()}")
    print("模式：dry-run（只预览，不写入）")
    print("=" * 96)
    print(f"{'资产':<18}{'改造前份额':>14}{'期初日期':>14}{'期初净值':>12}{'期初份额':>14}{'改造后份额':>14}")
    for position in ready:
        opening = _build_opening_transaction(position)
        projected_share, _ = _replay_transactions([opening])
        print(
            f"{_asset_label(position):<18}"
            f"{Decimal(position.holding_share):>14}"
            f"{str(opening.trade_date):>14}"
            f"{opening.nav:>12}"
            f"{opening.share:>14}"
            f"{projected_share:>14}"
        )
    if skipped:
        print("-" * 96)
        for position, reason in skipped:
            print(f"跳过 {_asset_label(position)}：{reason}")
    print("-" * 96)
    print(f"可回填 {len(ready)} 项，跳过 {len(skipped)} 项。")


def _apply(db, ready) -> int:
    failures: list[str] = []
    for position in ready:
        asset_type, asset_code = _identity(position)
        before_share = Decimal(position.holding_share)
        before_amount = Decimal(position.holding_amount) if position.holding_amount is not None else None
        locked = _position_row(db, asset_type, asset_code, for_update=True)
        ensure_opening_transaction(db, locked)
        db.flush()
        rebuilt = _rebuild_position_from_transactions(db, asset_type, asset_code)
        if rebuilt is None or abs(Decimal(rebuilt.holding_share) - before_share) > SHARE_TOLERANCE:
            failures.append(f"{_asset_label(position)}：份额核对不一致")
            continue
        if before_amount is not None and abs(Decimal(rebuilt.holding_amount) - before_amount) > AMOUNT_TOLERANCE:
            failures.append(f"{_asset_label(position)}：金额核对不一致")
    if failures:
        db.rollback()
        print("回填失败，已整体回滚：")
        for item in failures:
            print(f"  - {item}")
        return 1
    db.commit()
    print(f"已回填 {len(ready)} 项期初持仓事件，核对通过。")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="把手工/截图持仓回填为有日期的期初账本事件")
    parser.add_argument("--apply", action="store_true", help="实际写入（默认只预览）")
    parser.add_argument("--yes", action="store_true", help="与 --apply 一起使用，确认已备份数据库")
    args = parser.parse_args()
    if args.apply and not args.yes:
        print("--apply 需要同时提供 --yes 以确认已备份数据库。")
        return 2

    with SessionLocal() as db:
        ready, skipped = _collect_candidates(db)
        _print_preview(ready, skipped)
        if not args.apply:
            print("dry-run 结束：未写入任何数据。确认无误后使用 --apply --yes 执行。")
            return 0
        if not ready:
            print("没有需要回填的持仓。")
            return 0
        return _apply(db, ready)


if __name__ == "__main__":
    sys.exit(main())
