from app.db.session import SessionLocal, init_db
from app.services.nav_service import sync_fund_nav


def main() -> None:
    fund_code = input("Fund code: ").strip()
    init_db()
    with SessionLocal() as db:
        count = sync_fund_nav(db, fund_code)
    print(f"Synced {count} NAV rows for {fund_code.zfill(6)}")


if __name__ == "__main__":
    main()
