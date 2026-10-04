"""基准对比：账户 TWR 指数 vs 指数收盘，按共同日期对齐（不做前向填充）。

指标口径：
- 累计收益：对齐区间首日归一到 1.0 后的区间收益；
- 年化收益按自然日折算（与 return_metrics.annualize 一致）；
- 波动率按 252 个交易日折算（与 indicator_service 的风控口径一致）；
- Beta = cov / var，Alpha = 账户年化 − β × 基准年化（无风险利率按 0，需在 notes 中说明）。
"""

from __future__ import annotations

import math
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import MarketIndexDaily
from app.services import return_metrics

MIN_OBSERVATIONS = 20  # 少于 20 个日收益不做对比，统计量噪声过大
TRADING_DAYS_PER_YEAR = 252
METRIC_KEYS = (
    "account_cumulative",
    "benchmark_cumulative",
    "excess_return",
    "account_annualized",
    "benchmark_annualized",
    "account_volatility",
    "benchmark_volatility",
    "account_max_drawdown",
    "benchmark_max_drawdown",
    "beta",
    "alpha",
    "correlation",
)


def index_series(db: Session, index_code: str, start: date, end: date) -> list[tuple[date, Decimal]]:
    rows = db.scalars(
        select(MarketIndexDaily)
        .where(
            MarketIndexDaily.index_code == index_code,
            MarketIndexDaily.close.is_not(None),
            MarketIndexDaily.trade_date >= start,
            MarketIndexDaily.trade_date <= end,
        )
        .order_by(MarketIndexDaily.trade_date.asc())
    )
    return [(item.trade_date, Decimal(item.close)) for item in rows if Decimal(item.close) > 0]


def resolve_index_name(db: Session, index_code: str) -> str:
    name = db.scalar(
        select(MarketIndexDaily.index_name)
        .where(MarketIndexDaily.index_code == index_code)
        .order_by(MarketIndexDaily.trade_date.desc())
        .limit(1)
    )
    if name:
        return name
    from app.services.market_service import DEFAULT_MARKET_INDEXES

    return DEFAULT_MARKET_INDEXES.get(index_code, index_code)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values)


def _stdev(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = _mean(values)
    return math.sqrt(sum((value - mean) ** 2 for value in values) / (len(values) - 1))


def _quant(value: float | Decimal | None, places: str = "0.000001") -> Decimal | None:
    if value is None:
        return None
    return Decimal(str(value)).quantize(Decimal(places))


def _max_drawdown(series: list[Decimal]) -> Decimal | None:
    peak: Decimal | None = None
    worst = Decimal("0")
    for value in series:
        peak = value if peak is None or value > peak else peak
        if peak > 0:
            worst = max(worst, (peak - value) / peak)
    return worst


def compare(
    performance: dict,
    index_rows: list[tuple[date, Decimal]],
    *,
    index_code: str,
    index_name: str,
    min_observations: int = MIN_OBSERVATIONS,
) -> dict:
    """纯函数：账户曲线（含 returns.twr_index） vs 指数收盘序列。"""
    returns = performance.get("returns") or {}
    twr_points = [item for item in (returns.get("twr_index") or []) if item.get("index") is not None]
    account_points = len(returns.get("twr_index") or [])
    empty_metrics = {key: None for key in METRIC_KEYS}

    if not index_rows:
        return {
            "index_code": index_code,
            "index_name": index_name,
            "status": "no_index_data",
            "coverage": {
                "start_date": None,
                "end_date": None,
                "aligned_days": 0,
                "account_points": account_points,
                "index_points": 0,
                "missing_index_days": account_points,
                "index_latest_date": None,
            },
            "metrics": empty_metrics,
            "series": [],
            "notes": [f"指数「{index_name}」（{index_code}）暂无历史行情，请先到市场概览页同步"],
        }

    index_map = {day: close for day, close in index_rows}
    aligned = [
        (item["point_date"], Decimal(item["index"]), index_map[item["point_date"]])
        for item in twr_points
        if item["point_date"] in index_map
    ]
    coverage = {
        "start_date": aligned[0][0] if aligned else None,
        "end_date": aligned[-1][0] if aligned else None,
        "aligned_days": len(aligned),
        "account_points": account_points,
        "index_points": len(index_rows),
        "missing_index_days": account_points - len(aligned),
        "index_latest_date": index_rows[-1][0],
    }
    if len(aligned) - 1 < min_observations:
        return {
            "index_code": index_code,
            "index_name": index_name,
            "status": "insufficient_overlap",
            "coverage": coverage,
            "metrics": empty_metrics,
            "series": [],
            "notes": [
                f"账户曲线与指数的共同交易日不足（{len(aligned)} 天，至少需要 {min_observations + 1} 天）"
            ],
        }

    notes: list[str] = []
    if coverage["missing_index_days"]:
        notes.append(f"账户曲线有 {coverage['missing_index_days']} 天在指数中没有行情，已从对比中剔除")

    account_series = [item[1] for item in aligned]
    benchmark_series = [item[2] for item in aligned]
    account_rebased = [value / account_series[0] for value in account_series]
    benchmark_rebased = [value / benchmark_series[0] for value in benchmark_series]

    account_daily = [
        float(account_series[index] / account_series[index - 1] - 1)
        for index in range(1, len(account_series))
    ]
    benchmark_daily = [
        float(benchmark_series[index] / benchmark_series[index - 1] - 1)
        for index in range(1, len(benchmark_series))
    ]

    days = (aligned[-1][0] - aligned[0][0]).days
    account_cumulative = account_rebased[-1] - 1
    benchmark_cumulative = benchmark_rebased[-1] - 1
    account_annualized = return_metrics.annualize(account_cumulative, days)
    benchmark_annualized = return_metrics.annualize(benchmark_cumulative, days)

    mean_account, mean_benchmark = _mean(account_daily), _mean(benchmark_daily)
    std_account, std_benchmark = _stdev(account_daily), _stdev(benchmark_daily)
    covariance = (
        sum(
            (account - mean_account) * (benchmark - mean_benchmark)
            for account, benchmark in zip(account_daily, benchmark_daily)
        )
        / (len(account_daily) - 1)
    )
    variance_benchmark = std_benchmark**2 if std_benchmark else None
    beta = covariance / variance_benchmark if variance_benchmark else None
    alpha = None
    if beta is not None and account_annualized is not None and benchmark_annualized is not None:
        alpha = _quant(float(account_annualized) - beta * float(benchmark_annualized))
    correlation = (
        covariance / (std_account * std_benchmark) if std_account and std_benchmark else None
    )
    notes.append("年化收益按自然日折算，波动率按 252 个交易日折算；Alpha 按无风险利率 0 计算")

    return {
        "index_code": index_code,
        "index_name": index_name,
        "status": "ok",
        "coverage": coverage,
        "metrics": {
            "account_cumulative": _quant(account_cumulative),
            "benchmark_cumulative": _quant(benchmark_cumulative),
            "excess_return": _quant(account_cumulative - benchmark_cumulative),
            "account_annualized": account_annualized,
            "benchmark_annualized": benchmark_annualized,
            "account_volatility": _quant(std_account * math.sqrt(TRADING_DAYS_PER_YEAR) if std_account else None),
            "benchmark_volatility": _quant(
                std_benchmark * math.sqrt(TRADING_DAYS_PER_YEAR) if std_benchmark else None
            ),
            "account_max_drawdown": _quant(_max_drawdown(account_rebased)),
            "benchmark_max_drawdown": _quant(_max_drawdown(benchmark_rebased)),
            "beta": _quant(beta, "0.0001"),
            "alpha": alpha,
            "correlation": _quant(correlation, "0.0001"),
        },
        "series": [
            {
                "point_date": day,
                "account_index": _quant(account_value),
                "benchmark_index": _quant(benchmark_value),
            }
            for (day, _, _), account_value, benchmark_value in zip(
                aligned, account_rebased, benchmark_rebased
            )
        ],
        "notes": notes,
    }


def compare_performance(db: Session, performance: dict, *, index_code: str) -> dict:
    """从库里取指数行情并与账户曲线对比。"""
    returns = performance.get("returns") or {}
    dates = [
        item["point_date"] for item in (returns.get("twr_index") or []) if item.get("index") is not None
    ]
    rows = index_series(db, index_code, min(dates), max(dates)) if dates else []
    return compare(
        performance,
        rows,
        index_code=index_code,
        index_name=resolve_index_name(db, index_code),
    )
