from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AlertEvent, FundIndicator, FundNav, FundScore, PortfolioPosition
from app.services.portfolio_service import portfolio_drawdown_1m, position_summary


def _upsert_alert(
    db: Session,
    alert_type: str,
    fund_code: str | None,
    level: str,
    title: str,
    content: str,
) -> AlertEvent:
    existing = db.scalar(
        select(AlertEvent).where(
            AlertEvent.alert_type == alert_type,
            AlertEvent.fund_code == fund_code,
            AlertEvent.title == title,
        )
    )
    if existing:
        existing.content = content
        existing.alert_level = level
        alert = existing
    else:
        alert = AlertEvent(
            alert_type=alert_type,
            fund_code=fund_code,
            alert_level=level,
            title=title,
            content=content,
        )
        db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def generate_alerts(db: Session) -> list[AlertEvent]:
    alerts: list[AlertEvent] = []
    latest_navs = db.scalars(
        select(FundNav).where(FundNav.daily_return <= Decimal("-0.03")).order_by(FundNav.nav_date.desc())
    ).all()
    seen = set()
    for nav in latest_navs:
        if nav.fund_code in seen:
            continue
        seen.add(nav.fund_code)
        alerts.append(
            _upsert_alert(
                db,
                "daily_drop",
                nav.fund_code,
                "high",
                f"{nav.fund_code} 单日跌幅超过 3%",
                f"{nav.nav_date} 日涨跌幅为 {nav.daily_return}",
            )
        )

    for indicator in db.scalars(select(FundIndicator).where(FundIndicator.max_drawdown_1y <= Decimal("-0.08"))):
        alerts.append(
            _upsert_alert(
                db,
                "drawdown",
                indicator.fund_code,
                "medium",
                f"{indicator.fund_code} 回撤超过阈值",
                f"近1年最大回撤为 {indicator.max_drawdown_1y}",
            )
        )

    scores = db.scalars(select(FundScore).order_by(FundScore.fund_code, FundScore.score_date.desc())).all()
    by_code: dict[str, list[FundScore]] = {}
    for score in scores:
        by_code.setdefault(score.fund_code, []).append(score)
    for fund_code, items in by_code.items():
        if len(items) >= 2 and items[0].total_score is not None and items[1].total_score is not None:
            if items[1].total_score - items[0].total_score >= Decimal("10"):
                alerts.append(
                    _upsert_alert(
                        db,
                        "score_drop",
                        fund_code,
                        "medium",
                        f"{fund_code} 评分下降超过 10 分",
                        f"评分由 {items[1].total_score} 降至 {items[0].total_score}",
                    )
                )

    summaries = [position_summary(db, item) for item in db.scalars(select(PortfolioPosition))]
    total = sum((s["current_value"] or Decimal("0")) for s in summaries)
    if total:
        for summary in summaries:
            value = summary["current_value"] or Decimal("0")
            if value / total > Decimal("0.30"):
                code = summary["position"].fund_code
                alerts.append(
                    _upsert_alert(
                        db,
                        "position_weight",
                        code,
                        "medium",
                        f"{code} 持仓占比超过 30%",
                        f"当前估算占比为 {(value / total):.2%}",
                    )
                )
    drawdown_1m = portfolio_drawdown_1m(db)
    if drawdown_1m is not None and drawdown_1m <= Decimal("-0.08"):
        alerts.append(
            _upsert_alert(
                db,
                "portfolio_drawdown",
                None,
                "medium",
                "组合近 1 月回撤超过 8%",
                f"当前估算近 1 月组合最大回撤为 {drawdown_1m:.2%}",
            )
        )
    return alerts


def unread_alerts(db: Session) -> list[AlertEvent]:
    return list(
        db.scalars(select(AlertEvent).where(AlertEvent.is_read.is_(False)).order_by(AlertEvent.created_at.desc()))
    )
