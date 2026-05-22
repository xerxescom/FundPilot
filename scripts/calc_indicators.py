"""Calculate indicators for every active watchlist fund.

Run this after NAV data has been synced. It reads `fund_nav`, calculates
returns, drawdown, volatility, Sharpe ratio, and win rate, then stores results
in `fund_indicator`.

Run:
    uv run python scripts/calc_indicators.py
"""

from app.db.session import SessionLocal, init_db
from app.services.indicator_service import calculate_watchlist_indicators


def main() -> None:
    init_db()
    with SessionLocal() as db:
        print(calculate_watchlist_indicators(db))


if __name__ == "__main__":
    main()
