from __future__ import annotations

from decimal import Decimal

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FundNav, Watchlist
from app.services.alert_service import _upsert_alert


def fund_return_matrix(db: Session) -> pd.DataFrame:
    codes = [item.fund_code for item in db.scalars(select(Watchlist).where(Watchlist.is_active.is_(True)))]
    if len(codes) < 2:
        return pd.DataFrame()
    rows = db.scalars(
        select(FundNav)
        .where(FundNav.fund_code.in_(codes), FundNav.daily_return.is_not(None))
        .order_by(FundNav.nav_date.asc())
    ).all()
    data = [
        {
            "nav_date": row.nav_date,
            "fund_code": row.fund_code,
            "daily_return": float(row.daily_return),
        }
        for row in rows
    ]
    if not data:
        return pd.DataFrame()
    return pd.DataFrame(data).pivot_table(index="nav_date", columns="fund_code", values="daily_return")


def calculate_correlation(db: Session, min_periods: int = 20) -> pd.DataFrame:
    matrix = fund_return_matrix(db)
    if matrix.empty or matrix.shape[1] < 2:
        return pd.DataFrame()
    return matrix.corr(min_periods=min_periods)


def high_correlation_pairs(db: Session, threshold: Decimal = Decimal("0.85")) -> list[dict]:
    corr = calculate_correlation(db)
    pairs = []
    if corr.empty:
        return pairs
    columns = list(corr.columns)
    for i, left in enumerate(columns):
        for right in columns[i + 1 :]:
            value = corr.loc[left, right]
            if pd.notna(value) and value >= float(threshold):
                pairs.append({"fund_a": left, "fund_b": right, "correlation": float(value)})
    return pairs


def generate_correlation_alerts(db: Session) -> list:
    alerts = []
    for pair in high_correlation_pairs(db):
        alerts.append(
            _upsert_alert(
                db,
                "high_correlation",
                pair["fund_a"],
                "medium",
                f"{pair['fund_a']} 与 {pair['fund_b']} 相关性过高",
                f"近日日收益率相关系数为 {pair['correlation']:.2f}，可能存在重复配置。",
            )
        )
    return alerts
