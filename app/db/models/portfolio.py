from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Date, DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class PortfolioPosition(Base):
    __tablename__ = "portfolio_position"

    id: Mapped[int] = mapped_column(primary_key=True)
    fund_code: Mapped[str] = mapped_column(String(20), index=True)
    asset_type: Mapped[str] = mapped_column(String(20), default="fund", server_default="fund", index=True)
    asset_code: Mapped[str | None] = mapped_column(String(30), index=True)
    holding_amount: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    holding_share: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    cost_nav: Mapped[Decimal | None] = mapped_column(Numeric(20, 6))
    buy_date: Mapped[date | None] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), onupdate=func.now())


class PortfolioTransaction(Base):
    __tablename__ = "portfolio_transaction"

    id: Mapped[int] = mapped_column(primary_key=True)
    fund_code: Mapped[str] = mapped_column(String(20), index=True)
    asset_type: Mapped[str] = mapped_column(String(20), default="fund", server_default="fund", index=True)
    asset_code: Mapped[str | None] = mapped_column(String(30), index=True)
    trade_date: Mapped[date] = mapped_column(Date, index=True)
    trade_type: Mapped[str] = mapped_column(String(20), default="buy")
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    nav: Mapped[Decimal] = mapped_column(Numeric(20, 6))
    share: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    fee: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    note: Mapped[str | None] = mapped_column(Text)
    # 外部引用（券商编号或内容哈希）。唯一索引；NULL 互不冲突，手工/期初流水留空。
    external_ref: Mapped[str | None] = mapped_column(String(120), unique=True, index=True)
    # manual / opening / citic_delivery / citic_statement
    source: Mapped[str | None] = mapped_column(String(30))
    import_batch_id: Mapped[int | None] = mapped_column(Integer, index=True)
    # 卖出时的已实现盈亏，由账本重放确定性写入
    realized_pnl: Mapped[Decimal | None] = mapped_column(Numeric(20, 4))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PortfolioCashEvent(Base):
    """账户级现金事件：出入金、分红、利息、费用、调整与期初现金。金额带符号。"""

    __tablename__ = "portfolio_cash_event"

    id: Mapped[int] = mapped_column(primary_key=True)
    event_date: Mapped[date] = mapped_column(Date, index=True)
    event_type: Mapped[str] = mapped_column(String(20), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(20, 4))
    asset_type: Mapped[str | None] = mapped_column(String(20))
    asset_code: Mapped[str | None] = mapped_column(String(30))
    note: Mapped[str | None] = mapped_column(Text)
    source: Mapped[str] = mapped_column(String(20), default="manual")
    external_ref: Mapped[str | None] = mapped_column(String(120), unique=True, index=True)
    import_batch_id: Mapped[int | None] = mapped_column(Integer, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class PortfolioImportBatch(Base):
    """一次 CSV 导入的批次记录：文件指纹、使用的映射、行计数与错误明细。"""

    __tablename__ = "portfolio_import_batch"

    id: Mapped[int] = mapped_column(primary_key=True)
    source_kind: Mapped[str] = mapped_column(String(30))
    file_name: Mapped[str | None] = mapped_column(String(255))
    file_hash: Mapped[str | None] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(20), index=True, default="previewed")
    mapping_json: Mapped[Any | None] = mapped_column(JSON)
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    imported_count: Mapped[int] = mapped_column(Integer, default=0)
    duplicate_count: Mapped[int] = mapped_column(Integer, default=0)
    skipped_count: Mapped[int] = mapped_column(Integer, default=0)
    error_count: Mapped[int] = mapped_column(Integer, default=0)
    notes_json: Mapped[Any | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    committed_at: Mapped[datetime | None] = mapped_column(DateTime)
    rolled_back_at: Mapped[datetime | None] = mapped_column(DateTime)
    rollback_reason: Mapped[str | None] = mapped_column(Text)
