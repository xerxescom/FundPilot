from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FundInfo
from app.services import data_health_service, indicator_service, nav_service, score_service
from app.services.ai.report_service import generate_fund_explanation, latest_fund_report


def analysis_status(db: Session, fund_code: str) -> dict:
    fund_code = fund_code.zfill(6)
    fund = db.scalar(select(FundInfo).where(FundInfo.fund_code == fund_code))
    nav = nav_service.latest_nav(db, fund_code)
    indicator = indicator_service.latest_indicator(db, fund_code)
    score = score_service.latest_score(db, fund_code)
    report = latest_fund_report(db, fund_code)
    health = data_health_service.fund_data_health(db, fund_code)

    steps = [
        {"key": "nav", "label": "净值已同步", "done": nav is not None},
        {"key": "indicator", "label": "指标已计算", "done": indicator is not None},
        {"key": "score", "label": "评分已生成", "done": score is not None},
        {"key": "report", "label": "报告已生成", "done": report is not None},
    ]
    if not nav:
        status = "not_synced"
        label = "未同步"
    elif not indicator:
        status = "nav_synced"
        label = "净值已同步"
    elif not score:
        status = "indicator_ready"
        label = "指标已计算"
    elif not report:
        status = "score_ready"
        label = "评分已生成"
    else:
        status = "complete"
        label = "分析完成"

    return {
        "fund_code": fund_code,
        "fund_name": fund.fund_name if fund else fund_code,
        "fund_type": fund.fund_type if fund else None,
        "industry": None,
        "latest_nav_date": nav.nav_date if nav else None,
        "latest_nav": nav.unit_nav if nav else None,
        "latest_indicator_date": indicator.calc_date if indicator else None,
        "latest_score": score.total_score if score else None,
        "rating": score.rating if score else None,
        "score_reason": score.reason if score else None,
        "latest_report_at": report.created_at if report else None,
        "data_status": health["status"],
        "data_issues": health["issues"],
        "status": status,
        "status_label": label,
        "steps": steps,
        "complete": status == "complete",
    }


def analyze_fund(db: Session, fund_code: str) -> dict:
    fund_code = fund_code.zfill(6)
    result: dict[str, object] = {"fund_code": fund_code, "steps": []}
    synced_rows = nav_service.sync_fund_nav(db, fund_code)
    result["steps"].append({"key": "sync_nav", "label": "同步净值", "status": "success", "result": synced_rows})
    indicator = indicator_service.calculate_and_save_indicators(db, fund_code)
    result["steps"].append({"key": "calc_indicator", "label": "计算指标", "status": "success", "result": indicator.calc_date})
    score = score_service.calculate_and_save_score(db, fund_code)
    result["steps"].append({"key": "calc_score", "label": "计算评分", "status": "success", "result": score.total_score})
    report = generate_fund_explanation(db, fund_code)
    result["steps"].append({"key": "fund_report", "label": "生成基金解释", "status": "success", "result": report.id})
    result["status"] = analysis_status(db, fund_code)
    return result
