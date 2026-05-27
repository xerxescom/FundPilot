from __future__ import annotations

from app.db.models import FundInfo, Watchlist


TRACKING_INDEX_ALIASES: list[tuple[tuple[str, ...], str]] = [
    (("沪深300", "HS300"), "沪深300"),
    (("中证500", "ZZ500"), "中证500"),
    (("中证1000", "ZZ1000"), "中证1000"),
    (("创业板", "创业板指"), "创业板指"),
    (("上证50",), "上证50"),
    (("上证指数", "上证综指"), "上证指数"),
    (("科创50",), "科创50"),
    (("恒生科技",), "恒生科技"),
    (("恒生指数", "恒生"), "恒生指数"),
    (("纳斯达克100", "纳指100", "NASDAQ100"), "纳斯达克100"),
    (("标普500", "S&P500", "SP500"), "标普500"),
]

VALUATION_INDEX_MAP = {
    "沪深300": ("sh000300", "沪深300"),
    "中证500": ("sh000905", "中证500"),
    "中证1000": ("sh000852", "中证1000"),
    "创业板指": ("sz399006", "创业板指"),
    "上证50": ("sh000016", "上证50"),
    "上证指数": ("sh000001", "上证指数"),
    "科创50": ("sh000688", "科创50"),
}

INDUSTRY_VALUATION_FALLBACK = {
    "宽基": ("sh000300", "沪深300"),
    "指数": ("sh000300", "沪深300"),
    "科技": ("sz399006", "创业板指"),
    "新能源": ("sz399006", "创业板指"),
    "新能源车": ("sz399006", "创业板指"),
    "医药": ("sh000300", "沪深300"),
    "消费": ("sh000300", "沪深300"),
    "金融": ("sh000300", "沪深300"),
    "周期": ("sh000300", "沪深300"),
    "混合": ("sh000300", "沪深300"),
}

OFFSHORE_INDEXES = {"恒生科技", "恒生指数", "纳斯达克100", "标普500"}

INDUSTRY_KEYWORDS = {
    "医药": "医药",
    "医疗": "医药",
    "生物": "医药",
    "消费": "消费",
    "白酒": "消费",
    "食品": "消费",
    "科技": "科技",
    "芯片": "科技",
    "半导体": "科技",
    "人工智能": "科技",
    "新能源": "新能源",
    "光伏": "新能源",
    "电池": "新能源",
    "汽车": "新能源车",
    "金融": "金融",
    "银行": "金融",
    "证券": "金融",
    "煤炭": "周期",
    "钢铁": "周期",
    "有色": "周期",
    "黄金": "黄金",
    "红利": "红利",
    "沪深300": "宽基",
    "中证500": "宽基",
    "中证1000": "宽基",
    "创业板": "宽基",
    "科创": "宽基",
}


def infer_tracking_index(fund_name: str | None, fund_type: str | None = None) -> str | None:
    text = f"{fund_name or ''} {fund_type or ''}".upper()
    for aliases, canonical in TRACKING_INDEX_ALIASES:
        if any(alias.upper() in text for alias in aliases):
            return canonical
    return None


def infer_profile_industry(fund_name: str | None, fund_type: str | None = None) -> str | None:
    text = f"{fund_name or ''} {fund_type or ''}"
    for keyword, label in INDUSTRY_KEYWORDS.items():
        if keyword in text:
            return label
    if "债" in text:
        return "债券"
    if "货币" in text:
        return "货币"
    if "QDII" in text.upper():
        return "海外/QDII"
    if "指数" in text or "ETF" in text.upper():
        return "指数"
    if "混合" in text:
        return "混合"
    return fund_type


def ensure_tracking_index(fund: FundInfo | None) -> str | None:
    if not fund:
        return None
    if fund.tracking_index:
        return fund.tracking_index
    tracking_index = infer_tracking_index(fund.fund_name, fund.fund_type)
    if tracking_index:
        fund.tracking_index = tracking_index
    return tracking_index


def match_valuation_index(fund: FundInfo | None, watchlist: Watchlist | None = None) -> dict:
    tracking_index = ensure_tracking_index(fund)
    if tracking_index in OFFSHORE_INDEXES:
        return {
            "tracking_index": tracking_index,
            "valuation_index_code": None,
            "valuation_index_name": None,
            "industry_exposure_source": "tracking_index",
            "industry_exposure": tracking_index,
        }
    if tracking_index in VALUATION_INDEX_MAP:
        code, name = VALUATION_INDEX_MAP[tracking_index]
        return {
            "tracking_index": tracking_index,
            "valuation_index_code": code,
            "valuation_index_name": name,
            "industry_exposure_source": "tracking_index",
            "industry_exposure": tracking_index,
        }

    industry = watchlist.industry if watchlist and watchlist.industry else infer_profile_industry(
        fund.fund_name if fund else None,
        fund.fund_type if fund else None,
    )
    if industry in INDUSTRY_VALUATION_FALLBACK:
        code, name = INDUSTRY_VALUATION_FALLBACK[industry]
        return {
            "tracking_index": tracking_index,
            "valuation_index_code": code,
            "valuation_index_name": name,
            "industry_exposure_source": "name_inference",
            "industry_exposure": industry,
        }
    return {
        "tracking_index": tracking_index,
        "valuation_index_code": None,
        "valuation_index_name": None,
        "industry_exposure_source": "name_inference" if industry else None,
        "industry_exposure": industry,
    }
