from __future__ import annotations

from decimal import Decimal

import pandas as pd

from app.data_source.akshare_client import AkshareFundDataSource
from app.data_source.eastmoney_client import EastmoneyFundDataSource

UNIT_NAV_TOLERANCE = Decimal("0.0001")
DAILY_RETURN_TOLERANCE = Decimal("0.0001")


def _load_source(source_name: str, fund_code: str) -> tuple[pd.DataFrame | None, str | None]:
    source = AkshareFundDataSource() if source_name == "akshare" else EastmoneyFundDataSource()
    try:
        rows = source.get_fund_nav_history(fund_code)
    except Exception as exc:
        return None, str(exc)
    return rows, None


def reconcile_fund_nav(fund_code: str, limit: int = 120) -> dict:
    fund_code = fund_code.zfill(6)
    ak_rows, ak_error = _load_source("akshare", fund_code)
    em_rows, em_error = _load_source("eastmoney", fund_code)

    if ak_rows is None and em_rows is None:
        return {
            "fund_code": fund_code,
            "status": "failed",
            "summary": "两个数据源均不可用",
            "source_errors": {"akshare": ak_error, "eastmoney": em_error},
            "rows": [],
        }

    if ak_rows is None or em_rows is None:
        available = "eastmoney" if ak_rows is None else "akshare"
        return {
            "fund_code": fund_code,
            "status": "degraded",
            "summary": f"仅 {available} 数据源可用",
            "source_errors": {"akshare": ak_error, "eastmoney": em_error},
            "rows": [],
        }

    left = ak_rows[["nav_date", "unit_nav", "daily_return"]].rename(
        columns={"unit_nav": "akshare_unit_nav", "daily_return": "akshare_daily_return"}
    )
    right = em_rows[["nav_date", "unit_nav", "daily_return"]].rename(
        columns={"unit_nav": "eastmoney_unit_nav", "daily_return": "eastmoney_daily_return"}
    )
    merged = left.merge(right, on="nav_date", how="outer").sort_values("nav_date", ascending=False)
    merged = merged.head(limit).copy()
    merged["unit_nav_diff"] = (merged["akshare_unit_nav"] - merged["eastmoney_unit_nav"]).abs()
    merged["daily_return_diff"] = (
        merged["akshare_daily_return"] - merged["eastmoney_daily_return"]
    ).abs()

    ak_missing = int(merged["akshare_unit_nav"].isna().sum())
    em_missing = int(merged["eastmoney_unit_nav"].isna().sum())
    unit_diff_count = int((merged["unit_nav_diff"] > float(UNIT_NAV_TOLERANCE)).sum())
    return_diff_count = int((merged["daily_return_diff"] > float(DAILY_RETURN_TOLERANCE)).sum())
    issue_count = ak_missing + em_missing + unit_diff_count + return_diff_count

    def row_status(row: pd.Series) -> str:
        if pd.isna(row["akshare_unit_nav"]):
            return "AKShare 缺失"
        if pd.isna(row["eastmoney_unit_nav"]):
            return "Eastmoney 缺失"
        if row["unit_nav_diff"] > float(UNIT_NAV_TOLERANCE):
            return "单位净值差异"
        if row["daily_return_diff"] > float(DAILY_RETURN_TOLERANCE):
            return "日涨跌幅差异"
        return "一致"

    merged["status"] = merged.apply(row_status, axis=1)
    return {
        "fund_code": fund_code,
        "status": "ok" if issue_count == 0 else "warning",
        "summary": f"最近 {len(merged)} 条对账记录，发现 {issue_count} 个差异信号",
        "source_errors": {"akshare": ak_error, "eastmoney": em_error},
        "counts": {
            "akshare_missing": ak_missing,
            "eastmoney_missing": em_missing,
            "unit_nav_diff": unit_diff_count,
            "daily_return_diff": return_diff_count,
        },
        "rows": merged.where(pd.notna(merged), None).to_dict(orient="records"),
    }
