from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FundInfo, FundIndicator, FundScore, Watchlist
from app.services.indicator_service import latest_indicator
from app.services.nav_service import decimal_or_none


def _value(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def score_indicator(indicator: FundIndicator, fund: FundInfo | None = None) -> dict:
    ret_1y = _value(indicator.return_1y)
    drawdown = _value(indicator.max_drawdown_1y)
    volatility = _value(indicator.volatility_1y)
    win_rate = _value(indicator.win_rate_1y)

    reasons: list[str] = []

    if ret_1y is None:
        return_score = 10
        reasons.append("近1年收益数据不足，收益评分降级处理")
    elif ret_1y > 0.20:
        return_score = 30
        reasons.append("近1年收益表现突出")
    elif ret_1y > 0.10:
        return_score = 24
        reasons.append("近1年收益表现较好")
    elif ret_1y > 0.05:
        return_score = 18
        reasons.append("近1年收益表现中等")
    elif ret_1y >= 0:
        return_score = 12
        reasons.append("近1年收益偏弱但仍为正")
    else:
        return_score = 5
        reasons.append("近1年收益为负，需要谨慎观察")

    if drawdown is None:
        drawdown_score = 10
        reasons.append("回撤数据不足，回撤评分降级处理")
    elif drawdown > -0.10:
        drawdown_score = 25
        reasons.append("最大回撤控制较好")
    elif drawdown > -0.20:
        drawdown_score = 20
        reasons.append("最大回撤处于可接受区间")
    elif drawdown > -0.30:
        drawdown_score = 12
        reasons.append("最大回撤偏大")
    else:
        drawdown_score = 5
        reasons.append("最大回撤较深，风险较高")

    if volatility is None:
        volatility_score = 6
        reasons.append("波动率数据不足，波动评分降级处理")
    elif volatility < 0.15:
        volatility_score = 15
        reasons.append("年化波动率较低")
    elif volatility < 0.25:
        volatility_score = 10
        reasons.append("年化波动率适中")
    elif volatility < 0.35:
        volatility_score = 6
        reasons.append("年化波动率偏高")
    else:
        volatility_score = 3
        reasons.append("年化波动率较高，需要控制仓位风险")

    if win_rate is None:
        stability_score = 6
    elif win_rate >= 0.55:
        stability_score = 15
    elif win_rate >= 0.50:
        stability_score = 11
    elif win_rate >= 0.45:
        stability_score = 8
    else:
        stability_score = 5

    fund_size = float(fund.fund_size) if fund and fund.fund_size is not None else None
    size_score = 6 if fund_size is None else (10 if fund_size >= 10 else 5)
    trade_status_score = 5
    total_score = (
        return_score
        + drawdown_score
        + volatility_score
        + stability_score
        + size_score
        + trade_status_score
    )
    rating = (
        "重点关注"
        if total_score >= 85
        else "可以观察"
        if total_score >= 70
        else "一般"
        if total_score >= 60
        else "暂不关注"
    )
    return {
        "total_score": total_score,
        "return_score": return_score,
        "drawdown_score": drawdown_score,
        "volatility_score": volatility_score,
        "stability_score": stability_score,
        "size_score": size_score,
        "trade_status_score": trade_status_score,
        "rating": rating,
        "reason": "；".join(reasons),
    }


def calculate_and_save_score(db: Session, fund_code: str) -> FundScore:
    fund_code = fund_code.zfill(6)
    indicator = latest_indicator(db, fund_code)
    if not indicator:
        raise ValueError(f"No indicator found for {fund_code}")
    fund = db.scalar(select(FundInfo).where(FundInfo.fund_code == fund_code))
    scored = score_indicator(indicator, fund)
    existing = db.scalar(
        select(FundScore).where(
            FundScore.fund_code == fund_code,
            FundScore.score_date == indicator.calc_date,
        )
    )
    numeric_fields = {
        key: decimal_or_none(scored[key], "0.01")
        for key in [
            "total_score",
            "return_score",
            "drawdown_score",
            "volatility_score",
            "stability_score",
            "size_score",
            "trade_status_score",
        ]
    }
    values = {**numeric_fields, "rating": scored["rating"], "reason": scored["reason"]}
    if existing:
        for key, value in values.items():
            setattr(existing, key, value)
        score = existing
    else:
        score = FundScore(fund_code=fund_code, score_date=indicator.calc_date, **values)
        db.add(score)
    db.commit()
    db.refresh(score)
    return score


def latest_score(db: Session, fund_code: str) -> FundScore | None:
    return db.scalar(
        select(FundScore)
        .where(FundScore.fund_code == fund_code.zfill(6))
        .order_by(FundScore.score_date.desc())
        .limit(1)
    )


def calculate_watchlist_scores(db: Session) -> dict[str, str]:
    result = {}
    for item in db.scalars(select(Watchlist).where(Watchlist.is_active.is_(True))):
        try:
            result[item.fund_code] = str(calculate_and_save_score(db, item.fund_code).total_score)
        except Exception as exc:
            result[item.fund_code] = f"failed: {exc}"
    return result


def top_scores(db: Session, limit: int = 20) -> list[FundScore]:
    scores = list(
        db.scalars(select(FundScore).order_by(FundScore.score_date.desc(), FundScore.total_score.desc()))
    )
    latest_by_code: dict[str, FundScore] = {}
    for score in scores:
        if score.fund_code not in latest_by_code:
            latest_by_code[score.fund_code] = score
    return sorted(
        latest_by_code.values(),
        key=lambda item: (item.total_score is not None, item.total_score or 0),
        reverse=True,
    )[:limit]
