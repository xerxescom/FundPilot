from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.thresholds import get_thresholds
from app.db.models import AlertEvent, FundIndicator, FundNav, FundScore, PortfolioPosition
from app.db.models.fund import FundInfo
from app.services.portfolio_service import portfolio_drawdown_1m, position_summary


def _build_name_map(db: Session, codes: list[str]) -> dict[str, str]:
    """Return {fund_code: fund_name} for the given codes, falling back to the code itself."""
    if not codes:
        return {}
    infos = db.scalars(select(FundInfo).where(FundInfo.fund_code.in_(codes))).all()
    return {info.fund_code: info.fund_name for info in infos}


def _fund_label(code: str, name_map: dict[str, str]) -> str:
    """Return 'Name(code)' if name is available, else just 'code'."""
    name = name_map.get(code)
    return f"{name}({code})" if name else code


def _alert_to_dict(alert: AlertEvent, name_map: dict[str, str]) -> dict:
    return {
        "id": alert.id,
        "alert_type": alert.alert_type,
        "fund_code": alert.fund_code,
        "fund_name": name_map.get(alert.fund_code) if alert.fund_code else None,
        "alert_level": alert.alert_level,
        "title": alert.title,
        "content": alert.content,
        "status": alert.status,
        "is_read": alert.is_read,
        "created_at": alert.created_at,
    }


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
        existing.status = existing.status or "unread"
        alert = existing
    else:
        alert = AlertEvent(
            alert_type=alert_type,
            fund_code=fund_code,
            alert_level=level,
            title=title,
            content=content,
            status="unread",
        )
        db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def generate_alerts(db: Session) -> list[AlertEvent]:
    thresholds = get_thresholds()
    alerts: list[AlertEvent] = []

    # Collect all fund codes so we can look up names in one batch
    latest_navs = db.scalars(
        select(FundNav)
        .where(FundNav.daily_return <= Decimal(str(thresholds.daily_drop_alert)))
        .order_by(FundNav.nav_date.desc())
    ).all()
    seen: set[str] = set()
    nav_codes: list[str] = []
    for nav in latest_navs:
        if nav.fund_code not in seen:
            seen.add(nav.fund_code)
            nav_codes.append(nav.fund_code)

    indicator_list = list(
        db.scalars(
            select(FundIndicator).where(
                FundIndicator.max_drawdown_1y <= Decimal(str(thresholds.portfolio_drawdown_alert))
            )
        )
    )

    scores = db.scalars(select(FundScore).order_by(FundScore.fund_code, FundScore.score_date.desc())).all()
    by_code: dict[str, list[FundScore]] = {}
    for score in scores:
        by_code.setdefault(score.fund_code, []).append(score)

    all_codes = list(
        set(nav_codes)
        | {ind.fund_code for ind in indicator_list}
        | set(by_code.keys())
    )
    name_map = _build_name_map(db, all_codes)

    # Daily drop alerts
    for code in nav_codes:
        nav = next(n for n in latest_navs if n.fund_code == code)
        label = _fund_label(code, name_map)
        alerts.append(
            _upsert_alert(
                db,
                "daily_drop",
                code,
                "high",
                f"{label} 单日跌幅超过 {abs(thresholds.daily_drop_alert):.0%}",
                f"{nav.nav_date} 日涨跌幅为 {nav.daily_return}",
            )
        )

    # Drawdown alerts
    for indicator in indicator_list:
        label = _fund_label(indicator.fund_code, name_map)
        alerts.append(
            _upsert_alert(
                db,
                "drawdown",
                indicator.fund_code,
                "medium",
                f"{label} 回撤超过阈值",
                f"近 1 年最大回撤为 {indicator.max_drawdown_1y}",
            )
        )

    # Score drop alerts
    for fund_code, items in by_code.items():
        if len(items) >= 2 and items[0].total_score is not None and items[1].total_score is not None:
            if items[1].total_score - items[0].total_score >= Decimal(str(thresholds.score_drop_alert)):
                label = _fund_label(fund_code, name_map)
                alerts.append(
                    _upsert_alert(
                        db,
                        "score_drop",
                        fund_code,
                        "medium",
                        f"{label} 评分下降超过 {thresholds.score_drop_alert:.0f} 分",
                        f"评分由 {items[1].total_score} 降至 {items[0].total_score}",
                    )
                )

    # Position weight alerts
    summaries = [position_summary(db, item) for item in db.scalars(select(PortfolioPosition))]
    total = sum((s["current_value"] or Decimal("0")) for s in summaries)
    if total:
        pos_codes = [s["position"].fund_code for s in summaries]
        pos_name_map = _build_name_map(db, pos_codes)
        for summary in summaries:
            value = summary["current_value"] or Decimal("0")
            if value / total > Decimal(str(thresholds.portfolio_concentration)):
                code = summary["position"].fund_code
                label = _fund_label(code, pos_name_map)
                alerts.append(
                    _upsert_alert(
                        db,
                        "position_weight",
                        code,
                        "medium",
                        f"{label} 持仓占比超过 {thresholds.portfolio_concentration:.0%}",
                        f"当前估算占比为 {(value / total):.2%}",
                    )
                )

    drawdown_1m = portfolio_drawdown_1m(db)
    if drawdown_1m is not None and drawdown_1m <= Decimal(str(thresholds.portfolio_drawdown_alert)):
        alerts.append(
            _upsert_alert(
                db,
                "portfolio_drawdown",
                None,
                "medium",
                f"组合近 1 月回撤超过 {abs(thresholds.portfolio_drawdown_alert):.0%}",
                f"当前估算近 1 月组合最大回撤为 {drawdown_1m:.2%}",
            )
        )
    return alerts


def unread_alerts(db: Session) -> list[dict]:
    events = list(
        db.scalars(
            select(AlertEvent)
            .where(AlertEvent.status == "unread", AlertEvent.is_read.is_(False))
            .order_by(AlertEvent.created_at.desc())
        )
    )
    codes = [e.fund_code for e in events if e.fund_code]
    name_map = _build_name_map(db, codes)
    return [_alert_to_dict(e, name_map) for e in events]


def update_alert_status(db: Session, alert_id: int, status: str) -> AlertEvent | None:
    if status not in {"unread", "read", "handled", "ignored"}:
        raise ValueError("status must be one of unread, read, handled, ignored")
    alert = db.get(AlertEvent, alert_id)
    if not alert:
        return None
    alert.status = status
    alert.is_read = status != "unread"
    db.commit()
    db.refresh(alert)
    return alert
