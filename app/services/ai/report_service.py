from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import AIReport, AlertEvent, FundIndicator, FundScore, Watchlist
from app.services.ai.ollama_client import OllamaClient
from app.services.ai.prompt_templates import DAILY_REPORT_PROMPT, FUND_EXPLAIN_PROMPT

FORBIDDEN_TERMS = ["立即买入", "立即卖出", "重仓买入", "保证收益"]


def _sanitize(content: str) -> str:
    cleaned = content
    for term in FORBIDDEN_TERMS:
        cleaned = cleaned.replace(term, "继续观察")
    return cleaned.strip()


def _fallback_report(data: dict) -> str:
    return (
        "今日概况\n"
        "系统已基于本地净值、指标和评分数据生成规则摘要。\n\n"
        "重点关注\n"
        f"当前自选基金数量：{data.get('watchlist_count', 0)}，"
        f"已有评分数量：{data.get('score_count', 0)}。\n\n"
        "风险提醒\n"
        f"当前未读预警数量：{data.get('alert_count', 0)}。请重点查看回撤、波动和持仓集中度。\n\n"
        "明日观察\n"
        "继续观察净值更新、评分变化和预警新增情况。本报告不构成投资建议。"
    )


def collect_daily_report_data(db: Session) -> dict:
    watchlist = db.scalars(select(Watchlist).where(Watchlist.is_active.is_(True))).all()
    scores = db.scalars(select(FundScore).order_by(FundScore.total_score.desc()).limit(10)).all()
    alerts = db.scalars(select(AlertEvent).where(AlertEvent.is_read.is_(False))).all()
    return {
        "watchlist_count": len(watchlist),
        "score_count": len(scores),
        "alert_count": len(alerts),
        "top_scores": [
            {
                "fund_code": item.fund_code,
                "score": float(item.total_score) if item.total_score is not None else None,
                "rating": item.rating,
                "reason": item.reason,
            }
            for item in scores
        ],
        "alerts": [
            {"fund_code": item.fund_code, "title": item.title, "level": item.alert_level}
            for item in alerts[:10]
        ],
    }


def generate_daily_report(db: Session) -> AIReport:
    data = collect_daily_report_data(db)
    prompt = DAILY_REPORT_PROMPT.format(fund_data=data)
    model_name = get_settings().ollama_model
    try:
        content = OllamaClient().generate(prompt)
        if not content:
            content = _fallback_report(data)
    except Exception:
        content = _fallback_report(data)
        model_name = "rule-fallback"
    report = AIReport(
        report_type="daily",
        title="每日基金简报",
        content=_sanitize(content),
        model_name=model_name,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def generate_fund_explanation(db: Session, fund_code: str) -> AIReport:
    fund_code = fund_code.zfill(6)
    indicator = db.scalar(
        select(FundIndicator).where(FundIndicator.fund_code == fund_code).order_by(FundIndicator.calc_date.desc())
    )
    score = db.scalar(select(FundScore).where(FundScore.fund_code == fund_code).order_by(FundScore.score_date.desc()))
    data = {
        "fund_code": fund_code,
        "indicator": indicator.__dict__ if indicator else None,
        "score": score.__dict__ if score else None,
    }
    prompt = FUND_EXPLAIN_PROMPT.format(fund_data=data)
    model_name = get_settings().ollama_model
    try:
        content = OllamaClient().generate(prompt)
    except Exception:
        content = f"{fund_code} 当前使用规则解释：请结合收益率、最大回撤、波动率和评分原因综合观察。本说明不构成投资建议。"
        model_name = "rule-fallback"
    report = AIReport(
        report_type="fund",
        target_code=fund_code,
        title=f"{fund_code} 基金解释",
        content=_sanitize(content),
        model_name=model_name,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def latest_report(db: Session, report_type: str = "daily") -> AIReport | None:
    return db.scalar(
        select(AIReport)
        .where(AIReport.report_type == report_type)
        .order_by(AIReport.created_at.desc())
        .limit(1)
    )


def latest_fund_report(db: Session, fund_code: str) -> AIReport | None:
    return db.scalar(
        select(AIReport)
        .where(AIReport.report_type == "fund", AIReport.target_code == fund_code.zfill(6))
        .order_by(AIReport.created_at.desc())
        .limit(1)
    )
