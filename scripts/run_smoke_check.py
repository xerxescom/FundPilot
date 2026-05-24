"""Run a lightweight local smoke check for FundPilot.

Usage:
    uv run python scripts/run_smoke_check.py
"""

from app.db.session import SessionLocal, init_db
from app.services import data_health_service, market_service, score_service, watchlist_service
from app.services.ai.report_service import latest_report


def main() -> None:
    init_db()
    with SessionLocal() as db:
        watchlist = watchlist_service.list_watchlist_items(db)
        scores = score_service.top_scores(db, limit=5)
        health = data_health_service.data_health_overview(db)
        market_context = market_service.latest_market_context(db)
        report = latest_report(db)
    print("database: ok")
    print(f"watchlist_count: {len(watchlist)}")
    print(f"top_score_count: {len(scores)}")
    print(f"data_health_status: {health['status_counts']}")
    print(f"market_context_count: {len(market_context)}")
    print(f"latest_report: {report.created_at if report else 'none'}")


if __name__ == "__main__":
    main()
