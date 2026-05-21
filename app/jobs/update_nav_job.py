from app.db.session import SessionLocal
from app.services.nav_service import sync_watchlist_nav


def update_fund_nav() -> dict[str, int | str]:
    with SessionLocal() as db:
        return sync_watchlist_nav(db)
