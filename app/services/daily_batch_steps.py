"""批次步骤执行器：每个 (step, asset_type) 复用既有服务，并映射为 ItemOutcome。

只有“抓取成功但数据尚未发布”会归类为 pending（暂未发布）；抓取异常一律是
failed/source_error（真正失败）。所有数据处理都走既有服务，不在此重复实现。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from loguru import logger
from sqlalchemy.orm import Session

from app.db.models import TaskBatch, TaskBatchItem
from app.services import (
    alert_service,
    asset_service,
    daily_batch_service,
    indicator_service,
    market_service,
    nav_service,
    score_service,
    trading_calendar_service,
)
from app.services.ai.report_service import generate_daily_report
from app.services.task_log_service import summarize_result

LISTED_SYNC_ATTEMPTS = 2


@dataclass
class ItemOutcome:
    status: str
    result_json: dict | None = None
    error_class: str | None = None
    error_message: str | None = None


def _latest_fund_nav_date(db: Session, asset_code: str) -> date | None:
    latest = nav_service.latest_nav(db, asset_code)
    return latest.nav_date if latest is not None else None


def _latest_listed_price_date(db: Session, asset_code: str) -> date | None:
    price = asset_service.latest_price(db, asset_code)
    return price.price_date if price is not None else None


def _classify(db: Session, asset_type: str, latest_date: date | None, batch: TaskBatch) -> ItemOutcome:
    status, error_class = trading_calendar_service.classify_asset_freshness(
        db, asset_type, latest_date, batch.trade_date
    )
    if status == "failed":
        label = "净值" if asset_type == "fund" else "行情"
        message = f"最新{label}日期 {latest_date or '无'}，落后于应披露的 {batch.trade_date}"
        return ItemOutcome(status, error_class=error_class, error_message=message)
    return ItemOutcome(status)


def _execute_market(db: Session, item: TaskBatchItem, batch: TaskBatch, now: datetime) -> ItemOutcome:
    result = market_service.sync_market_context(db)
    success_count, failure_count, _ = summarize_result(result)
    payload = {"synced_indexes": success_count or 0, "failed_indexes": failure_count}
    if not success_count:
        return ItemOutcome("failed", payload, "source_error", "全部市场指数同步失败")
    return ItemOutcome("success", payload)


def _execute_sync_fund(db: Session, item: TaskBatchItem, batch: TaskBatch, now: datetime) -> ItemOutcome:
    try:
        detail = nav_service.sync_fund_nav_detailed(db, item.asset_code)
    except Exception as exc:  # noqa: BLE001 - 数据源异常统一归类为 source_error
        return ItemOutcome("failed", None, "source_error", str(exc)[:500])
    latest_date = _latest_fund_nav_date(db, item.asset_code)
    outcome = _classify(db, "fund", latest_date, batch)
    result = {
        "synced_rows": detail.get("synced_rows"),
        "source": detail.get("source"),
        "quality": detail.get("quality"),
        "latest_nav_date": latest_date.isoformat() if latest_date else None,
    }
    return ItemOutcome(outcome.status, result, outcome.error_class, outcome.error_message)


def _execute_sync_listed(db: Session, item: TaskBatchItem, batch: TaskBatch, now: datetime) -> ItemOutcome:
    last_exc: Exception | None = None
    detail: dict | None = None
    for _ in range(LISTED_SYNC_ATTEMPTS):
        try:
            detail = asset_service.sync_listed_asset(db, item.asset_code, item.asset_type)
            break
        except Exception as exc:  # noqa: BLE001 - 重试后再归类
            last_exc = exc
    if detail is None:
        return ItemOutcome("failed", None, "source_error", str(last_exc)[:500] if last_exc else "同步失败")
    latest_date = _latest_listed_price_date(db, item.asset_code)
    outcome = _classify(db, item.asset_type, latest_date, batch)
    result = {
        "synced_rows": detail.get("synced_rows"),
        "latest_price_date": latest_date.isoformat() if latest_date else None,
    }
    return ItemOutcome(outcome.status, result, outcome.error_class, outcome.error_message)


def _execute_quality_fund(db: Session, item: TaskBatchItem, batch: TaskBatch, now: datetime) -> ItemOutcome:
    sync_item = daily_batch_service.get_item(db, batch, "sync_nav", item.asset_type, item.asset_code)
    sync_result = (sync_item.result_json if sync_item else None) or {}
    quality = sync_result.get("quality") or {}
    latest_date = _latest_fund_nav_date(db, item.asset_code)
    if latest_date is None:
        return ItemOutcome("failed", None, "data_quality", "缺少净值数据")
    issues = [str(issue) for issue in quality.get("issues") or []]
    payload = {"latest_nav_date": latest_date.isoformat(), "issues": issues}
    if quality.get("valid") is False:
        return ItemOutcome("failed", payload, "data_quality", "；".join(issues[:3]) or "数据质量校验未通过")
    return ItemOutcome("success", payload)


def _execute_quality_listed(db: Session, item: TaskBatchItem, batch: TaskBatch, now: datetime) -> ItemOutcome:
    price = asset_service.latest_price(db, item.asset_code)
    if price is None or price.close is None:
        return ItemOutcome("failed", None, "data_quality", "缺少行情数据")
    payload = {"latest_price_date": price.price_date.isoformat(), "close": str(price.close)}
    return ItemOutcome("success", payload)


def _execute_indicators(db: Session, item: TaskBatchItem, batch: TaskBatch, now: datetime) -> ItemOutcome:
    try:
        indicator = indicator_service.calculate_and_save_indicators(db, item.asset_code)
    except ValueError as exc:
        return ItemOutcome("failed", None, "insufficient_history", str(exc)[:500])
    return ItemOutcome("success", {"calc_date": indicator.calc_date.isoformat()})


def _execute_scores(db: Session, item: TaskBatchItem, batch: TaskBatch, now: datetime) -> ItemOutcome:
    try:
        score = score_service.calculate_and_save_score(db, item.asset_code)
    except ValueError as exc:
        return ItemOutcome("failed", None, "indicator_missing", str(exc)[:500])
    return ItemOutcome(
        "success", {"score_date": score.score_date.isoformat(), "total_score": str(score.total_score)}
    )


def _execute_alerts(db: Session, item: TaskBatchItem, batch: TaskBatch, now: datetime) -> ItemOutcome:
    try:
        alerts = alert_service.generate_alerts(db)
    except Exception as exc:  # noqa: BLE001 - 预警失败不阻断报告
        logger.warning(f"批次预警生成失败：{exc}")
        return ItemOutcome("failed", None, "alert_error", str(exc)[:500])
    return ItemOutcome("success", {"alert_count": len(alerts)})


def _execute_report(db: Session, item: TaskBatchItem, batch: TaskBatch, now: datetime) -> ItemOutcome:
    report = generate_daily_report(
        db, batch_id=batch.id, trade_date=batch.trade_date, coverage=batch.coverage_json
    )
    return ItemOutcome("success", {"report_id": report.id, "is_fallback": bool(report.is_fallback)})


_GLOBAL_HANDLERS = {
    "market": _execute_market,
    "alerts": _execute_alerts,
    "report": _execute_report,
}
_ASSET_HANDLERS = {
    ("sync_nav", "fund"): _execute_sync_fund,
    ("sync_nav", "stock"): _execute_sync_listed,
    ("sync_nav", "etf"): _execute_sync_listed,
    ("quality_check", "fund"): _execute_quality_fund,
    ("quality_check", "stock"): _execute_quality_listed,
    ("quality_check", "etf"): _execute_quality_listed,
    ("calc_indicators", "fund"): _execute_indicators,
    ("calc_scores", "fund"): _execute_scores,
}


def execute_item(db: Session, item: TaskBatchItem, batch: TaskBatch, now: datetime | None = None) -> ItemOutcome:
    now = now or datetime.now()
    if item.asset_code == "":
        handler = _GLOBAL_HANDLERS.get(item.step)
    else:
        handler = _ASSET_HANDLERS.get((item.step, item.asset_type))
    if handler is None:
        return ItemOutcome("failed", None, "unknown_step", f"未实现的步骤：{item.step}/{item.asset_type}")
    return handler(db, item, batch, now)
