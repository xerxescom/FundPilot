from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FundIndicator, FundScore, Watchlist
from app.services import correlation_service, portfolio_service, score_service


def _float(value: Decimal | int | float | None) -> float | None:
    return float(value) if value is not None else None


def compare_funds(db: Session, codes: list[str]) -> dict:
    codes = [code.zfill(6) for code in codes if code.strip()]
    labels = {
        item.fund_code: {
            "fund_name": item.fund_name,
            "industry": item.industry,
        }
        for item in db.scalars(select(Watchlist).where(Watchlist.fund_code.in_(codes)))
    }
    rows = []
    for code in codes:
        indicator = db.scalar(
            select(FundIndicator).where(FundIndicator.fund_code == code).order_by(FundIndicator.calc_date.desc())
        )
        score = score_service.latest_score(db, code)
        meta = labels.get(code, {})
        rows.append(
            {
                "fund_code": code,
                "fund_name": meta.get("fund_name"),
                "industry": meta.get("industry"),
                "calc_date": indicator.calc_date if indicator else None,
                "return_1m": _float(indicator.return_1m) if indicator else None,
                "return_3m": _float(indicator.return_3m) if indicator else None,
                "return_1y": _float(indicator.return_1y) if indicator else None,
                "max_drawdown_1y": _float(indicator.max_drawdown_1y) if indicator else None,
                "volatility_1y": _float(indicator.volatility_1y) if indicator else None,
                "sharpe_1y": _float(indicator.sharpe_1y) if indicator else None,
                "win_rate_1y": _float(indicator.win_rate_1y) if indicator else None,
                "score": _float(score.total_score) if score else None,
                "rating": score.rating if score else None,
                "reason": score.reason if score else None,
            }
        )
    corr = correlation_service.calculate_correlation(db)
    correlation = {}
    for left in codes:
        for right in codes:
            if left == right or corr.empty or left not in corr.index or right not in corr.columns:
                continue
            value = corr.loc[left, right]
            if value == value:
                correlation[f"{left}-{right}"] = round(float(value), 4)
    return {"funds": rows, "correlation": correlation}


def score_trend(db: Session, fund_code: str) -> list[dict]:
    fund_code = fund_code.zfill(6)
    rows = db.scalars(
        select(FundScore).where(FundScore.fund_code == fund_code).order_by(FundScore.score_date.asc())
    ).all()
    return [
        {
            "fund_code": row.fund_code,
            "score_date": row.score_date,
            "total_score": _float(row.total_score),
            "rating": row.rating,
            "return_score": _float(row.return_score),
            "drawdown_score": _float(row.drawdown_score),
            "volatility_score": _float(row.volatility_score),
            "stability_score": _float(row.stability_score),
            "size_score": _float(row.size_score),
            "trade_status_score": _float(row.trade_status_score),
        }
        for row in rows
    ]


def industry_overview(db: Session) -> list[dict]:
    positions = portfolio_service.portfolio_overview(db)["positions"]
    value_by_code = {
        item["position"].fund_code: item["current_value"] or Decimal("0")
        for item in positions
    }
    total_value = sum(value_by_code.values(), Decimal("0"))
    groups: dict[str, dict] = {}
    for item in db.scalars(select(Watchlist).where(Watchlist.is_active.is_(True))):
        industry = item.industry or "未分类"
        group = groups.setdefault(
            industry,
            {"industry": industry, "fund_count": 0, "scores": [], "position_value": Decimal("0")},
        )
        group["fund_count"] += 1
        score = score_service.latest_score(db, item.fund_code)
        if score and score.total_score is not None:
            group["scores"].append(float(score.total_score))
        group["position_value"] += value_by_code.get(item.fund_code, Decimal("0"))
    result = []
    for group in groups.values():
        scores = group.pop("scores")
        value = group["position_value"]
        result.append(
            {
                **group,
                "position_value": float(value),
                "position_weight": float(value / total_value) if total_value else None,
                "avg_score": round(sum(scores) / len(scores), 2) if scores else None,
            }
        )
    return sorted(result, key=lambda item: (item["position_value"], item["fund_count"]), reverse=True)


def risk_return_points(db: Session) -> list[dict]:
    overview = portfolio_service.portfolio_overview(db)
    total_value = overview["total_value"] or Decimal("0")
    weight_by_code = {}
    if total_value:
        for item in overview["positions"]:
            current_value = item["current_value"] or Decimal("0")
            weight_by_code[item["position"].fund_code] = float(current_value / total_value)
    rows = []
    for item in db.scalars(select(Watchlist).where(Watchlist.is_active.is_(True))):
        indicator = db.scalar(
            select(FundIndicator)
            .where(FundIndicator.fund_code == item.fund_code)
            .order_by(FundIndicator.calc_date.desc())
        )
        score = score_service.latest_score(db, item.fund_code)
        if not indicator:
            continue
        rows.append(
            {
                "fund_code": item.fund_code,
                "fund_name": item.fund_name,
                "industry": item.industry or "未分类",
                "return_1y": _float(indicator.return_1y),
                "max_drawdown_1y": _float(indicator.max_drawdown_1y),
                "volatility_1y": _float(indicator.volatility_1y),
                "score": _float(score.total_score) if score else None,
                "position_weight": weight_by_code.get(item.fund_code, 0.0),
            }
        )
    return rows
