from __future__ import annotations

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import FundInfo, FundIndicator, FundScore, Watchlist
from app.services.indicator_service import latest_indicator
from app.services.nav_service import decimal_or_none

SCORE_STRATEGIES = {
    "default": {
        "name": "默认策略",
        "scenario": "综合观察收益、回撤、波动、稳定性和规模，适合日常基金池排序。",
        "weights": {
            "return_score": 1.0,
            "drawdown_score": 1.0,
            "volatility_score": 1.0,
            "stability_score": 1.0,
            "size_score": 1.0,
            "trade_status_score": 1.0,
        },
    },
    "steady": {
        "name": "稳健型",
        "scenario": "优先观察回撤、波动和胜率，适合低波动持有体验筛选。",
        "weights": {
            "return_score": 0.75,
            "drawdown_score": 1.45,
            "volatility_score": 1.35,
            "stability_score": 1.2,
            "size_score": 1.0,
            "trade_status_score": 1.0,
        },
    },
    "growth": {
        "name": "进攻型",
        "scenario": "更关注收益弹性，同时保留基础风险约束，适合进攻观察池排序。",
        "weights": {
            "return_score": 1.55,
            "drawdown_score": 0.75,
            "volatility_score": 0.7,
            "stability_score": 0.9,
            "size_score": 0.8,
            "trade_status_score": 1.0,
        },
    },
    "low_drawdown": {
        "name": "低回撤型",
        "scenario": "重点压低回撤和波动，适合防守观察和组合稳定器筛选。",
        "weights": {
            "return_score": 0.6,
            "drawdown_score": 1.8,
            "volatility_score": 1.45,
            "stability_score": 1.05,
            "size_score": 0.9,
            "trade_status_score": 1.0,
        },
    },
}


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
        reasons.append("年化波动率较高，需要控制持仓风险")

    if win_rate is None:
        stability_score = 6
        reasons.append("胜率数据不足，稳定性评分降级处理")
    elif win_rate >= 0.55:
        stability_score = 15
        reasons.append("近1年上涨天数占比较高")
    elif win_rate >= 0.50:
        stability_score = 11
        reasons.append("近1年胜率略高于均衡水平")
    elif win_rate >= 0.45:
        stability_score = 8
        reasons.append("近1年胜率接近均衡水平")
    else:
        stability_score = 5
        reasons.append("近1年胜率偏低")

    fund_size = float(fund.fund_size) if fund and fund.fund_size is not None else None
    size_score = 6 if fund_size is None else (10 if fund_size >= 10 else 5)
    if fund_size is None:
        reasons.append("基金规模数据缺失，规模评分采用中性分")
    elif fund_size < 10:
        reasons.append("基金规模偏小，流动性和稳定性需继续观察")

    trade_status_score = 5
    total_score = return_score + drawdown_score + volatility_score + stability_score + size_score + trade_status_score
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


def available_strategies() -> list[dict[str, str]]:
    return [
        {"key": key, "name": config["name"], "scenario": config["scenario"]}
        for key, config in SCORE_STRATEGIES.items()
    ]


def _rating(total_score: float) -> str:
    return (
        "重点关注"
        if total_score >= 85
        else "可以观察"
        if total_score >= 70
        else "一般"
        if total_score >= 60
        else "暂不关注"
    )


def score_indicator_with_strategy(
    indicator: FundIndicator,
    fund: FundInfo | None = None,
    strategy: str = "default",
) -> dict:
    if strategy not in SCORE_STRATEGIES:
        raise ValueError(f"Unknown score strategy: {strategy}")
    base = score_indicator(indicator, fund)
    weights = SCORE_STRATEGIES[strategy]["weights"]
    weighted_total = sum(float(base[field]) * float(weight) for field, weight in weights.items())
    max_weighted_total = sum(
        max_score * float(weights[field])
        for field, max_score in {
            "return_score": 30,
            "drawdown_score": 25,
            "volatility_score": 15,
            "stability_score": 15,
            "size_score": 10,
            "trade_status_score": 5,
        }.items()
    )
    total_score = round(weighted_total / max_weighted_total * 100, 2) if max_weighted_total else 0
    strategy_name = SCORE_STRATEGIES[strategy]["name"]
    return {
        **base,
        "strategy": strategy,
        "strategy_name": strategy_name,
        "strategy_scenario": SCORE_STRATEGIES[strategy]["scenario"],
        "total_score": total_score,
        "rating": _rating(total_score),
        "reason": f"{strategy_name}：{base['reason']}",
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
    """Return each fund's latest score, ordered by total score descending."""
    latest_date_sq = (
        select(
            FundScore.fund_code,
            func.max(FundScore.score_date).label("latest_date"),
        )
        .group_by(FundScore.fund_code)
        .subquery()
    )

    return list(
        db.scalars(
            select(FundScore)
            .join(
                latest_date_sq,
                (FundScore.fund_code == latest_date_sq.c.fund_code)
                & (FundScore.score_date == latest_date_sq.c.latest_date),
            )
            .order_by(FundScore.total_score.desc().nulls_last())
            .limit(limit)
        )
    )


def top_scores_by_strategy(db: Session, strategy: str = "default", limit: int = 20) -> list[dict]:
    if strategy == "default":
        fund_names = {
            item.fund_code: item.fund_name
            for item in db.scalars(select(FundInfo).where(FundInfo.fund_name.is_not(None))).all()
        }
        return [
            {
                "fund_code": item.fund_code,
                "fund_name": fund_names.get(item.fund_code),
                "score_date": item.score_date,
                "total_score": float(item.total_score) if item.total_score is not None else None,
                "return_score": float(item.return_score) if item.return_score is not None else None,
                "drawdown_score": float(item.drawdown_score) if item.drawdown_score is not None else None,
                "volatility_score": float(item.volatility_score) if item.volatility_score is not None else None,
                "stability_score": float(item.stability_score) if item.stability_score is not None else None,
                "size_score": float(item.size_score) if item.size_score is not None else None,
                "trade_status_score": float(item.trade_status_score) if item.trade_status_score is not None else None,
                "rating": item.rating,
                "reason": item.reason,
                "strategy": "default",
                "strategy_name": SCORE_STRATEGIES["default"]["name"],
                "strategy_scenario": SCORE_STRATEGIES["default"]["scenario"],
            }
            for item in top_scores(db, limit)
        ]

    if strategy not in SCORE_STRATEGIES:
        raise ValueError(f"Unknown score strategy: {strategy}")

    latest_indicator_sq = (
        select(
            FundIndicator.fund_code,
            func.max(FundIndicator.calc_date).label("latest_date"),
        )
        .group_by(FundIndicator.fund_code)
        .subquery()
    )
    rows = db.execute(
        select(FundIndicator, FundInfo)
        .join(
            latest_indicator_sq,
            (FundIndicator.fund_code == latest_indicator_sq.c.fund_code)
            & (FundIndicator.calc_date == latest_indicator_sq.c.latest_date),
        )
        .outerjoin(FundInfo, FundInfo.fund_code == FundIndicator.fund_code)
    ).all()

    scored = []
    for indicator, fund in rows:
        item = score_indicator_with_strategy(indicator, fund, strategy)
        scored.append(
            {
                "fund_code": indicator.fund_code,
                "fund_name": fund.fund_name if fund else None,
                "score_date": indicator.calc_date,
                **item,
            }
        )
    return sorted(scored, key=lambda item: item["total_score"] or 0, reverse=True)[:limit]
