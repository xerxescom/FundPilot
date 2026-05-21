from app.db.session import SessionLocal, init_db
from app.services.nav_service import sync_watchlist_nav


def main() -> None:
    init_db()
    with SessionLocal() as db:
        print(sync_watchlist_nav(db))


if __name__ == "__main__":
    main()
