"""Calculate scores for every active watchlist fund.

Run this after indicators have been calculated. It reads `fund_indicator`,
applies the rule-based scoring model, and stores results in `fund_score`.

Run:
    uv run python scripts/calc_scores.py
"""

from app.db.session import SessionLocal, init_db
from app.services.score_service import calculate_watchlist_scores


def main() -> None:
    init_db()
    with SessionLocal() as db:
        print(calculate_watchlist_scores(db))


if __name__ == "__main__":
    main()
