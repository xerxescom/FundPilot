"""交易日历：缓存 akshare 开市日历，离线时回退到周末规则。

判定“暂未发布”与“真正失败”都以这里的开市日为准：
抓取成功但最新数据日期落后且在宽限内 = pending（暂未发布），超出宽限才算失败。
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta

from loguru import logger
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import TradeCalendar

CALENDAR_SOURCE_AKSHARE = "akshare"
CALENDAR_SOURCE_FALLBACK = "weekend_fallback"
_MAX_BACKTRACK_DAYS = 10
_REFRESH_WINDOW_PAST_DAYS = 90
_REFRESH_WINDOW_FUTURE_DAYS = 30


def _close_time() -> time:
    raw = get_settings().market_close_time
    try:
        hour, minute = (int(part) for part in raw.split(":", 1))
        return time(hour, minute)
    except (ValueError, TypeError):
        return time(15, 0)


def coverage_range(db: Session) -> tuple[date | None, date | None]:
    row = db.execute(select(func.min(TradeCalendar.trade_date), func.max(TradeCalendar.trade_date))).first()
    return (row[0], row[1]) if row else (None, None)


def calendar_source_for(db: Session, day: date) -> str:
    lower, upper = coverage_range(db)
    if lower and upper and lower <= day <= upper:
        return CALENDAR_SOURCE_AKSHARE
    return CALENDAR_SOURCE_FALLBACK


def _is_weekend_rule(day: date) -> bool:
    return day.weekday() < 5


def is_trading_day(db: Session, day: date) -> bool:
    row = db.get(TradeCalendar, day)
    if row is not None:
        return bool(row.is_open)
    lower, upper = coverage_range(db)
    if lower and upper and lower <= day <= upper:
        return False
    # 覆盖范围外（尚未刷新到位）：退化为周末规则
    return _is_weekend_rule(day)


def count_open_days(db: Session, start: date, end: date) -> int:
    """[start, end] 内的开市日数量；无覆盖时退化为工作日计数。"""
    if start > end:
        return 0
    count = db.scalar(
        select(func.count()).select_from(TradeCalendar).where(TradeCalendar.trade_date >= start, TradeCalendar.trade_date <= end)
    )
    if count:
        return int(count)
    lower, upper = coverage_range(db)
    if lower and upper and lower <= start and end <= upper:
        return 0
    days = 0
    cursor = start
    while cursor <= end:
        if _is_weekend_rule(cursor):
            days += 1
        cursor += timedelta(days=1)
    return days


def _as_date(value: object) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.strptime(str(value), "%Y-%m-%d").date()


def refresh_trade_calendar(db: Session, start: date | None = None, end: date | None = None) -> bool:
    """从 akshare 拉取开市日历并写入缓存；任何异常只记日志并返回 False。"""
    today = date.today()
    start = start or today - timedelta(days=_REFRESH_WINDOW_PAST_DAYS)
    end = end or today + timedelta(days=_REFRESH_WINDOW_FUTURE_DAYS)
    try:
        import akshare as ak

        frame = ak.tool_trade_date_hist_sina()
        dates = {_as_date(value) for value in frame["trade_date"]}
    except Exception as exc:  # noqa: BLE001 - 离线时静默回退，不阻塞批次
        logger.warning(f"交易日历刷新失败，沿用本地缓存/周末规则：{exc}")
        return False

    existing = {
        item.trade_date
        for item in db.scalars(
            select(TradeCalendar).where(TradeCalendar.trade_date >= start, TradeCalendar.trade_date <= end)
        )
    }
    added = 0
    for day in sorted(dates):
        if start <= day <= end and day not in existing:
            db.add(TradeCalendar(trade_date=day, is_open=True, source=CALENDAR_SOURCE_AKSHARE))
            added += 1
    if added:
        db.commit()
    return True


def ensure_calendar_coverage(db: Session, start: date | None = None, end: date | None = None) -> bool:
    """覆盖不足或缓存过期时尽力刷新；返回是否实际刷新过。"""
    settings = get_settings()
    today = date.today()
    start = start or today - timedelta(days=_REFRESH_WINDOW_PAST_DAYS)
    end = end or today + timedelta(days=_REFRESH_WINDOW_FUTURE_DAYS)
    lower, upper = coverage_range(db)
    covered = bool(lower and upper and lower <= start and upper >= end)
    if covered:
        latest_update = db.scalar(select(func.max(TradeCalendar.updated_at)))
        if latest_update and (datetime.now() - latest_update).days < settings.trade_calendar_refresh_days:
            return False
    return refresh_trade_calendar(db, start, end)


def latest_expected_trade_date(db: Session, now: datetime | None = None) -> date:
    """批次应针对的最新开市日：今天开市但未到收盘时间时，仍取上一个开市日。"""
    now = now or datetime.now()
    today = now.date()
    if is_trading_day(db, today) and now.time() >= _close_time():
        return today
    cursor = today - timedelta(days=1)
    for _ in range(_MAX_BACKTRACK_DAYS):
        if is_trading_day(db, cursor):
            return cursor
        cursor -= timedelta(days=1)
    return today


def classify_asset_freshness(
    db: Session, asset_type: str, latest_date: date | None, expected_trade_date: date
) -> tuple[str, str | None]:
    """按品种宽限把同步结果分为 success / pending(暂未发布) / failed。

    返回 (status, error_class)；只有“抓取成功但数据尚未发布”才是 pending，
    抓取失败由调用方归类为 source_error。
    """
    if latest_date is None:
        return "failed", "data_missing"
    if latest_date >= expected_trade_date:
        return "success", None
    settings = get_settings()
    lag = count_open_days(db, latest_date + timedelta(days=1), expected_trade_date)
    grace = (
        settings.fund_disclosure_grace_trade_days
        if asset_type == "fund"
        else settings.market_data_grace_trade_days
    )
    if lag <= grace:
        return "pending", None
    return "failed", ("disclosure_overdue" if asset_type == "fund" else "market_data_missing")
