"""Add one fund code to the local watchlist table.

Run this before `sync_watchlist_nav.py` if you want the batch sync script to
know which funds belong to your active watchlist.

Run:
    uv run python scripts/add_watchlist.py
"""

from app.db.session import SessionLocal, init_db
from app.services.watchlist_service import add_watchlist_item


def main() -> None:
    fund_code = input("Fund code: ").strip()
    fund_name = input("Fund name (optional, auto fetched if empty): ").strip() or None
    industry = input("Industry/theme (optional): ").strip() or None
    note = input("Note (optional): ").strip() or None
    init_db()
    with SessionLocal() as db:
        item = add_watchlist_item(db, fund_code=fund_code, fund_name=fund_name, industry=industry, note=note)
    print(f"Added watchlist fund: {item.fund_code} {item.fund_name or ''}".strip())


if __name__ == "__main__":
    main()
