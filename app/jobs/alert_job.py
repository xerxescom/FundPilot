from app.db.session import SessionLocal
from app.services.alert_service import generate_alerts
from app.services.task_log_service import run_logged


def generate_risk_alerts() -> int:
    with SessionLocal() as db:
        return run_logged(db, "risk_alerts", lambda: len(generate_alerts(db)))
