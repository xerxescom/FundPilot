from app.db.session import SessionLocal, init_db
from app.services.alert_service import generate_alerts


def main() -> None:
    init_db()
    with SessionLocal() as db:
        alerts = generate_alerts(db)
    print(f"Generated or updated {len(alerts)} alerts")


if __name__ == "__main__":
    main()
