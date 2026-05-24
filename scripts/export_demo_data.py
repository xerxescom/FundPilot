"""Export a compact demo snapshot as JSON.

Usage:
    uv run python scripts/export_demo_data.py
"""

import json

from app.db.session import SessionLocal
from app.services import data_health_service, research_service, score_service, watchlist_service
from app.services.ai.report_service import latest_report


def main() -> None:
    with SessionLocal() as db:
        watchlist = watchlist_service.list_watchlist_items(db)
        report = latest_report(db)
        payload = {
            "watchlist": [
                {
                    "fund_code": item.fund_code,
                    "fund_name": item.fund_name,
                    "industry": item.industry,
                }
                for item in watchlist
            ],
            "top_scores": [
                {
                    "fund_code": item.fund_code,
                    "score": float(item.total_score) if item.total_score is not None else None,
                    "rating": item.rating,
                }
                for item in score_service.top_scores(db, limit=10)
            ],
            "data_health": data_health_service.data_health_overview(db),
            "industry_overview": research_service.industry_overview(db),
            "latest_report": report.content if report else None,
        }
    print(json.dumps(payload, ensure_ascii=False, default=str, indent=2))


if __name__ == "__main__":
    main()
