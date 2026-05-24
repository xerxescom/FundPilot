"""Compare one fund's NAV data between AKShare and Eastmoney.

Usage:
    uv run python scripts/reconcile_fund_data.py
"""

from app.services.reconcile_service import reconcile_fund_nav


def main() -> None:
    fund_code = input("Fund code: ").strip()
    if not fund_code:
        raise SystemExit("Fund code is required")
    result = reconcile_fund_nav(fund_code)
    print(result["summary"])
    print(result["counts"] if "counts" in result else result["source_errors"])


if __name__ == "__main__":
    main()
