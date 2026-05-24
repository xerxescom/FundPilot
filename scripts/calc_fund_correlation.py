"""Calculate fund correlation and generate high-correlation alerts.

Run:
    uv run python scripts/calc_fund_correlation.py
"""

from app.db.session import SessionLocal, init_db
from app.services.correlation_service import calculate_correlation, generate_correlation_alerts


def main() -> None:
    init_db()
    with SessionLocal() as db:
        corr = calculate_correlation(db)
        alerts = generate_correlation_alerts(db)
    print({} if corr.empty else corr.round(4).to_dict())
    print(f"Generated {len(alerts)} high-correlation alerts")


if __name__ == "__main__":
    main()
