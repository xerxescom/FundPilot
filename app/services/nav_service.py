from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data_source.akshare_client import AkshareFundDataSource
from app.data_source.eastmoney_client import EastmoneyFundDataSource
from app.db.models import FundInfo, FundNav, Watchlist

SOURCE_RETRY_COUNT = 2


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


def validate_nav_rows(rows: pd.DataFrame, fund_code: str) -> dict[str, Any]:
    issues: list[str] = []
    fund_code = fund_code.zfill(6)
    required = {"fund_code", "nav_date", "unit_nav"}
    missing_columns = sorted(required - set(rows.columns))
    if missing_columns:
        issues.append(f"缺少必要字段：{', '.join(missing_columns)}")
        return {"valid": False, "issues": issues, "row_count": 0}

    normalized = rows.copy()
    normalized["fund_code"] = normalized["fund_code"].astype(str).str.zfill(6)
    normalized["nav_date"] = pd.to_datetime(normalized["nav_date"], errors="coerce")
    normalized["unit_nav"] = pd.to_numeric(normalized["unit_nav"], errors="coerce")
    if "daily_return" in normalized.columns:
        normalized["daily_return"] = pd.to_numeric(normalized["daily_return"], errors="coerce")

    wrong_code_count = int((normalized["fund_code"] != fund_code).sum())
    missing_date_count = int(normalized["nav_date"].isna().sum())
    missing_nav_count = int(normalized["unit_nav"].isna().sum())
    duplicate_count = int(normalized.duplicated(["fund_code", "nav_date"]).sum())
    missing_return_count = (
        int(normalized["daily_return"].isna().sum()) if "daily_return" in normalized.columns else len(normalized)
    )

    if normalized.empty:
        issues.append("数据源返回空净值")
    if wrong_code_count:
        issues.append(f"存在 {wrong_code_count} 条基金代码不匹配")
    if missing_date_count:
        issues.append(f"存在 {missing_date_count} 条缺少净值日期")
    if missing_nav_count:
        issues.append(f"存在 {missing_nav_count} 条缺少单位净值")
    if duplicate_count:
        issues.append(f"存在 {duplicate_count} 条重复净值")
    if missing_return_count:
        issues.append(f"存在 {missing_return_count} 条缺少日涨跌幅")

    blocking_issues = wrong_code_count + missing_date_count + missing_nav_count
    return {
        "valid": not normalized.empty and blocking_issues == 0,
        "issues": issues,
        "row_count": len(normalized),
        "duplicate_count": duplicate_count,
        "missing_daily_return_count": missing_return_count,
    }


def upsert_nav_rows(db: Session, rows: pd.DataFrame) -> int:
    count = 0
    for _, row in rows.iterrows():
        fund_code = str(row["fund_code"]).zfill(6)
        nav_date: date = row["nav_date"]
        existing = db.scalar(select(FundNav).where(FundNav.fund_code == fund_code, FundNav.nav_date == nav_date))
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


def _data_sources():
    return [AkshareFundDataSource(), EastmoneyFundDataSource()]


def fetch_nav_with_fallback(fund_code: str) -> tuple[pd.DataFrame, dict[str, Any]]:
    fund_code = fund_code.zfill(6)
    attempts: list[dict[str, Any]] = []
    last_error: Exception | None = None

    for source in _data_sources():
        for attempt in range(1, SOURCE_RETRY_COUNT + 1):
            try:
                rows = source.get_fund_nav_history(fund_code)
                quality = validate_nav_rows(rows, fund_code)
                attempts.append(
                    {
                        "source": source.source_name,
                        "attempt": attempt,
                        "status": "success" if quality["valid"] else "invalid",
                        "row_count": quality["row_count"],
                        "issues": quality["issues"],
                    }
                )
                if quality["valid"]:
                    return rows, {"source": source.source_name, "attempts": attempts, "quality": quality}
                last_error = ValueError("; ".join(quality["issues"]) or "invalid NAV rows")
            except Exception as exc:
                last_error = exc
                attempts.append(
                    {
                        "source": source.source_name,
                        "attempt": attempt,
                        "status": "failed",
                        "row_count": 0,
                        "issues": [str(exc)],
                    }
                )

    raise ValueError(f"全部数据源同步失败：{attempts}") from last_error


def sync_fund_nav_detailed(db: Session, fund_code: str) -> dict[str, Any]:
    fund_code = fund_code.zfill(6)
    ensure_fund_info(db, fund_code)
    rows, diagnostics = fetch_nav_with_fallback(fund_code)
    count = upsert_nav_rows(db, rows)
    return {
        "fund_code": fund_code,
        "synced_rows": count,
        "source": diagnostics["source"],
        "attempts": diagnostics["attempts"],
        "quality": diagnostics["quality"],
    }


def sync_fund_nav(db: Session, fund_code: str) -> int:
    return int(sync_fund_nav_detailed(db, fund_code)["synced_rows"])


def sync_watchlist_nav(db: Session) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    funds = db.scalars(select(Watchlist).where(Watchlist.is_active.is_(True))).all()
    for item in funds:
        try:
            detail = sync_fund_nav_detailed(db, item.fund_code)
            result[item.fund_code] = {"status": "success", **detail}
        except Exception as exc:
            result[item.fund_code] = {
                "fund_code": item.fund_code.zfill(6),
                "status": "failed",
                "synced_rows": 0,
                "source": None,
                "attempts": [],
                "quality": {
                    "valid": False,
                    "issues": [str(exc)],
                    "row_count": 0,
                    "duplicate_count": 0,
                    "missing_daily_return_count": 0,
                },
            }
    return result


def list_fund_nav(db: Session, fund_code: str, limit: int | None = None) -> list[FundNav]:
    stmt = select(FundNav).where(FundNav.fund_code == fund_code.zfill(6)).order_by(FundNav.nav_date.asc())
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
