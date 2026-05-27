from __future__ import annotations

from time import perf_counter
from typing import Callable

from sqlalchemy.orm import Session

from app.db.session import SessionLocal
from app.services import alert_service, holding_service, indicator_service, market_service, nav_service, score_service
from app.services.ai.report_service import generate_daily_report
from app.services.task_log_service import record_task_log, result_counts, run_logged, update_task_log


def _task_factories(db: Session) -> dict[str, Callable[[], object]]:
    return {
        "sync_watchlist_nav": lambda: nav_service.sync_watchlist_nav(db),
        "calc_indicators": lambda: indicator_service.calculate_watchlist_indicators(db),
        "calc_scores": lambda: score_service.calculate_watchlist_scores(db),
        "sync_holding_industries": lambda: holding_service.sync_watchlist_holding_industries(db),
        "generate_alerts": lambda: [alert.title for alert in alert_service.generate_alerts(db)],
        "sync_market_context": lambda: market_service.sync_market_context(db),
        "generate_daily_report": lambda: str(generate_daily_report(db).id),
    }


def _task_fn(db: Session, task_name: str) -> Callable[[], object]:
    tasks = _task_factories(db)
    if task_name not in tasks:
        raise ValueError(f"Unknown task: {task_name}")
    return tasks[task_name]


def run_task(db: Session, task_name: str):
    return run_logged(db, f"manual_{task_name}", _task_fn(db, task_name))


def enqueue_task(db: Session, task_name: str):
    _task_fn(db, task_name)
    return record_task_log(
        db,
        task_name=f"queued_{task_name}",
        status="queued",
        success_count=0,
        failure_count=0,
        message="任务已提交后台执行",
    )


def run_queued_task(log_id: int, task_name: str) -> None:
    started = perf_counter()
    db = SessionLocal()
    try:
        update_task_log(db, log_id, status="running", message="任务执行中")
        result = _task_fn(db, task_name)()
        success_count, failure_count = result_counts(result)
        update_task_log(
            db,
            log_id,
            status="success",
            duration_ms=int((perf_counter() - started) * 1000),
            success_count=success_count,
            failure_count=failure_count,
            message=str(result)[:2000],
        )
    except Exception as exc:
        update_task_log(
            db,
            log_id,
            status="failed",
            duration_ms=int((perf_counter() - started) * 1000),
            success_count=0,
            failure_count=1,
            message=str(exc),
        )
    finally:
        db.close()


def available_tasks() -> list[dict[str, str]]:
    return [
        {
            "task_name": "sync_watchlist_nav",
            "description": "同步全部自选基金净值",
            "priority": "P0",
            "scenario": "基金数据抓取与指标分析",
        },
        {
            "task_name": "calc_indicators",
            "description": "计算全部自选基金指标",
            "priority": "P0",
            "scenario": "基金数据抓取与指标分析",
        },
        {
            "task_name": "calc_scores",
            "description": "计算全部自选基金评分",
            "priority": "P1",
            "scenario": "多策略基金评分体系的默认评分基础",
        },
        {
            "task_name": "sync_holding_industries",
            "description": "同步基金持仓行业",
            "priority": "P2",
            "scenario": "基金估值匹配和行业暴露解释",
        },
        {
            "task_name": "generate_alerts",
            "description": "生成风险预警",
            "priority": "P0",
            "scenario": "日常复盘和风险识别",
        },
        {
            "task_name": "sync_market_context",
            "description": "同步市场背景",
            "priority": "P2",
            "scenario": "热点新闻和市场解释的前置数据",
        },
        {
            "task_name": "generate_daily_report",
            "description": "生成每日基金简报",
            "priority": "P3",
            "scenario": "AI 投研观察与风险解释",
        },
    ]
