from app.db.session import SessionLocal
from app.services.market_service import sync_market_context


def sync_daily_market_context() -> dict[str, int | str]:
    with SessionLocal() as db:
        return sync_market_context(db)
