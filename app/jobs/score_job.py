from app.db.session import SessionLocal
from app.services.score_service import calculate_watchlist_scores
from app.services.task_log_service import run_logged


def calc_all_scores() -> dict[str, str]:
    with SessionLocal() as db:
        return run_logged(db, "calc_scores", lambda: calculate_watchlist_scores(db))
