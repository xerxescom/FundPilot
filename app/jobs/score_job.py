from app.db.session import SessionLocal
from app.services.score_service import calculate_watchlist_scores


def calc_all_scores() -> dict[str, str]:
    with SessionLocal() as db:
        return calculate_watchlist_scores(db)
