from __future__ import annotations

from decimal import Decimal

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data_source.akshare_client import AkshareFundDataSource
from app.db.models import AssetInfo, AssetPriceDaily


LISTED_ASSET_TYPES = {"stock", "etf"}


def normalize_asset_code(asset_code: str, asset_type: str) -> str:
    code = str(asset_code).strip().upper()
    if asset_type == "fund":
        return code.zfill(6)
    digits = "".join(char for char in code if char.isdigit())
    return digits or code


def get_asset(db: Session, asset_code: str) -> AssetInfo | None:
    return db.scalar(select(AssetInfo).where(AssetInfo.asset_code == asset_code))


def list_assets(db: Session, asset_type: str | None = None) -> list[AssetInfo]:
    stmt = select(AssetInfo).order_by(AssetInfo.asset_type, AssetInfo.asset_code)
    if asset_type:
        stmt = stmt.where(AssetInfo.asset_type == asset_type)
    return list(db.scalars(stmt))


def sync_listed_asset(db: Session, asset_code: str, asset_type: str = "stock") -> dict:
    if asset_type not in LISTED_ASSET_TYPES:
        raise ValueError("asset_type must be stock or etf")
    code = normalize_asset_code(asset_code, asset_type)
    source = AkshareFundDataSource()
    info_data = source.get_asset_info(code, asset_type)
    prices = source.get_asset_price_history(code, asset_type)

    asset = get_asset(db, code)
    if asset is None:
        asset = AssetInfo(**info_data)
        db.add(asset)
    else:
        for key, value in info_data.items():
            if value is not None:
                setattr(asset, key, value)

    synced_rows = _upsert_prices(db, prices)
    db.commit()
    db.refresh(asset)
    return {"asset": asset, "synced_rows": synced_rows, "latest_price_date": _latest_price_date(db, code)}


def price_history(db: Session, asset_code: str) -> list[AssetPriceDaily]:
    return list(
        db.scalars(
            select(AssetPriceDaily)
            .where(AssetPriceDaily.asset_code == asset_code)
            .order_by(AssetPriceDaily.price_date.asc())
        )
    )


def latest_price(db: Session, asset_code: str) -> AssetPriceDaily | None:
    return db.scalar(
        select(AssetPriceDaily)
        .where(AssetPriceDaily.asset_code == asset_code)
        .order_by(AssetPriceDaily.price_date.desc())
        .limit(1)
    )


def _latest_price_date(db: Session, asset_code: str):
    latest = latest_price(db, asset_code)
    return latest.price_date if latest else None


def _upsert_prices(db: Session, prices: pd.DataFrame) -> int:
    rows = prices.to_dict("records") if not prices.empty else []
    if not rows:
        return 0
    code = str(rows[0]["asset_code"])
    dates = [row["price_date"] for row in rows]
    existing = {
        item.price_date: item
        for item in db.scalars(
            select(AssetPriceDaily).where(
                AssetPriceDaily.asset_code == code,
                AssetPriceDaily.price_date.in_(dates),
            )
        )
    }
    for row in rows:
        values = {
            "asset_code": code,
            "price_date": row["price_date"],
            "close": _decimal_or_none(row.get("close")),
            "daily_return": _decimal_or_none(row.get("daily_return")),
            "source": row.get("source"),
        }
        item = existing.get(values["price_date"])
        if item:
            for key, value in values.items():
                setattr(item, key, value)
        else:
            db.add(AssetPriceDaily(**values))
    return len(rows)


def _decimal_or_none(value: object) -> Decimal | None:
    if value is None or pd.isna(value):
        return None
    return Decimal(str(value))
