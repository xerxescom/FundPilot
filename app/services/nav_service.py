from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data_source.akshare_client import AkshareFundDataSource
from app.data_source.eastmoney_client import EastmoneyFundDataSource
from app.db.models import FundInfo, FundNav, Watchlist


def decimal_or_none(value: object, places: str = "0.000001") -> Decimal | None:
    if value is None or pd.isna(value):
        return None
    return Decimal(str(value)).quantize(Decimal(places))


def ensure_fund_info(db: Session, fund_code: str) -> FundInfo:
    fund_code = fund_code.zfill(6)
    existing = db.scalar(select(FundInfo).where(FundInfo.fund_code == fund_code))
    if existing:
        return existing
    data = AkshareFundDataSource().get_fund_info(fund_code)
    fund = FundInfo(
        fund_code=fund_code,
        fund_name=data.get("fund_name") or fund_code,
        fund_type=data.get("fund_type"),
        source=data.get("source"),
    )
    db.add(fund)
    db.commit()
    db.refresh(fund)
    return fund


def upsert_nav_rows(db: Session, rows: pd.DataFrame) -> int:
    count = 0
    for _, row in rows.iterrows():
        fund_code = str(row["fund_code"]).zfill(6)
        nav_date: date = row["nav_date"]
        existing = db.scalar(
            select(FundNav).where(FundNav.fund_code == fund_code, FundNav.nav_date == nav_date)
        )
        values = {
            "unit_nav": decimal_or_none(row.get("unit_nav")),
            "accumulated_nav": decimal_or_none(row.get("accumulated_nav")),
            "daily_return": decimal_or_none(row.get("daily_return")),
            "source": row.get("source"),
        }
        if existing:
            for key, value in values.items():
                setattr(existing, key, value)
        else:
            db.add(FundNav(fund_code=fund_code, nav_date=nav_date, **values))
        count += 1
    db.commit()
    return count


def sync_fund_nav(db: Session, fund_code: str) -> int:
    fund_code = fund_code.zfill(6)
    ensure_fund_info(db, fund_code)
    try:
        rows = AkshareFundDataSource().get_fund_nav_history(fund_code)
    except Exception as primary_exc:
        try:
            rows = EastmoneyFundDataSource().get_fund_nav_history(fund_code)
        except Exception as fallback_exc:
            raise ValueError(
                f"Both data sources failed for {fund_code}; "
                f"akshare: {primary_exc}; eastmoney: {fallback_exc}"
            ) from fallback_exc
    return upsert_nav_rows(db, rows)


def sync_watchlist_nav(db: Session) -> dict[str, int | str]:
    result: dict[str, int | str] = {}
    funds = db.scalars(select(Watchlist).where(Watchlist.is_active.is_(True))).all()
    for item in funds:
        try:
            result[item.fund_code] = sync_fund_nav(db, item.fund_code)
        except Exception as exc:
            result[item.fund_code] = f"failed: {exc}"
    return result


def list_fund_nav(db: Session, fund_code: str, limit: int | None = None) -> list[FundNav]:
    stmt = (
        select(FundNav)
        .where(FundNav.fund_code == fund_code.zfill(6))
        .order_by(FundNav.nav_date.asc())
    )
    if limit:
        stmt = stmt.limit(limit)
    return list(db.scalars(stmt))


def latest_nav(db: Session, fund_code: str) -> FundNav | None:
    return db.scalar(
        select(FundNav)
        .where(FundNav.fund_code == fund_code.zfill(6))
        .order_by(FundNav.nav_date.desc())
        .limit(1)
    )
