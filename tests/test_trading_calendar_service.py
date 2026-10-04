import sys
import types
from datetime import date, datetime, timedelta

import pandas as pd
from sqlalchemy import select

from app.db.models import TradeCalendar
from app.services import trading_calendar_service as calendar


def _seed_open_days(db_session, days: list[date]) -> None:
    for day in days:
        db_session.add(TradeCalendar(trade_date=day, is_open=True, source="akshare"))
    db_session.commit()


def _stored_dates(db_session) -> set[date]:
    return set(db_session.scalars(select(TradeCalendar.trade_date)))


def _weekdays(start: date, end: date) -> list[date]:
    days = []
    cursor = start
    while cursor <= end:
        if cursor.weekday() < 5:
            days.append(cursor)
        cursor += timedelta(days=1)
    return days


def test_weekend_fallback_without_coverage(db_session):
    assert calendar.is_trading_day(db_session, date(2026, 10, 3)) is False  # 周六
    assert calendar.is_trading_day(db_session, date(2026, 10, 4)) is False  # 周日
    assert calendar.is_trading_day(db_session, date(2026, 10, 5)) is True  # 周一
    assert calendar.calendar_source_for(db_session, date(2026, 10, 5)) == "weekend_fallback"


def test_coverage_range_missing_row_means_closed(db_session):
    days = _weekdays(date(2026, 9, 28), date(2026, 10, 12))
    days = [day for day in days if day != date(2026, 10, 7)]  # 模拟节假日
    _seed_open_days(db_session, days)

    assert calendar.is_trading_day(db_session, date(2026, 10, 7)) is False  # 覆盖范围内无记录 → 休市
    assert calendar.is_trading_day(db_session, date(2026, 10, 6)) is True
    assert calendar.is_trading_day(db_session, date(2026, 10, 13)) is True  # 覆盖范围外 → 周末规则
    assert calendar.calendar_source_for(db_session, date(2026, 10, 6)) == "akshare"
    assert calendar.calendar_source_for(db_session, date(2026, 10, 20)) == "weekend_fallback"


def test_latest_expected_trade_date_respects_close_time(db_session):
    days = _weekdays(date(2026, 9, 28), date(2026, 10, 12))
    days = [day for day in days if day != date(2026, 10, 7)]
    _seed_open_days(db_session, days)

    # 交易日盘中 → 仍取上一开市日
    assert calendar.latest_expected_trade_date(db_session, datetime(2026, 10, 6, 10, 0)) == date(2026, 10, 5)
    # 交易日收盘后 → 今天
    assert calendar.latest_expected_trade_date(db_session, datetime(2026, 10, 6, 16, 0)) == date(2026, 10, 6)
    # 周末 → 上一开市日
    assert calendar.latest_expected_trade_date(db_session, datetime(2026, 10, 4, 10, 0)) == date(2026, 10, 2)
    # 节假日前的盘中 → 跳过休市日回溯
    assert calendar.latest_expected_trade_date(db_session, datetime(2026, 10, 8, 10, 0)) == date(2026, 10, 6)


def test_refresh_trade_calendar_upserts_and_tolerates_failure(db_session, monkeypatch):
    fake_dates = [date(2026, 9, 30), date(2026, 10, 1), date(2026, 10, 2)]
    fake_akshare = types.SimpleNamespace(
        tool_trade_date_hist_sina=lambda: pd.DataFrame({"trade_date": fake_dates})
    )
    monkeypatch.setitem(sys.modules, "akshare", fake_akshare)

    assert calendar.refresh_trade_calendar(db_session, date(2026, 9, 1), date(2026, 10, 31)) is True
    assert _stored_dates(db_session) == set(fake_dates)
    assert calendar.refresh_trade_calendar(db_session, date(2026, 9, 1), date(2026, 10, 31)) is True
    assert len(_stored_dates(db_session)) == 3  # 重复刷新不产生重复行

    def _boom():
        raise RuntimeError("network down")

    monkeypatch.setitem(sys.modules, "akshare", types.SimpleNamespace(tool_trade_date_hist_sina=_boom))
    assert calendar.refresh_trade_calendar(db_session, date(2026, 9, 1), date(2026, 10, 31)) is False
    assert len(_stored_dates(db_session)) == 3


def test_count_open_days_uses_rows_then_weekday_fallback(db_session):
    days = _weekdays(date(2026, 10, 5), date(2026, 10, 9))
    _seed_open_days(db_session, days)

    assert calendar.count_open_days(db_session, date(2026, 10, 5), date(2026, 10, 9)) == 5
    # 无覆盖的远期范围退化为工作日计数
    assert calendar.count_open_days(db_session, date(2026, 11, 2), date(2026, 11, 8)) == 5


def test_classify_asset_freshness_grace_windows(db_session):
    days = _weekdays(date(2026, 9, 28), date(2026, 10, 9))
    _seed_open_days(db_session, days)
    expected = date(2026, 10, 9)

    assert calendar.classify_asset_freshness(db_session, "fund", expected, expected) == ("success", None)
    assert calendar.classify_asset_freshness(db_session, "fund", date(2026, 10, 8), expected) == ("pending", None)
    assert calendar.classify_asset_freshness(db_session, "fund", date(2026, 10, 5), expected) == (
        "failed",
        "disclosure_overdue",
    )
    assert calendar.classify_asset_freshness(db_session, "stock", date(2026, 10, 8), expected) == ("pending", None)
    assert calendar.classify_asset_freshness(db_session, "etf", date(2026, 10, 6), expected) == (
        "failed",
        "market_data_missing",
    )
    assert calendar.classify_asset_freshness(db_session, "fund", None, expected) == ("failed", "data_missing")
