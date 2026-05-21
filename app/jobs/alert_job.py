from app.db.session import SessionLocal
from app.services.alert_service import generate_alerts


def generate_risk_alerts() -> int:
    with SessionLocal() as db:
        return len(generate_alerts(db))
