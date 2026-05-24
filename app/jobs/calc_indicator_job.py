from app.db.session import SessionLocal
from app.services.indicator_service import calculate_watchlist_indicators
from app.services.task_log_service import run_logged


def calc_all_indicators() -> dict[str, str]:
    with SessionLocal() as db:
        return run_logged(db, "calc_indicators", lambda: calculate_watchlist_indicators(db))
