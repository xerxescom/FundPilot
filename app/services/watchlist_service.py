from sqlalchemy import select
from sqlalchemy.orm import Session

from app.data_source.akshare_client import AkshareFundDataSource
from app.db.models import Watchlist


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
    "地产": "地产",
    "军工": "军工",
    "传媒": "传媒",
    "农业": "农业",
    "煤炭": "周期",
    "钢铁": "周期",
    "有色": "周期",
    "黄金": "黄金",
    "红利": "红利",
    "纳斯达克": "海外/QDII",
    "标普": "海外/QDII",
    "恒生": "港股",
    "沪深300": "宽基",
    "中证500": "宽基",
    "中证1000": "宽基",
    "创业板": "宽基",
    "科创": "宽基",
}


def infer_industry(fund_name: str | None, fund_type: str | None = None) -> str | None:
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


def add_watchlist_item(
    db: Session,
    fund_code: str,
    group_name: str = "default",
    note: str | None = None,
    fund_name: str | None = None,
    industry: str | None = None,
) -> Watchlist:
    fund_code = fund_code.zfill(6)
    fund_info = AkshareFundDataSource().get_fund_info(fund_code)
    if not fund_name:
        fund_name = fund_info.get("fund_name")
    if not industry:
        industry = infer_industry(fund_name, fund_info.get("fund_type"))
    item = db.scalar(
        select(Watchlist).where(
            Watchlist.fund_code == fund_code,
            Watchlist.group_name == group_name,
        )
    )
    if item:
        item.is_active = True
        item.fund_name = fund_name or item.fund_name
        item.industry = industry or item.industry
        item.note = note
    else:
        item = Watchlist(
            fund_code=fund_code,
            fund_name=fund_name,
            industry=industry,
            group_name=group_name,
            note=note,
            is_active=True,
        )
        db.add(item)
    db.commit()
    db.refresh(item)
    return item


def list_watchlist_items(db: Session, active_only: bool = True) -> list[Watchlist]:
    stmt = select(Watchlist).order_by(Watchlist.created_at.desc())
    if active_only:
        stmt = stmt.where(Watchlist.is_active.is_(True))
    return list(db.scalars(stmt))


def remove_watchlist_item(db: Session, fund_code: str, group_name: str = "default") -> bool:
    item = db.scalar(
        select(Watchlist).where(
            Watchlist.fund_code == fund_code.zfill(6),
            Watchlist.group_name == group_name,
            Watchlist.is_active.is_(True),
        )
    )
    if not item:
        return False
    item.is_active = False
    db.commit()
    return True
