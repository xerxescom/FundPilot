"""Print the current portfolio overview.

Run:
    uv run python scripts/calc_portfolio_risk.py
"""

from app.db.session import SessionLocal, init_db
from app.services.portfolio_service import portfolio_overview


def main() -> None:
    init_db()
    with SessionLocal() as db:
        overview = portfolio_overview(db)
    print(
        {
            "total_value": str(overview["total_value"]),
            "total_cost": str(overview["total_cost"]),
            "profit_amount": str(overview["profit_amount"]),
            "profit_rate": str(overview["profit_rate"]),
            "position_count": len(overview["positions"]),
        }
    )


if __name__ == "__main__":
    main()
