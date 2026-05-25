from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import alert_service, data_health_service, market_service, portfolio_service, score_service, watchlist_service
from app.services.ai.report_service import latest_report

router = APIRouter()


@router.get("/overview")
def dashboard_overview(db: Session = Depends(get_db)):
    watchlist = watchlist_service.list_watchlist_items(db)
    scores = score_service.top_scores(db, limit=5)
    alerts = alert_service.unread_alerts(db)
    report = latest_report(db)
    market_context = market_service.latest_market_context(db)
    health = data_health_service.data_health_overview(db)
    fund_names = {item.fund_code: item.fund_name or item.fund_code for item in watchlist}
    return {
        "watchlist_count": len(watchlist),
        "top_scores": [
            {
                "fund_code": item.fund_code,
                "fund_name": fund_names.get(item.fund_code, item.fund_code),
                "total_score": float(item.total_score) if item.total_score is not None else None,
                "rating": item.rating,
                "reason": item.reason,
                "score_date": item.score_date,
            }
            for item in scores
        ],
        "unread_alerts": alerts,
        "latest_report": report,
        "market_context": market_context,
        "data_health": health,
    }


@router.get("/today")
def dashboard_today(db: Session = Depends(get_db)):
    watchlist = watchlist_service.list_watchlist_items(db)
    health = data_health_service.data_health_overview(db)
    alerts = alert_service.unread_alerts(db)
    report = latest_report(db)
    market_context = market_service.latest_market_context(db)
    portfolio = portfolio_service.portfolio_diagnosis(db)
    todos = []

    stale_count = health["stale_fund_count"] + health["failed_fund_count"]
    if stale_count:
        todos.append(
            {
                "key": "sync",
                "title": f"同步 {stale_count} 只基金净值",
                "description": "部分自选基金净值缺失或过旧，建议先完成同步再看评分和图表。",
                "action": "sync_watchlist",
                "route": "/watchlist",
                "level": "warning",
            }
        )
    if health["pending_indicator_count"]:
        todos.append(
            {
                "key": "indicator",
                "title": f"计算 {health['pending_indicator_count']} 只基金指标",
                "description": "净值已更新后，指标需要重新计算，评分才有参考价值。",
                "action": "calc_indicators",
                "route": "/tasks",
                "level": "info",
            }
        )
    if health["pending_score_count"]:
        todos.append(
            {
                "key": "score",
                "title": f"生成 {health['pending_score_count']} 只基金评分",
                "description": "指标已经更新但评分还未生成，建议补齐评分后再查看排行和基金详情。",
                "action": "calc_scores",
                "route": "/tasks",
                "level": "info",
            }
        )
    if health["pending_report_count"]:
        todos.append(
            {
                "key": "fund_report",
                "title": f"生成 {health['pending_report_count']} 只基金解释",
                "description": "部分基金已有评分但缺少解释报告，建议生成后用于复盘评分变化原因。",
                "action": "generate_fund_reports",
                "route": "/watchlist",
                "level": "info",
            }
        )
    if alerts:
        todos.append(
            {
                "key": "alerts",
                "title": f"处理 {len(alerts)} 条风险预警",
                "description": "请查看触发原因，并标记为已读、已处理或忽略。",
                "action": "review_alerts",
                "route": "/",
                "level": "warning",
            }
        )
    if not report:
        todos.append(
            {
                "key": "report",
                "title": "生成今日 AI 简报",
                "description": "用结构化数据生成今日复盘，覆盖市场、自选、持仓和风险提醒。",
                "action": "generate_report",
                "route": "/reports/daily",
                "level": "info",
            }
        )
    if not todos:
        todos.append(
            {
                "key": "done",
                "title": "今日暂无必须处理事项",
                "description": "数据、评分、预警和报告未发现阻塞项，可以直接进入复盘。",
                "action": "review",
                "route": "/reports/daily",
                "level": "success",
            }
        )

    return {
        "date": None,
        "watchlist_count": len(watchlist),
        "todos": todos,
        "key_risks": portfolio["risk_items"],
        "data_health": health,
        "unread_alerts": alerts,
        "latest_report": report,
        "market_context": market_context,
        "portfolio_diagnosis": portfolio,
    }
