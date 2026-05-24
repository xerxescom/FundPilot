from __future__ import annotations

from sqlalchemy.orm import Session

from app.services import alert_service, indicator_service, market_service, nav_service, score_service
from app.services.ai.report_service import generate_daily_report
from app.services.task_log_service import run_logged


def run_task(db: Session, task_name: str):
    tasks = {
        "sync_watchlist_nav": lambda: nav_service.sync_watchlist_nav(db),
        "calc_indicators": lambda: indicator_service.calculate_watchlist_indicators(db),
        "calc_scores": lambda: score_service.calculate_watchlist_scores(db),
        "generate_alerts": lambda: [alert.title for alert in alert_service.generate_alerts(db)],
        "sync_market_context": lambda: market_service.sync_market_context(db),
        "generate_daily_report": lambda: str(generate_daily_report(db).id),
    }
    if task_name not in tasks:
        raise ValueError(f"Unknown task: {task_name}")
    return run_logged(db, f"manual_{task_name}", tasks[task_name])


def available_tasks() -> list[dict[str, str]]:
    return [
        {"task_name": "sync_watchlist_nav", "description": "同步全部自选基金净值"},
        {"task_name": "calc_indicators", "description": "计算全部自选基金指标"},
        {"task_name": "calc_scores", "description": "计算全部自选基金评分"},
        {"task_name": "generate_alerts", "description": "生成风险预警"},
        {"task_name": "sync_market_context", "description": "同步市场背景"},
        {"task_name": "generate_daily_report", "description": "生成每日基金简报"},
    ]
