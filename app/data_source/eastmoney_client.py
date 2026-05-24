from __future__ import annotations

import pandas as pd
from loguru import logger

from app.data_source.akshare_client import AkshareFundDataSource


class EastmoneyFundDataSource(AkshareFundDataSource):
    """Eastmoney-backed fund data source using AKShare's EM endpoints.

    AKShare exposes Eastmoney fund endpoints with normalized Python APIs. Keeping
    this client separate lets the app report a distinct fallback source and makes
    future replacement with direct Eastmoney HTTP calls straightforward.
    """

    source_name = "eastmoney"

    def get_fund_nav_history(self, fund_code: str) -> pd.DataFrame:
        try:
            rows = super().get_fund_nav_history(fund_code)
        except Exception as exc:
            logger.error("Eastmoney NAV fallback failed for {}: {}", fund_code, exc)
            raise
        rows["source"] = self.source_name
        return rows

    def get_fund_info(self, fund_code: str) -> dict:
        data = super().get_fund_info(fund_code)
        data["source"] = self.source_name
        return data
