from __future__ import annotations

from datetime import date

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data_source.akshare_client import AkshareFundDataSource
from app.db.models import FundHoldingIndustry, FundHoldingStock, Watchlist
from app.services.nav_service import decimal_or_none, ensure_fund_info
from app.services.task_log_service import run_logged


def upsert_fund_holding_industry_rows(db: Session, fund_code: str, rows: pd.DataFrame) -> int:
    count = 0
    fund_code = fund_code.zfill(6)
    for _, row in rows.iterrows():
        report_date: date = row["report_date"]
        industry = str(row["industry"])
        existing = db.scalar(
            select(FundHoldingIndustry).where(
                FundHoldingIndustry.fund_code == fund_code,
                FundHoldingIndustry.report_date == report_date,
                FundHoldingIndustry.industry == industry,
            )
        )
        values = {
            "weight": decimal_or_none(row.get("weight")),
            "source": row.get("source"),
        }
        if existing:
            for key, value in values.items():
                setattr(existing, key, value)
        else:
            db.add(
                FundHoldingIndustry(
                    fund_code=fund_code,
                    report_date=report_date,
                    industry=industry,
                    **values,
                )
            )
        count += 1
    db.commit()
    return count


def upsert_fund_holding_stock_rows(db: Session, fund_code: str, rows: pd.DataFrame) -> int:
    count = 0
    fund_code = fund_code.zfill(6)
    for _, row in rows.iterrows():
        report_date: date = row["report_date"]
        stock_code = str(row["stock_code"])
        existing = db.scalar(
            select(FundHoldingStock).where(
                FundHoldingStock.fund_code == fund_code,
                FundHoldingStock.report_date == report_date,
                FundHoldingStock.stock_code == stock_code,
            )
        )
        values = {
            "stock_name": str(row.get("stock_name") or stock_code),
            "industry": row.get("industry") if pd.notna(row.get("industry")) else None,
            "weight": decimal_or_none(row.get("weight")),
            "source": row.get("source"),
        }
        if existing:
            for key, value in values.items():
                setattr(existing, key, value)
        else:
            db.add(
                FundHoldingStock(
                    fund_code=fund_code,
                    report_date=report_date,
                    stock_code=stock_code,
                    **values,
                )
            )
        count += 1
    db.commit()
    return count


def _industry_rows_from_stock_rows(rows: pd.DataFrame) -> pd.DataFrame:
    if rows.empty or "industry" not in rows.columns or rows["industry"].isna().all():
        return pd.DataFrame()
    normalized = rows.dropna(subset=["industry", "weight"])
    if normalized.empty:
        return pd.DataFrame()
    return normalized.groupby(["fund_code", "report_date", "industry", "source"], as_index=False)["weight"].sum()


def sync_fund_holding_industries(db: Session, fund_code: str) -> int:
    fund_code = fund_code.zfill(6)
    ensure_fund_info(db, fund_code)
    source = AkshareFundDataSource()
    stock_rows = source.get_fund_holding_stocks(fund_code)
    if not stock_rows.empty:
        upsert_fund_holding_stock_rows(db, fund_code, stock_rows)
        rows = _industry_rows_from_stock_rows(stock_rows)
    else:
        rows = source.get_fund_holding_industries(fund_code)
    if rows.empty:
        return 0
    return upsert_fund_holding_industry_rows(db, fund_code, rows)


def sync_fund_holding_stocks(db: Session, fund_code: str) -> int:
    fund_code = fund_code.zfill(6)
    ensure_fund_info(db, fund_code)
    rows = AkshareFundDataSource().get_fund_holding_stocks(fund_code)
    if rows.empty:
        return 0
    count = upsert_fund_holding_stock_rows(db, fund_code, rows)
    industry_rows = _industry_rows_from_stock_rows(rows)
    if not industry_rows.empty:
        upsert_fund_holding_industry_rows(db, fund_code, industry_rows)
    return count


def sync_watchlist_holding_industries(db: Session) -> dict[str, int | str]:
    def _sync() -> dict[str, int | str]:
        result: dict[str, int | str] = {}
        funds = db.scalars(select(Watchlist).where(Watchlist.is_active.is_(True))).all()
        for item in funds:
            try:
                result[item.fund_code] = sync_fund_holding_stocks(db, item.fund_code)
            except Exception as exc:
                result[item.fund_code] = f"failed: {exc}"
        return result

    return run_logged(db, "sync_holding_industries", _sync)


def latest_holding_industries(db: Session, fund_code: str) -> list[FundHoldingIndustry]:
    fund_code = fund_code.zfill(6)
    latest_date = db.scalar(
        select(FundHoldingIndustry.report_date)
        .where(FundHoldingIndustry.fund_code == fund_code)
        .order_by(FundHoldingIndustry.report_date.desc())
        .limit(1)
    )
    if not latest_date:
        return []
    return list(
        db.scalars(
            select(FundHoldingIndustry)
            .where(
                FundHoldingIndustry.fund_code == fund_code,
                FundHoldingIndustry.report_date == latest_date,
            )
            .order_by(FundHoldingIndustry.weight.desc().nulls_last())
        )
    )


def latest_holding_stocks(db: Session, fund_code: str) -> list[FundHoldingStock]:
    fund_code = fund_code.zfill(6)
    latest_date = db.scalar(
        select(FundHoldingStock.report_date)
        .where(FundHoldingStock.fund_code == fund_code)
        .order_by(FundHoldingStock.report_date.desc())
        .limit(1)
    )
    if not latest_date:
        return []
    return list(
        db.scalars(
            select(FundHoldingStock)
            .where(
                FundHoldingStock.fund_code == fund_code,
                FundHoldingStock.report_date == latest_date,
            )
            .order_by(FundHoldingStock.weight.desc().nulls_last())
            .limit(10)
        )
    )
