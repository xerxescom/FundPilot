from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import AIReport, AlertEvent, FundIndicator, FundInfo, FundScore, Watchlist
from app.services import (
    correlation_service,
    data_health_service,
    market_service,
    portfolio_service,
    score_service,
)
from app.services.ai.ollama_client import OllamaClient
from app.services.ai.prompt_templates import DAILY_REPORT_PROMPT, FUND_EXPLAIN_PROMPT

FORBIDDEN_TERMS = ["立即买入", "立即卖出", "买入", "卖出", "重仓", "保证收益", "稳赚"]
SAFE_REPLACEMENT = "继续观察"


def _sanitize(content: str) -> str:
    cleaned = content
    for term in FORBIDDEN_TERMS:
        cleaned = cleaned.replace(term, SAFE_REPLACEMENT)
    return cleaned.strip()


def _contains_forbidden(content: str) -> str | None:
    return next((term for term in FORBIDDEN_TERMS if term in content), None)


def _snapshot(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)[:8000]


def _format_rate(value: object) -> str:
    return "-" if value is None else f"{float(value):.2%}"


def _fallback_report(data: dict) -> str:
    market_lines = [
        f"- {item['index_name']}：日涨跌 {_format_rate(item.get('daily_return'))}，近1月 {_format_rate(item.get('return_1m'))}"
        for item in data.get("market_context", [])
        if item.get("daily_return") is not None or item.get("return_1m") is not None
    ]
    portfolio = data.get("portfolio_overview", {})
    health = data.get("data_health", {})
    return (
        "今日概况\n"
        "系统已基于本地净值、指标和评分数据生成规则摘要。\n"
        f"当前需要关注数据质量的基金数量：{health.get('stale_fund_count', 0)}。\n\n"
        "市场背景\n"
        f"{chr(10).join(market_lines) if market_lines else '暂无市场指数数据。'}\n\n"
        "组合表现\n"
        f"组合当前市值：{portfolio.get('total_value')}，"
        f"收益率：{portfolio.get('profit_rate')}。\n\n"
        "自选基金表现\n"
        f"当前自选基金数量：{data.get('watchlist_count', 0)}，"
        f"已有评分数量：{data.get('score_count', 0)}。\n\n"
        "风险提醒\n"
        f"当前未读预警数量：{data.get('alert_count', 0)}。请重点查看回撤、波动和持仓集中度。\n\n"
        "明日观察\n"
        "继续观察净值更新、评分变化和预警新增情况。本报告不构成投资建议。"
    )


def _fallback_with_error(data: dict, error: Exception | str) -> str:
    return (
        "AI 调用失败，已使用规则兜底\n"
        f"失败原因：{error}\n\n"
        f"{_fallback_report(data)}"
    )


def collect_daily_report_data(db: Session) -> dict:
    watchlist = db.scalars(select(Watchlist).where(Watchlist.is_active.is_(True))).all()
    scores = score_service.top_scores(db, limit=10)
    alerts = db.scalars(select(AlertEvent).where(AlertEvent.is_read.is_(False))).all()
    fund_names = {
        item.fund_code: item.fund_name
        for item in db.scalars(select(Watchlist).where(Watchlist.is_active.is_(True)))
        if item.fund_name
    }
    fund_names.update(
        {
            item.fund_code: item.fund_name
            for item in db.scalars(select(FundInfo).where(FundInfo.fund_name.is_not(None)))
            if item.fund_name
        }
    )
    portfolio = portfolio_service.portfolio_overview(db)
    market_context = market_service.latest_market_context(db)
    high_correlation_pairs = correlation_service.high_correlation_pairs(db)
    data_health = data_health_service.data_health_overview(db)
    return {
        "watchlist_count": len(watchlist),
        "score_count": len(scores),
        "alert_count": len(alerts),
        "market_context": market_context,
        "data_health": {
            "latest_nav_date": data_health["latest_nav_date"],
            "stale_fund_count": data_health["stale_fund_count"],
            "pending_indicator_count": data_health["pending_indicator_count"],
            "pending_score_count": data_health["pending_score_count"],
            "pending_report_count": data_health["pending_report_count"],
            "gap_count": data_health["gap_count"],
        },
        "portfolio_overview": {
            "total_value": float(portfolio["total_value"]) if portfolio["total_value"] is not None else None,
            "total_cost": float(portfolio["total_cost"]) if portfolio["total_cost"] is not None else None,
            "profit_amount": float(portfolio["profit_amount"]) if portfolio["profit_amount"] is not None else None,
            "profit_rate": float(portfolio["profit_rate"]) if portfolio["profit_rate"] is not None else None,
            "position_count": len(portfolio["positions"]),
        },
        "top_scores": [
            {
                "fund_code": item.fund_code,
                "fund_name": fund_names.get(item.fund_code),
                "score": float(item.total_score) if item.total_score is not None else None,
                "rating": item.rating,
                "reason": item.reason,
            }
            for item in scores
        ],
        "alerts": [
            {
                "fund_code": item.fund_code,
                "fund_name": fund_names.get(item.fund_code or ""),
                "title": item.title,
                "level": item.alert_level,
            }
            for item in alerts[:10]
        ],
        "high_correlation_pairs": [
            {
                "fund_a": item["fund_a"],
                "fund_a_name": fund_names.get(item["fund_a"]),
                "fund_b": item["fund_b"],
                "fund_b_name": fund_names.get(item["fund_b"]),
                "correlation": item["correlation"],
            }
            for item in high_correlation_pairs[:10]
        ],
    }


def generate_daily_report(db: Session) -> AIReport:
    data = collect_daily_report_data(db)
    prompt = DAILY_REPORT_PROMPT.format(fund_data=data)
    model_name = get_settings().ollama_model
    is_fallback = False
    fallback_reason = None
    try:
        content = OllamaClient().generate(prompt)
        if not content:
            fallback_reason = "Ollama 返回了空内容"
            content = _fallback_with_error(data, fallback_reason)
            model_name = "rule-fallback"
            is_fallback = True
        else:
            forbidden = _contains_forbidden(content)
            if forbidden:
                fallback_reason = f"AI 输出包含受限表达：{forbidden}"
                content = _fallback_with_error(data, fallback_reason)
                model_name = "rule-fallback"
                is_fallback = True
    except Exception as exc:
        fallback_reason = str(exc)
        content = _fallback_with_error(data, exc)
        model_name = "rule-fallback"
        is_fallback = True
    report = AIReport(
        report_type="daily",
        title="每日基金简报",
        content=_sanitize(content),
        model_name=model_name,
        is_fallback=is_fallback,
        fallback_reason=fallback_reason,
        input_snapshot=_snapshot(data),
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


def _fallback_fund_explanation(fund_code: str, reason: Exception | str) -> str:
    return (
        "AI 调用失败，已使用规则兜底\n"
        f"失败原因：{reason}\n\n"
        f"{fund_code} 当前使用规则解释：请结合收益率、最大回撤、波动率和评分原因综合观察。"
        "本说明不构成投资建议。"
    )


def generate_fund_explanation(db: Session, fund_code: str) -> AIReport:
    fund_code = fund_code.zfill(6)
    fund = db.scalar(select(FundInfo).where(FundInfo.fund_code == fund_code))
    indicator = db.scalar(
        select(FundIndicator).where(FundIndicator.fund_code == fund_code).order_by(FundIndicator.calc_date.desc())
    )
    score = db.scalar(select(FundScore).where(FundScore.fund_code == fund_code).order_by(FundScore.score_date.desc()))
    data = {
        "fund_code": fund_code,
        "fund_name": fund.fund_name if fund else None,
        "indicator": indicator.__dict__ if indicator else None,
        "score": score.__dict__ if score else None,
    }
    prompt = FUND_EXPLAIN_PROMPT.format(fund_data=data)
    model_name = get_settings().ollama_model
    is_fallback = False
    fallback_reason = None
    try:
        content = OllamaClient().generate(prompt)
        if not content:
            fallback_reason = "Ollama 返回了空内容"
            content = _fallback_fund_explanation(fund_code, fallback_reason)
            model_name = "rule-fallback"
            is_fallback = True
        else:
            forbidden = _contains_forbidden(content)
            if forbidden:
                fallback_reason = f"AI 输出包含受限表达：{forbidden}"
                content = _fallback_fund_explanation(fund_code, fallback_reason)
                model_name = "rule-fallback"
                is_fallback = True
    except Exception as exc:
        fallback_reason = str(exc)
        content = _fallback_fund_explanation(fund_code, exc)
        model_name = "rule-fallback"
        is_fallback = True
    report = AIReport(
        report_type="fund",
        target_code=fund_code,
        title=f"{fund_code} 基金解释",
        content=_sanitize(content),
        model_name=model_name,
        is_fallback=is_fallback,
        fallback_reason=fallback_reason,
        input_snapshot=_snapshot(data),
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


def report_history(db: Session, report_type: str = "daily", limit: int = 30) -> list[AIReport]:
    return list(
        db.scalars(
            select(AIReport)
            .where(AIReport.report_type == report_type)
            .order_by(AIReport.created_at.desc())
            .limit(limit)
        )
    )


def latest_fund_report(db: Session, fund_code: str) -> AIReport | None:
    return db.scalar(
        select(AIReport)
        .where(AIReport.report_type == "fund", AIReport.target_code == fund_code.zfill(6))
        .order_by(AIReport.created_at.desc())
        .limit(1)
    )


def latest_daily_context(db: Session) -> dict:
    return collect_daily_report_data(db)
