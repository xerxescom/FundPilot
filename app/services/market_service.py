from __future__ import annotations

from datetime import date

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data_source.akshare_client import AkshareFundDataSource
from app.db.models import MarketIndexDaily
from app.services.nav_service import decimal_or_none
from app.services.task_log_service import run_logged

DEFAULT_MARKET_INDEXES = {
    "sh000300": "沪深300",
    "sh000905": "中证500",
    "sz399006": "创业板指",
    "sh000001": "上证指数",
}


def upsert_market_rows(db: Session, index_name: str, rows: pd.DataFrame) -> int:
    count = 0
    for _, row in rows.iterrows():
        index_code = str(row["index_code"])
        trade_date: date = row["trade_date"]
        existing = db.scalar(
            select(MarketIndexDaily).where(
                MarketIndexDaily.index_code == index_code,
                MarketIndexDaily.trade_date == trade_date,
            )
        )
        values = {
            "index_name": index_name,
            "close": decimal_or_none(row.get("close"), "0.0001"),
            "daily_return": decimal_or_none(row.get("daily_return")),
            "source": row.get("source"),
        }
        if existing:
            for key, value in values.items():
                setattr(existing, key, value)
        else:
            db.add(MarketIndexDaily(index_code=index_code, trade_date=trade_date, **values))
        count += 1
    db.commit()
    return count


def sync_market_index(db: Session, index_code: str, index_name: str) -> int:
    rows = AkshareFundDataSource().get_market_index_history(index_code)
    return upsert_market_rows(db, index_name, rows)


def sync_market_context(db: Session) -> dict[str, int | str]:
    def _sync() -> dict[str, int | str]:
        result: dict[str, int | str] = {}
        for index_code, index_name in DEFAULT_MARKET_INDEXES.items():
            try:
                result[index_code] = sync_market_index(db, index_code, index_name)
            except Exception as exc:
                result[index_code] = f"failed: {exc}"
        return result

    return run_logged(db, "sync_market_context", _sync)


def latest_market_context(db: Session) -> list[dict]:
    context = []
    for index_code, index_name in DEFAULT_MARKET_INDEXES.items():
        rows = list(
            db.scalars(
                select(MarketIndexDaily)
                .where(MarketIndexDaily.index_code == index_code)
                .order_by(MarketIndexDaily.trade_date.desc())
                .limit(60)
            )
        )
        if not rows:
            context.append(
                {
                    "index_code": index_code,
                    "index_name": index_name,
                    "trade_date": None,
                    "close": None,
                    "daily_return": None,
                    "return_1m": None,
                    "source": None,
                }
            )
            continue
        latest = rows[0]
        oldest = rows[-1]
        return_1m = (
            float(latest.close / oldest.close - 1)
            if latest.close is not None and oldest.close is not None and oldest.close
            else None
        )
        context.append(
            {
                "index_code": latest.index_code,
                "index_name": latest.index_name,
                "trade_date": latest.trade_date,
                "close": float(latest.close) if latest.close is not None else None,
                "daily_return": float(latest.daily_return) if latest.daily_return is not None else None,
                "return_1m": return_1m,
                "source": latest.source,
            }
        )
    return context
