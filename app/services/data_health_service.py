from __future__ import annotations

import ast
from collections import Counter
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import AIReport, FundIndicator, FundNav, FundScore, TaskRunLog, Watchlist

STALE_NAV_DAYS = 7
NAV_GAP_DAYS = 10


def _latest_indicator_date(db: Session, fund_code: str) -> date | None:
    return db.scalar(
        select(FundIndicator.calc_date)
        .where(FundIndicator.fund_code == fund_code)
        .order_by(FundIndicator.calc_date.desc())
        .limit(1)
    )


def _latest_score_date(db: Session, fund_code: str) -> date | None:
    return db.scalar(
        select(FundScore.score_date)
        .where(FundScore.fund_code == fund_code)
        .order_by(FundScore.score_date.desc())
        .limit(1)
    )


def _latest_fund_report_date(db: Session, fund_code: str) -> date | None:
    created_at = db.scalar(
        select(AIReport.created_at)
        .where(AIReport.report_type == "fund", AIReport.target_code == fund_code)
        .order_by(AIReport.created_at.desc())
        .limit(1)
    )
    return created_at.date() if created_at else None


def _nav_dates(db: Session, fund_code: str) -> list[date]:
    return list(
        db.scalars(select(FundNav.nav_date).where(FundNav.fund_code == fund_code).order_by(FundNav.nav_date.asc()))
    )


def _latest_sync_status(db: Session, fund_code: str) -> tuple[str | None, str | None, date | None]:
    logs = db.scalars(
        select(TaskRunLog)
        .where(TaskRunLog.task_name.in_(["update_fund_nav", "manual_sync_watchlist_nav"]))
        .order_by(TaskRunLog.created_at.desc())
        .limit(20)
    ).all()
    for log in logs:
        if not log.message or fund_code not in log.message:
            continue
        try:
            data = ast.literal_eval(log.message)
        except (SyntaxError, ValueError):
            continue
        if isinstance(data, dict) and fund_code in data:
            value = data[fund_code]
            if isinstance(value, dict):
                status = value.get("status")
                if status == "failed":
                    quality = value.get("quality")
                    issues = quality.get("issues", []) if isinstance(quality, dict) else []
                    reason = "；".join(str(issue) for issue in issues) if issues else None
                    return "failed", reason, log.created_at.date()
                return "success", None, log.created_at.date()
            if isinstance(value, str) and value.startswith("failed:"):
                return "failed", value.removeprefix("failed:").strip(), log.created_at.date()
            return "success", None, log.created_at.date()
    return None, None, None


def fund_data_health(db: Session, fund_code: str, today: date | None = None) -> dict:
    fund_code = fund_code.zfill(6)
    today = today or date.today()
    dates = _nav_dates(db, fund_code)
    latest_nav_date = dates[-1] if dates else None
    missing_return_count = db.scalar(
        select(func.count())
        .select_from(FundNav)
        .where(FundNav.fund_code == fund_code, FundNav.daily_return.is_(None))
    )
    duplicate_rows = db.execute(
        select(FundNav.nav_date, func.count())
        .where(FundNav.fund_code == fund_code)
        .group_by(FundNav.nav_date)
        .having(func.count() > 1)
    ).all()
    gap_count = sum(1 for left, right in zip(dates, dates[1:]) if (right - left).days > NAV_GAP_DAYS)
    latest_indicator_date = _latest_indicator_date(db, fund_code)
    latest_score_date = _latest_score_date(db, fund_code)
    latest_report_date = _latest_fund_report_date(db, fund_code)
    latest_sync_status, latest_failure_reason, latest_sync_date = _latest_sync_status(db, fund_code)
    is_stale = latest_nav_date is None or (today - latest_nav_date).days > STALE_NAV_DAYS
    stale_days = (today - latest_nav_date).days if latest_nav_date else None
    needs_indicator = bool(latest_nav_date and (latest_indicator_date is None or latest_indicator_date < latest_nav_date))
    needs_score = bool(
        latest_indicator_date and (latest_score_date is None or latest_score_date < latest_indicator_date)
    )
    needs_report = bool(latest_score_date and (latest_report_date is None or latest_report_date < latest_score_date))
    status = "正常"
    issues = []
    if not dates:
        status = "缺少净值"
        issues.append("尚未同步净值")
    if is_stale:
        status = "需关注"
        issues.append("最新净值日期过时")
    if gap_count:
        status = "需关注"
        issues.append(f"存在 {gap_count} 处净值日期断档")
    if duplicate_rows:
        status = "需关注"
        issues.append(f"存在 {len(duplicate_rows)} 个重复净值日期")
    if missing_return_count:
        status = "需关注"
        issues.append(f"存在 {missing_return_count} 条缺失日涨跌幅")
    if needs_indicator:
        issues.append("指标需要重新计算")
    if needs_score:
        issues.append("评分需要重新生成")
    if needs_report:
        issues.append("基金解释报告待生成")

    return {
        "fund_code": fund_code,
        "latest_nav_date": latest_nav_date,
        "nav_count": len(dates),
        "gap_count": gap_count,
        "duplicate_date_count": len(duplicate_rows),
        "missing_daily_return_count": missing_return_count or 0,
        "latest_indicator_date": latest_indicator_date,
        "latest_score_date": latest_score_date,
        "latest_report_date": latest_report_date,
        "latest_sync_status": latest_sync_status,
        "latest_failure_reason": latest_failure_reason,
        "latest_sync_date": latest_sync_date,
        "stale_days": stale_days,
        "needs_indicator": needs_indicator,
        "needs_score": needs_score,
        "needs_report": needs_report,
        "is_stale": is_stale,
        "status": status,
        "issues": issues,
    }


def data_health_overview(db: Session, today: date | None = None) -> dict:
    items = list(db.scalars(select(Watchlist).where(Watchlist.is_active.is_(True)).order_by(Watchlist.fund_code)))
    funds = [fund_data_health(db, item.fund_code, today=today) for item in items]
    status_counts = Counter(item["status"] for item in funds)
    latest_dates = [item["latest_nav_date"] for item in funds if item["latest_nav_date"]]
    latest_available_trade_date = max(latest_dates) if latest_dates else None
    return {
        "watchlist_count": len(items),
        "latest_nav_date": max(latest_dates) if latest_dates else None,
        "latest_available_trade_date": latest_available_trade_date,
        "stale_fund_count": sum(1 for item in funds if item["is_stale"]),
        "failed_fund_count": sum(1 for item in funds if item["nav_count"] == 0),
        "pending_indicator_count": sum(1 for item in funds if item["needs_indicator"]),
        "pending_score_count": sum(1 for item in funds if item["needs_score"]),
        "pending_report_count": sum(1 for item in funds if item["needs_report"]),
        "missing_daily_return_count": sum(item["missing_daily_return_count"] for item in funds),
        "gap_count": sum(item["gap_count"] for item in funds),
        "duplicate_date_count": sum(item["duplicate_date_count"] for item in funds),
        "status_counts": dict(status_counts),
        "funds": funds,
    }
