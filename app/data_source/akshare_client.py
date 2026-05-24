from __future__ import annotations

import pandas as pd
from loguru import logger

from app.data_source.base import FundDataSource


class AkshareFundDataSource(FundDataSource):
    source_name = "akshare"

    def get_fund_info(self, fund_code: str) -> dict:
        try:
            import akshare as ak

            rows = ak.fund_name_em()
            code_col = self._pick_column(rows, ["基金代码", "fund_code", "代码"])
            name_col = self._pick_column(rows, ["基金简称", "基金名称", "name"])
            type_col = self._pick_column(rows, ["基金类型", "类型"])
            match = rows[rows[code_col].astype(str).str.zfill(6) == fund_code.zfill(6)]
            if match.empty:
                raise ValueError(f"Fund code not found: {fund_code}")
            row = match.iloc[0]
            return {
                "fund_code": fund_code.zfill(6),
                "fund_name": str(row.get(name_col, fund_code)),
                "fund_type": str(row.get(type_col, "")) or None,
                "source": self.source_name,
            }
        except Exception as exc:
            logger.warning("Failed to fetch fund info for {}: {}", fund_code, exc)
            return {
                "fund_code": fund_code.zfill(6),
                "fund_name": fund_code.zfill(6),
                "fund_type": None,
                "source": self.source_name,
            }

    def get_fund_nav_history(self, fund_code: str) -> pd.DataFrame:
        try:
            import akshare as ak

            raw = ak.fund_open_fund_info_em(symbol=fund_code.zfill(6), indicator="单位净值走势")
        except Exception as exc:
            logger.error("Failed to fetch NAV history for {}: {}", fund_code, exc)
            raise ValueError(f"Failed to fetch NAV history for {fund_code}") from exc

        if raw is None or raw.empty:
            raise ValueError(f"No NAV history returned for {fund_code}")

        date_col = self._pick_column(raw, ["净值日期", "日期", "x"])
        unit_col = self._pick_column(raw, ["单位净值", "净值", "y"])
        return_col = self._pick_optional_column(raw, ["日增长率", "日涨跌幅", "涨跌幅"])
        acc_col = self._pick_optional_column(raw, ["累计净值"])

        df = pd.DataFrame(
            {
                "fund_code": fund_code.zfill(6),
                "nav_date": pd.to_datetime(raw[date_col], errors="coerce").dt.date,
                "unit_nav": pd.to_numeric(raw[unit_col], errors="coerce"),
                "accumulated_nav": pd.to_numeric(raw[acc_col], errors="coerce") if acc_col else None,
                "daily_return": self._normalize_return(raw[return_col]) if return_col else None,
                "source": self.source_name,
            }
        )
        df = df.dropna(subset=["nav_date", "unit_nav"]).drop_duplicates(["fund_code", "nav_date"])
        return df.sort_values("nav_date").reset_index(drop=True)

    def get_fund_rank_list(self) -> pd.DataFrame:
        try:
            import akshare as ak

            return ak.fund_open_fund_rank_em(symbol="全部")
        except Exception as exc:
            logger.warning("Failed to fetch fund rank list: {}", exc)
            return pd.DataFrame()

    def get_market_index_history(self, index_code: str) -> pd.DataFrame:
        try:
            import akshare as ak

            raw = ak.stock_zh_index_daily(symbol=index_code)
        except Exception as exc:
            logger.error("Failed to fetch market index history for {}: {}", index_code, exc)
            raise ValueError(f"Failed to fetch market index history for {index_code}") from exc

        if raw is None or raw.empty:
            raise ValueError(f"No market index history returned for {index_code}")

        date_col = self._pick_column(raw, ["date", "日期"])
        close_col = self._pick_column(raw, ["close", "收盘"])
        df = pd.DataFrame(
            {
                "index_code": index_code,
                "trade_date": pd.to_datetime(raw[date_col], errors="coerce").dt.date,
                "close": pd.to_numeric(raw[close_col], errors="coerce"),
                "source": self.source_name,
            }
        )
        df = df.dropna(subset=["trade_date", "close"]).drop_duplicates(["index_code", "trade_date"])
        df = df.sort_values("trade_date").reset_index(drop=True)
        df["daily_return"] = df["close"].pct_change()
        return df

    @staticmethod
    def _pick_column(df: pd.DataFrame, candidates: list[str]) -> str:
        col = AkshareFundDataSource._pick_optional_column(df, candidates)
        if not col:
            raise ValueError(f"None of columns {candidates} found in {list(df.columns)}")
        return col

    @staticmethod
    def _pick_optional_column(df: pd.DataFrame, candidates: list[str]) -> str | None:
        for col in candidates:
            if col in df.columns:
                return col
        return None

    @staticmethod
    def _normalize_return(series: pd.Series) -> pd.Series:
        values = series.astype(str).str.replace("%", "", regex=False)
        numeric = pd.to_numeric(values, errors="coerce")
        if numeric.abs().max(skipna=True) and numeric.abs().max(skipna=True) > 1:
            numeric = numeric / 100
        return numeric
