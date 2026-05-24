from app.db.session import SessionLocal
from app.services.nav_service import sync_watchlist_nav
from app.services.task_log_service import run_logged


def update_fund_nav() -> dict[str, int | str]:
    with SessionLocal() as db:
        return run_logged(db, "update_fund_nav", lambda: sync_watchlist_nav(db))
