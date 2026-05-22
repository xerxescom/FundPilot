"""Generate a daily fund report.

This collects watchlist, score, and alert data, then asks Ollama for a report.
If Ollama is unavailable, it writes a rule-based fallback report instead.

Run:
    uv run python scripts/generate_daily_report.py
"""

from app.db.session import SessionLocal, init_db
from app.services.ai.report_service import generate_daily_report


def main() -> None:
    init_db()
    with SessionLocal() as db:
        report = generate_daily_report(db)
    print(report.content)


if __name__ == "__main__":
    main()
