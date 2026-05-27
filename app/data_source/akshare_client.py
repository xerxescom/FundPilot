from __future__ import annotations

import pandas as pd
from loguru import logger

from app.data_source.base import FundDataSource
from app.services.fund_profile_service import infer_tracking_index


class AkshareFundDataSource(FundDataSource):
    source_name = "akshare"

    def get_fund_info(self, fund_code: str) -> dict:
        fund_code = fund_code.zfill(6)
        try:
            import akshare as ak

            rows = ak.fund_name_em()
            code_col = self._pick_column(rows, ["基金代码", "fund_code", "代码"])
            name_col = self._pick_column(rows, ["基金简称", "基金名称", "name"])
            type_col = self._pick_optional_column(rows, ["基金类型", "类型"])
            match = rows[rows[code_col].astype(str).str.zfill(6) == fund_code]
            if match.empty:
                raise ValueError(f"Fund code not found: {fund_code}")
            row = match.iloc[0]
            return {
                "fund_code": fund_code,
                "fund_name": str(row.get(name_col, fund_code)),
                "fund_type": str(row.get(type_col, "")) if type_col else None,
                "tracking_index": infer_tracking_index(str(row.get(name_col, fund_code)), str(row.get(type_col, "")) if type_col else None),
                "source": self.source_name,
            }
        except Exception as exc:
            logger.warning("Failed to fetch fund info for {}: {}", fund_code, exc)
            return {
                "fund_code": fund_code,
                "fund_name": fund_code,
                "fund_type": None,
                "tracking_index": None,
                "source": self.source_name,
            }

    def get_fund_nav_history(self, fund_code: str) -> pd.DataFrame:
        fund_code = fund_code.zfill(6)
        try:
            import akshare as ak

            raw = ak.fund_open_fund_info_em(symbol=fund_code, indicator="单位净值走势")
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
                "fund_code": fund_code,
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

    def get_fund_holding_industries(self, fund_code: str) -> pd.DataFrame:
        stocks = self.get_fund_holding_stocks(fund_code)
        if stocks.empty or "industry" not in stocks.columns or stocks["industry"].isna().all():
            return pd.DataFrame()
        rows = stocks.dropna(subset=["industry", "weight"])
        grouped = rows.groupby(["fund_code", "report_date", "industry", "source"], as_index=False)["weight"].sum()
        return grouped.sort_values("weight", ascending=False).reset_index(drop=True)

    def get_fund_holding_stocks(self, fund_code: str) -> pd.DataFrame:
        fund_code = fund_code.zfill(6)
        try:
            import akshare as ak
        except Exception as exc:
            logger.warning("Failed to import akshare for fund holdings {}: {}", fund_code, exc)
            return pd.DataFrame()

        frames: list[pd.DataFrame] = []
        for year in range(pd.Timestamp.today().year, pd.Timestamp.today().year - 3, -1):
            try:
                raw = ak.fund_portfolio_hold_em(symbol=fund_code, date=str(year))
            except Exception as exc:
                logger.warning("Failed to fetch fund holdings for {} {}: {}", fund_code, year, exc)
                continue
            if raw is None or raw.empty:
                continue
            code_col = self._pick_optional_column(raw, ["股票代码", "证券代码", "代码", "stock_code"])
            name_col = self._pick_optional_column(raw, ["股票名称", "证券名称", "名称", "stock_name"])
            industry_col = self._pick_optional_column(raw, ["行业", "所属行业", "申万行业", "industry"])
            weight_col = self._pick_optional_column(raw, ["占净值比例", "持仓占比", "占比", "weight"])
            report_col = self._pick_optional_column(raw, ["季度", "报告期", "报告日期", "date"])
            if not code_col or not name_col or not weight_col:
                continue
            frame = pd.DataFrame(
                {
                    "fund_code": fund_code,
                    "stock_code": raw[code_col].astype(str).str.extract(r"(\d+)", expand=False).fillna(raw[code_col].astype(str)),
                    "stock_name": raw[name_col].astype(str),
                    "industry": raw[industry_col].astype(str) if industry_col else None,
                    "weight": self._normalize_return(raw[weight_col]),
                    "report_date": pd.to_datetime(raw[report_col], errors="coerce").dt.date if report_col else None,
                    "source": self.source_name,
                }
            )
            frames.append(frame)

        if not frames:
            return pd.DataFrame()
        rows = pd.concat(frames, ignore_index=True)
        rows = rows.dropna(subset=["industry", "weight"])
        if rows.empty:
            return pd.DataFrame()
        if "report_date" not in rows.columns or rows["report_date"].isna().all():
            rows["report_date"] = pd.Timestamp.today().date()
        latest_date = rows["report_date"].dropna().max()
        latest = rows[rows["report_date"] == latest_date]
        return latest.sort_values("weight", ascending=False).head(10).reset_index(drop=True)

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

    def get_market_index_valuation(self, index_code: str, index_name: str) -> pd.DataFrame:
        symbol_map = {
            "sh000300": "沪深300",
            "sh000905": "中证500",
            "sh000852": "中证1000",
            "sz399006": "创业板",
            "sh000016": "上证50",
            "sh000001": "上证",
            "sh000688": "科创50",
            "sh000932": "中证消费",
            "sh000933": "中证医药",
            "sh000993": "全指信息",
            "sh000819": "中证有色",
            "sh000813": "细分化工",
            "sz399808": "中证新能源",
            "sz399976": "CS新能车",
            "sz399986": "中证银行",
            "sz399975": "证券公司",
            "sz399967": "中证军工",
            "sz399971": "中证传媒",
            "sz399998": "中证煤炭",
            "sz399997": "中证白酒",
        }
        symbol = symbol_map.get(index_code, index_name)
        try:
            import akshare as ak

            raw = ak.stock_index_pe_lg(symbol=symbol)
        except Exception as exc:
            logger.warning("Failed to fetch market valuation for {} {}: {}", index_code, symbol, exc)
            return pd.DataFrame()
        if raw is None or raw.empty:
            return pd.DataFrame()

        date_col = self._pick_column(raw, ["日期", "date"])
        pe_col = self._pick_column(raw, ["滚动市盈率", "PE_TTM", "pe_ttm"])
        df = pd.DataFrame(
            {
                "index_code": index_code,
                "index_name": index_name,
                "trade_date": pd.to_datetime(raw[date_col], errors="coerce").dt.date,
                "pe_ttm": pd.to_numeric(raw[pe_col], errors="coerce"),
                "source": self.source_name,
            }
        )
        df = df.dropna(subset=["trade_date", "pe_ttm"]).drop_duplicates(["index_code", "trade_date"])
        df = df.sort_values("trade_date").reset_index(drop=True)
        df["pe_percentile"] = df["pe_ttm"].rank(pct=True)
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
        max_abs = numeric.abs().max(skipna=True)
        if pd.notna(max_abs) and max_abs > 1:
            numeric = numeric / 100
        return numeric
