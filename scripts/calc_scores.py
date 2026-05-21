from app.db.session import SessionLocal, init_db
from app.services.score_service import calculate_watchlist_scores


def main() -> None:
    init_db()
    with SessionLocal() as db:
        print(calculate_watchlist_scores(db))


if __name__ == "__main__":
    main()
