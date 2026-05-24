from app.db.session import SessionLocal
from app.services.ai.report_service import generate_daily_report
from app.services.task_log_service import run_logged


def generate_daily_ai_report() -> str:
    with SessionLocal() as db:
        return run_logged(db, "daily_ai_report", lambda: str(generate_daily_report(db).id))
