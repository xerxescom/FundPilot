"""Sync market index context data.

Fetches major index history with AKShare and stores it in `market_index_daily`.

Run:
    uv run python scripts/sync_market_context.py
"""

from app.db.session import SessionLocal, init_db
from app.services.market_service import sync_market_context


def main() -> None:
    init_db()
    with SessionLocal() as db:
        print(sync_market_context(db))


if __name__ == "__main__":
    main()
