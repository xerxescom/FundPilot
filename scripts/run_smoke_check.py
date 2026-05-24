"""Run a lightweight local smoke check for FundPilot.

Usage:
    uv run python scripts/run_smoke_check.py
"""

from sqlalchemy import select

from app.db.models import FundIndicator, FundNav
from app.db.session import SessionLocal, init_db
from app.services import data_health_service, market_service, score_service, watchlist_service
from app.services.ai.report_service import latest_report


def _status(ok: bool) -> str:
    return "ok" if ok else "missing"


def main() -> None:
    init_db()
    with SessionLocal() as db:
        watchlist = watchlist_service.list_watchlist_items(db)
        nav_count = db.scalar(select(FundNav).limit(1)) is not None
        indicator_count = db.scalar(select(FundIndicator).limit(1)) is not None
        scores = score_service.top_scores(db, limit=5)
        health = data_health_service.data_health_overview(db)
        market_context = market_service.latest_market_context(db)
        report = latest_report(db)

    print("FundPilot smoke check")
    print("=====================")
    print("database: ok")
    print(f"watchlist: {_status(bool(watchlist))} ({len(watchlist)} active/known)")
    print(f"fund_nav: {_status(nav_count)}")
    print(f"indicators: {_status(indicator_count)}")
    print(f"scores: {_status(bool(scores))} ({len(scores)} top rows)")
    print(f"market_context: {_status(bool(market_context))} ({len(market_context)} indexes)")
    print(f"data_health: {health['status_counts']}")
    print(f"latest_report: {report.created_at if report else 'missing'}")


if __name__ == "__main__":
    main()
