from app.db.session import SessionLocal
from app.services.ai.report_service import generate_daily_report


def generate_daily_ai_report() -> str:
    with SessionLocal() as db:
        return str(generate_daily_report(db).id)
