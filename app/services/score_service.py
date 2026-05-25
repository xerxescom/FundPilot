from __future__ import annotations

from datetime import date
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import FundInfo, FundIndicator, FundNav, FundScore, Watchlist
from app.services.indicator_service import latest_indicator
from app.services.nav_service import decimal_or_none
from app.services import correlation_service, market_service, portfolio_service

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


def _confidence_level(score: int) -> str:
    if score >= 80:
        return "high"
    if score >= 55:
        return "medium"
    return "low"


def _is_stale(calc_date: date | None) -> bool:
    return bool(calc_date and (date.today() - calc_date).days > 10)


def _trade_blocked(fund: FundInfo | None) -> bool:
    if not fund or not fund.buy_status:
        return False
    blocked_words = ("暂停", "封闭", "停止", "不可", "关闭")
    return any(word in fund.buy_status for word in blocked_words)


def _score_trend(ret_1m: float | None, ret_3m: float | None, ret_6m: float | None) -> tuple[int, list[str], list[str]]:
    reasons: list[str] = []
    flags: list[str] = []
    if ret_1m is None and ret_3m is None and ret_6m is None:
        return 4, ["近期趋势数据不足，趋势评分采用保守分"], ["trend_data_missing"]

    trend_score = 4
    if ret_1m is not None and ret_1m > 0:
        trend_score += 2
    if ret_3m is not None and ret_3m > 0:
        trend_score += 2
    if ret_6m is not None and ret_6m > 0:
        trend_score += 2
    trend_score = min(trend_score, 8)

    if ret_1m is not None and ret_3m is not None and ret_1m > 0.08 and ret_3m > 0.15:
        flags.append("near_term_overheated")
        reasons.append("近1月和近3月涨幅偏快，存在追高风险")
    elif ret_1m is not None and ret_3m is not None and ret_1m < 0 and ret_3m < 0:
        flags.append("trend_weakening")
        reasons.append("近1月和近3月趋势偏弱，需要等待趋势确认")
    elif trend_score >= 7:
        reasons.append("近1月、3月和6月趋势对评分形成支持")
    else:
        reasons.append("近期趋势支持度一般")

    return trend_score, reasons, flags


def _score_sharpe(sharpe: float | None) -> tuple[int, list[str], list[str]]:
    if sharpe is None:
        return 3, ["夏普比率数据不足，风险调整收益评分采用保守分"], ["sharpe_missing"]
    if sharpe >= 1.2:
        return 7, ["夏普比率较高，单位波动带来的收益较好"], []
    if sharpe >= 0.6:
        return 5, ["夏普比率处于可接受区间"], []
    if sharpe >= 0:
        return 3, ["夏普比率偏低，风险调整收益一般"], []
    return 1, ["夏普比率为负，风险调整收益较弱"], ["negative_sharpe"]


def _confidence_score(
    indicator: FundIndicator,
    fund: FundInfo | None,
    risk_flags: list[str],
    nav_stats: dict | None = None,
) -> tuple[int, str, list[str]]:
    score = 100
    notes: list[str] = []
    key_metrics = [
        indicator.return_1y,
        indicator.max_drawdown_1y,
        indicator.volatility_1y,
        indicator.win_rate_1y,
    ]
    missing_key_count = sum(1 for value in key_metrics if value is None)
    score -= missing_key_count * 8
    if missing_key_count:
        notes.append("关键指标缺失，评分可信度下降")
        risk_flags.append("key_metric_missing")

    trend_missing_count = sum(1 for value in [indicator.return_1m, indicator.return_3m, indicator.return_6m] if value is None)
    score -= trend_missing_count * 4
    if trend_missing_count >= 2:
        notes.append("近期趋势样本不足")

    if indicator.sharpe_1y is None:
        score -= 5
    if _is_stale(indicator.calc_date):
        score -= 25
        notes.append("最新指标日期偏旧")
        risk_flags.append("stale_indicator")

    if not fund:
        score -= 15
        notes.append("基金档案缺失")
        risk_flags.append("fund_profile_missing")
    else:
        if fund.fund_size is None:
            score -= 5
        if fund.establish_date is None:
            score -= 5
        if not fund.buy_status:
            score -= 5

    if nav_stats:
        history_days = nav_stats.get("history_days")
        latest_nav_date = nav_stats.get("latest_nav_date")
        if history_days is not None and history_days < 365:
            score -= 15
            notes.append("净值历史不足1年")
            risk_flags.append("short_nav_history")
        if latest_nav_date and (date.today() - latest_nav_date).days > 10:
            score -= 20
            notes.append("最新净值日期偏旧")
            risk_flags.append("stale_nav")

    score = max(0, min(100, score))
    return score, _confidence_level(score), notes


def _buy_window_signal(
    total_score: float,
    confidence_score: int,
    risk_flags: list[str],
    fund: FundInfo | None,
    ret_1m: float | None,
    ret_3m: float | None,
    drawdown: float | None,
    volatility: float | None,
) -> tuple[str, str]:
    if _trade_blocked(fund):
        return "blocked", "交易状态显示当前不具备申购条件，窗口信号被阻断"
    if confidence_score < 55 or "stale_nav" in risk_flags or "stale_indicator" in risk_flags:
        return "cautious", "数据可信度不足或数据偏旧，当前仅适合谨慎观察"
    if "key_metric_missing" in risk_flags:
        return "cautious", "关键指标不完整，高等级窗口信号被降级"
    if drawdown is not None and drawdown <= -0.25:
        return "cautious", "历史回撤偏深，即使分数较高也需要控制风险"
    if "near_term_overheated" in risk_flags:
        return "wait_pullback", "近期涨幅偏快，等待回撤或趋势确认更稳妥"
    if ret_1m is not None and ret_3m is not None and ret_1m < 0 and ret_3m < 0:
        return "wait_pullback", "短中期趋势转弱，等待趋势修复"
    if volatility is not None and volatility >= 0.35:
        return "cautious", "波动率偏高，窗口信号保持谨慎"
    if total_score >= 85 and confidence_score >= 80:
        return "favorable", "质量分、可信度和近期状态共同支持较好的观察窗口"
    if total_score >= 70:
        return "watch", "综合质量尚可，可继续观察并结合仓位约束判断"
    return "cautious", "综合评分尚未形成足够支持，当前以谨慎观察为主"


def _market_signal(db: Session) -> dict:
    context = market_service.latest_market_context(db)
    returns = [item["return_1m"] for item in context if item.get("return_1m") is not None]
    if not returns:
        return {"market_signal": "neutral", "market_reason": "市场环境数据不足，窗口信号不做市场加成"}
    avg_return = sum(float(item) for item in returns) / len(returns)
    if avg_return >= 0.03:
        return {"market_signal": "supportive", "market_reason": "主要指数近1月整体偏强，对窗口信号形成支持"}
    if avg_return <= -0.03:
        return {"market_signal": "weak", "market_reason": "主要指数近1月整体偏弱，窗口信号需要降级观察"}
    return {"market_signal": "neutral", "market_reason": "主要指数近1月表现中性，市场环境不构成明显加减分"}


def _portfolio_fit(db: Session, fund_code: str) -> dict:
    fund_code = fund_code.zfill(6)
    overview = portfolio_service.portfolio_overview(db)
    total_value = overview["total_value"]
    held_weight = None
    for item in overview["positions"]:
        position = item["position"]
        if position.fund_code == fund_code and total_value and item["current_value"] is not None:
            held_weight = float(item["current_value"] / total_value)
            break

    related_pairs = [
        pair for pair in correlation_service.high_correlation_pairs(db) if fund_code in {pair["fund_a"], pair["fund_b"]}
    ]
    score = 85
    reasons: list[str] = []
    flags: list[str] = []
    if held_weight is not None:
        score -= 25
        reasons.append(f"该基金已在组合中，当前估算权重约 {held_weight:.1%}")
        flags.append("already_held")
        if held_weight >= 0.30:
            score -= 20
            reasons.append("持仓权重偏高，继续加仓会放大集中度")
            flags.append("portfolio_concentration")
    if related_pairs:
        score -= 20
        pair_text = "、".join(
            pair["fund_b"] if pair["fund_a"] == fund_code else pair["fund_a"] for pair in related_pairs[:3]
        )
        reasons.append(f"与组合或自选中的 {pair_text} 相关性较高，分散化贡献有限")
        flags.append("high_correlation")
    if not overview["positions"]:
        reasons.append("当前没有持仓数据，组合适配采用中性偏高评估")
    if not reasons:
        reasons.append("未触发持仓集中或高相关规则，组合适配较好")

    score = max(0, min(100, score))
    level = "high" if score >= 75 else "medium" if score >= 50 else "low"
    return {
        "portfolio_fit_score": score,
        "portfolio_fit_level": level,
        "portfolio_fit_reason": "；".join(reasons),
        "portfolio_risk_flags": flags,
    }


def _apply_context(payload: dict, market: dict, portfolio: dict) -> dict:
    risk_flags = set(payload.get("risk_flags") or [])
    risk_flags.update(portfolio.get("portfolio_risk_flags") or [])
    signal = payload.get("buy_window_signal")
    reason = payload.get("buy_window_reason") or ""

    if market["market_signal"] == "weak" and signal == "favorable":
        signal = "watch"
        reason = f"{reason}；但市场环境偏弱，窗口信号降为可以观察"
        risk_flags.add("market_weak")
    elif market["market_signal"] == "weak" and signal == "watch":
        signal = "wait_pullback"
        reason = f"{reason}；市场环境偏弱，等待趋势确认更稳妥"
        risk_flags.add("market_weak")

    if portfolio["portfolio_fit_level"] == "low" and signal in {"favorable", "watch"}:
        signal = "cautious"
        reason = f"{reason}；组合适配偏低，需先控制集中度或重复配置"
    elif portfolio["portfolio_fit_level"] == "medium" and signal == "favorable":
        signal = "watch"
        reason = f"{reason}；组合适配一般，窗口信号降为观察"

    payload.update(
        {
            **market,
            "portfolio_fit_score": portfolio["portfolio_fit_score"],
            "portfolio_fit_level": portfolio["portfolio_fit_level"],
            "portfolio_fit_reason": portfolio["portfolio_fit_reason"],
            "buy_window_signal": signal,
            "buy_window_reason": reason,
            "risk_flags": sorted(risk_flags),
        }
    )
    return payload


def score_indicator(
    indicator: FundIndicator,
    fund: FundInfo | None = None,
    nav_stats: dict | None = None,
) -> dict:
    ret_1y = _value(indicator.return_1y)
    ret_1m = _value(indicator.return_1m)
    ret_3m = _value(indicator.return_3m)
    ret_6m = _value(indicator.return_6m)
    drawdown = _value(indicator.max_drawdown_1y)
    volatility = _value(indicator.volatility_1y)
    win_rate = _value(indicator.win_rate_1y)
    sharpe = _value(indicator.sharpe_1y)

    reasons: list[str] = []
    risk_flags: list[str] = []

    if ret_1y is None:
        long_return_score = 6
        reasons.append("近1年收益数据不足，收益评分降级处理")
    elif ret_1y > 0.20:
        long_return_score = 22
        reasons.append("近1年收益表现突出，长期收益质量对评分贡献较高")
    elif ret_1y > 0.10:
        long_return_score = 18
        reasons.append("近1年收益表现较好")
    elif ret_1y > 0.05:
        long_return_score = 14
        reasons.append("近1年收益表现中等")
    elif ret_1y >= 0:
        long_return_score = 10
        reasons.append("近1年收益偏弱但仍为正")
    else:
        long_return_score = 4
        reasons.append("近1年收益为负，需要谨慎观察")
    trend_score, trend_reasons, trend_flags = _score_trend(ret_1m, ret_3m, ret_6m)
    reasons.extend(trend_reasons)
    risk_flags.extend(trend_flags)
    return_score = long_return_score + trend_score

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
        win_rate_score = 3
        reasons.append("胜率数据不足，稳定性评分降级处理")
    elif win_rate >= 0.55:
        win_rate_score = 8
        reasons.append("近1年上涨天数占比较高")
    elif win_rate >= 0.50:
        win_rate_score = 6
        reasons.append("近1年胜率略高于均衡水平")
    elif win_rate >= 0.45:
        win_rate_score = 5
        reasons.append("近1年胜率接近均衡水平")
    else:
        win_rate_score = 3
        reasons.append("近1年胜率偏低")
    sharpe_score, sharpe_reasons, sharpe_flags = _score_sharpe(sharpe)
    reasons.extend(sharpe_reasons)
    risk_flags.extend(sharpe_flags)
    stability_score = win_rate_score + sharpe_score

    fund_size = float(fund.fund_size) if fund and fund.fund_size is not None else None
    size_score = 7 if fund_size is None else (10 if fund_size >= 10 else 5)
    if fund_size is None:
        reasons.append("基金规模数据缺失，规模评分采用中性分")
    elif fund_size < 10:
        reasons.append("基金规模偏小，流动性和稳定性需继续观察")
        risk_flags.append("small_fund_size")

    trade_status_score = 0 if _trade_blocked(fund) else 5
    if _trade_blocked(fund):
        reasons.append("交易状态异常或暂停申购，窗口信号需要阻断")
        risk_flags.append("trade_blocked")

    total_score = return_score + drawdown_score + volatility_score + stability_score + size_score + trade_status_score
    confidence_score, confidence_level, confidence_notes = _confidence_score(indicator, fund, risk_flags, nav_stats)
    reasons.extend(confidence_notes)
    if total_score >= 80 and confidence_score < 55:
        reasons.append("综合分较高但可信度偏低，不能单独作为强信号依据")
    buy_window_signal, buy_window_reason = _buy_window_signal(
        total_score,
        confidence_score,
        risk_flags,
        fund,
        ret_1m,
        ret_3m,
        drawdown,
        volatility,
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
        "confidence_score": confidence_score,
        "confidence_level": confidence_level,
        "buy_window_signal": buy_window_signal,
        "buy_window_reason": buy_window_reason,
        "risk_flags": sorted(set(risk_flags)),
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
    nav_stats: dict | None = None,
) -> dict:
    if strategy not in SCORE_STRATEGIES:
        raise ValueError(f"Unknown score strategy: {strategy}")
    base = score_indicator(indicator, fund, nav_stats)
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
    buy_window_signal, buy_window_reason = _buy_window_signal(
        total_score,
        int(base["confidence_score"]),
        list(base["risk_flags"]),
        fund,
        _value(indicator.return_1m),
        _value(indicator.return_3m),
        _value(indicator.max_drawdown_1y),
        _value(indicator.volatility_1y),
    )
    return {
        **base,
        "strategy": strategy,
        "strategy_name": strategy_name,
        "strategy_scenario": SCORE_STRATEGIES[strategy]["scenario"],
        "total_score": total_score,
        "rating": _rating(total_score),
        "buy_window_signal": buy_window_signal,
        "buy_window_reason": buy_window_reason,
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


def _nav_stats(db: Session, fund_code: str) -> dict:
    rows = db.execute(
        select(func.min(FundNav.nav_date), func.max(FundNav.nav_date)).where(FundNav.fund_code == fund_code.zfill(6))
    ).one()
    first_nav_date, latest_nav_date = rows
    history_days = (latest_nav_date - first_nav_date).days if first_nav_date and latest_nav_date else None
    return {"history_days": history_days, "latest_nav_date": latest_nav_date}


def _score_to_dict(score: FundScore, fund_name: str | None = None) -> dict:
    return {
        "fund_code": score.fund_code,
        "fund_name": fund_name,
        "score_date": score.score_date,
        "total_score": float(score.total_score) if score.total_score is not None else None,
        "return_score": float(score.return_score) if score.return_score is not None else None,
        "drawdown_score": float(score.drawdown_score) if score.drawdown_score is not None else None,
        "volatility_score": float(score.volatility_score) if score.volatility_score is not None else None,
        "stability_score": float(score.stability_score) if score.stability_score is not None else None,
        "size_score": float(score.size_score) if score.size_score is not None else None,
        "trade_status_score": float(score.trade_status_score) if score.trade_status_score is not None else None,
        "rating": score.rating,
        "reason": score.reason,
    }


def score_payload(db: Session, fund_code: str) -> dict | None:
    fund_code = fund_code.zfill(6)
    score = latest_score(db, fund_code)
    if not score:
        return None
    fund = db.scalar(select(FundInfo).where(FundInfo.fund_code == fund_code))
    indicator = latest_indicator(db, fund_code)
    payload = _score_to_dict(score, fund.fund_name if fund else None)
    if indicator:
        fresh = score_indicator(indicator, fund, _nav_stats(db, fund_code))
        payload.update(
            {
                "confidence_score": fresh["confidence_score"],
                "confidence_level": fresh["confidence_level"],
                "buy_window_signal": fresh["buy_window_signal"],
                "buy_window_reason": fresh["buy_window_reason"],
                "risk_flags": fresh["risk_flags"],
                "reason": fresh["reason"],
            }
        )
    else:
        payload.update(
            {
                "confidence_score": 0,
                "confidence_level": "low",
                "buy_window_signal": "cautious",
                "buy_window_reason": "缺少最新指标，无法形成可靠窗口信号",
                "risk_flags": ["indicator_missing"],
            }
        )
    return _apply_context(payload, _market_signal(db), _portfolio_fit(db, fund_code))


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
        rows = []
        for item in top_scores(db, limit):
            payload = score_payload(db, item.fund_code) or _score_to_dict(item)
            payload.update(
                {
                    "strategy": "default",
                    "strategy_name": SCORE_STRATEGIES["default"]["name"],
                    "strategy_scenario": SCORE_STRATEGIES["default"]["scenario"],
                }
            )
            rows.append(payload)
        return rows

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
        item = score_indicator_with_strategy(indicator, fund, strategy, _nav_stats(db, indicator.fund_code))
        item = _apply_context(item, _market_signal(db), _portfolio_fit(db, indicator.fund_code))
        scored.append(
            {
                "fund_code": indicator.fund_code,
                "fund_name": fund.fund_name if fund else None,
                "score_date": indicator.calc_date,
                **item,
            }
        )
    return sorted(scored, key=lambda item: item["total_score"] or 0, reverse=True)[:limit]
