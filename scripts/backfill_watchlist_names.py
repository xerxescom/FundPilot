"""Backfill missing fund names in the watchlist table.

Use this after upgrading from an older local database that only stored
`fund_code` in `watchlist`.

Run:
    uv run python scripts/backfill_watchlist_names.py
"""

from app.data_source.akshare_client import AkshareFundDataSource
from app.db.models import Watchlist
from app.db.session import SessionLocal, init_db


def main() -> None:
    init_db()
    source = AkshareFundDataSource()
    updated = 0
    with SessionLocal() as db:
        items = db.query(Watchlist).filter(Watchlist.fund_name.is_(None)).all()
        for item in items:
            item.fund_name = source.get_fund_info(item.fund_code).get("fund_name")
            updated += 1
        db.commit()
    print(f"Backfilled {updated} watchlist fund names")


if __name__ == "__main__":
    main()
