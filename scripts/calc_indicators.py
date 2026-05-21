from app.db.session import SessionLocal, init_db
from app.services.indicator_service import calculate_watchlist_indicators


def main() -> None:
    init_db()
    with SessionLocal() as db:
        print(calculate_watchlist_indicators(db))


if __name__ == "__main__":
    main()
