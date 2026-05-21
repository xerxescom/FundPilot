from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FundIndicator, FundNav, Watchlist
from app.services.nav_service import decimal_or_none


def calculate_indicators_from_nav(nav_df: pd.DataFrame, calc_date: date | None = None) -> dict:
    if nav_df.empty:
        raise ValueError("NAV data is empty")

    df = nav_df.copy()
    df["nav_date"] = pd.to_datetime(df["nav_date"])
    df["unit_nav"] = pd.to_numeric(df["unit_nav"], errors="coerce")
    df = df.dropna(subset=["nav_date", "unit_nav"]).sort_values("nav_date")
    if df.empty:
        raise ValueError("NAV data has no valid rows")

    calc_ts = pd.Timestamp(calc_date) if calc_date else df["nav_date"].max()
    current_nav = df.iloc[-1]["unit_nav"]

    def period_return(days: int) -> float | None:
        subset = df[df["nav_date"] <= calc_ts - pd.Timedelta(days=days)]
        if subset.empty or not current_nav:
            return None
        base_nav = subset.iloc[-1]["unit_nav"]
        return float(current_nav / base_nav - 1) if base_nav else None

    one_year = df[df["nav_date"] >= calc_ts - pd.Timedelta(days=365)].copy()
    returns = one_year["unit_nav"].pct_change().dropna()
    running_max = one_year["unit_nav"].cummax()
    drawdowns = one_year["unit_nav"] / running_max - 1
    volatility = float(returns.std() * np.sqrt(252)) if len(returns) > 1 else None
    annual_return = period_return(365)
    sharpe = annual_return / volatility if annual_return is not None and volatility else None
    win_rate = float((returns > 0).sum() / len(returns)) if len(returns) else None

    return {
        "calc_date": calc_ts.date(),
        "return_1w": period_return(7),
        "return_1m": period_return(30),
        "return_3m": period_return(90),
        "return_6m": period_return(180),
        "return_1y": annual_return,
        "max_drawdown_1y": float(drawdowns.min()) if not drawdowns.empty else None,
        "volatility_1y": volatility,
        "sharpe_1y": sharpe,
        "win_rate_1y": win_rate,
    }


def calculate_and_save_indicators(db: Session, fund_code: str) -> FundIndicator:
    fund_code = fund_code.zfill(6)
    rows = db.scalars(
        select(FundNav).where(FundNav.fund_code == fund_code).order_by(FundNav.nav_date.asc())
    ).all()
    nav_df = pd.DataFrame(
        [
            {
                "nav_date": row.nav_date,
                "unit_nav": float(row.unit_nav) if row.unit_nav is not None else None,
            }
            for row in rows
        ]
    )
    metrics = calculate_indicators_from_nav(nav_df)
    existing = db.scalar(
        select(FundIndicator).where(
            FundIndicator.fund_code == fund_code,
            FundIndicator.calc_date == metrics["calc_date"],
        )
    )
    values = {key: decimal_or_none(value) for key, value in metrics.items() if key != "calc_date"}
    if existing:
        for key, value in values.items():
            setattr(existing, key, value)
        indicator = existing
    else:
        indicator = FundIndicator(fund_code=fund_code, calc_date=metrics["calc_date"], **values)
        db.add(indicator)
    db.commit()
    db.refresh(indicator)
    return indicator


def latest_indicator(db: Session, fund_code: str) -> FundIndicator | None:
    return db.scalar(
        select(FundIndicator)
        .where(FundIndicator.fund_code == fund_code.zfill(6))
        .order_by(FundIndicator.calc_date.desc())
        .limit(1)
    )


def calculate_watchlist_indicators(db: Session) -> dict[str, str]:
    result = {}
    for item in db.scalars(select(Watchlist).where(Watchlist.is_active.is_(True))):
        try:
            result[item.fund_code] = str(calculate_and_save_indicators(db, item.fund_code).calc_date)
        except Exception as exc:
            result[item.fund_code] = f"failed: {exc}"
    return result
