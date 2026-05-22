"""Sync NAV data for every active watchlist fund.

This is the manual version of the daily NAV update job. It reads active rows
from `watchlist`, fetches NAV data, and upserts rows into `fund_nav`.

Run:
    uv run python scripts/sync_watchlist_nav.py
"""

from app.db.session import SessionLocal, init_db
from app.services.nav_service import sync_watchlist_nav


def main() -> None:
    init_db()
    with SessionLocal() as db:
        result = sync_watchlist_nav(db)
    if not result:
        print("No active watchlist funds found. Run `uv run python scripts/add_watchlist.py` first.")
        return
    print(result)


if __name__ == "__main__":
    main()
