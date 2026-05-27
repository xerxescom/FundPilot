from abc import ABC, abstractmethod

import pandas as pd


class FundDataSource(ABC):
    @abstractmethod
    def get_fund_info(self, fund_code: str) -> dict:
        raise NotImplementedError

    @abstractmethod
    def get_fund_nav_history(self, fund_code: str) -> pd.DataFrame:
        raise NotImplementedError

    @abstractmethod
    def get_fund_rank_list(self) -> pd.DataFrame:
        raise NotImplementedError

    @abstractmethod
    def get_fund_holding_industries(self, fund_code: str) -> pd.DataFrame:
        raise NotImplementedError

    @abstractmethod
    def get_fund_holding_stocks(self, fund_code: str) -> pd.DataFrame:
        raise NotImplementedError

    @abstractmethod
    def get_market_index_history(self, index_code: str) -> pd.DataFrame:
        raise NotImplementedError

    @abstractmethod
    def get_market_index_valuation(self, index_code: str, index_name: str) -> pd.DataFrame:
        raise NotImplementedError
