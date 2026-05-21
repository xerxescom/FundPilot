from app.db.session import SessionLocal, init_db
from app.services.ai.report_service import generate_daily_report


def main() -> None:
    init_db()
    with SessionLocal() as db:
        report = generate_daily_report(db)
    print(report.content)


if __name__ == "__main__":
    main()
