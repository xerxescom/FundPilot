from app.db.session import SessionLocal
from app.services.indicator_service import calculate_watchlist_indicators


def calc_all_indicators() -> dict[str, str]:
    with SessionLocal() as db:
        return calculate_watchlist_indicators(db)
