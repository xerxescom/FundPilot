"""收益口径的纯函数：TWR 分段连乘、年化与 XIRR（牛顿迭代 + 二分兜底）。

约定：
- 单段收益按**期末口径**：`(期末估值 − 当日外部流入) / 期初估值 − 1`，
  即当日投入的资金不参与当段收益；该口径需要在返回的 notes 中向用户说明。
- XIRR 现金流取投入方视角：投入为负（含期初市值），收回与期末市值为正。
- 金额全程 Decimal；仅 XIRR/年化的分数次幂用 float（1e-12 级误差，远低于输出精度）。
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

MIN_XIRR_FLOWS = 2
MIN_ANNUALIZE_DAYS = 30  # 短于此区间的年化收益率（含 XIRR）噪声过大，不对外输出
MAX_XIRR_RATE = 10.0
_RATE_QUANT = Decimal("0.000001")
_XIRR_TOLERANCE = 1e-9
_XIRR_MAX_ITERATIONS = 100
_XIRR_BISECTION_STEPS = 200

XIRR_STATUS_LABELS = {
    "ok": "计算成功",
    "insufficient_flows": "现金流不足（少于两笔）",
    "all_same_sign": "现金流方向单一，无法求解",
    "no_solution": "在合理区间内无解",
    "zero_days": "起止日期相同，无法年化",
    "short_window": f"区间不足 {MIN_ANNUALIZE_DAYS} 天，年化收益不具参考意义",
}


def link_returns(sub_returns: list[Decimal | None]) -> Decimal | None:
    """几何连乘；None 段（无法计算的区间）跳过；任一段 (1+r)<=0 时返回 None。"""
    total = Decimal("1")
    seen = False
    for value in sub_returns:
        if value is None:
            continue
        factor = Decimal("1") + value
        if factor <= 0:
            return None
        total *= factor
        seen = True
    return total - Decimal("1") if seen else None


def period_return(value_prev: Decimal, value_now: Decimal, flow: Decimal) -> Decimal | None:
    """单段收益（期末口径）。期初估值为 0 时无法定义，返回 None。"""
    if value_prev is None or value_prev <= 0:
        return None
    return (value_now - flow) / value_prev - Decimal("1")


def annualize(total_return: Decimal | None, days: int) -> Decimal | None:
    """按自然日年化：``(1+r)^(365/days) - 1``。"""
    if total_return is None or days <= 0:
        return None
    base = float(Decimal("1") + total_return)
    if base <= 0:
        return None
    return Decimal(str(base ** (365.0 / days) - 1.0)).quantize(_RATE_QUANT)


def _npv(amounts: list[float], day_offsets: list[int], rate: float) -> float:
    return sum(
        amount / (1.0 + rate) ** (days / 365.0)
        for amount, days in zip(amounts, day_offsets)
    )


def _npv_derivative(amounts: list[float], day_offsets: list[int], rate: float) -> float:
    return sum(
        -(days / 365.0) * amount / (1.0 + rate) ** (days / 365.0 + 1.0)
        for amount, days in zip(amounts, day_offsets)
    )


def _quantize_rate(rate: float) -> Decimal:
    return Decimal(str(round(rate, 6))).quantize(_RATE_QUANT)


def xirr(flows: list[tuple[date, Decimal]], *, guess: float = 0.1) -> tuple[Decimal | None, str]:
    """解 ``NPV(r) = Σ CF_i / (1+r)^(d_i/365) = 0``，返回 (年化收益率, 状态)。"""
    ordered = sorted(flows, key=lambda item: item[0])
    nonzero = [item for item in ordered if Decimal(item[1]) != 0]
    if len(nonzero) < MIN_XIRR_FLOWS:
        return None, "insufficient_flows"
    amounts = [float(item[1]) for item in nonzero]
    if all(amount > 0 for amount in amounts) or all(amount < 0 for amount in amounts):
        return None, "all_same_sign"

    start = ordered[0][0]
    day_offsets = [(item[0] - start).days for item in nonzero]
    if day_offsets[-1] == 0:
        return None, "zero_days"

    rate = guess
    for _ in range(_XIRR_MAX_ITERATIONS):
        value = _npv(amounts, day_offsets, rate)
        if abs(value) < _XIRR_TOLERANCE:
            return _quantize_rate(rate), "ok"
        derivative = _npv_derivative(amounts, day_offsets, rate)
        if derivative == 0:
            break
        next_rate = rate - value / derivative
        if not (-0.9999 < next_rate < MAX_XIRR_RATE):
            break
        if abs(next_rate - rate) < 1e-12:
            return _quantize_rate(next_rate), "ok"
        rate = next_rate

    # 牛顿法未收敛：在 (-0.9999, MAX_XIRR_RATE) 上二分符号变化区间
    low, high = -0.9999, MAX_XIRR_RATE
    value_low = _npv(amounts, day_offsets, low)
    value_high = _npv(amounts, day_offsets, high)
    if value_low == 0:
        return _quantize_rate(low), "ok"
    if value_high == 0:
        return _quantize_rate(high), "ok"
    if value_low * value_high > 0:
        return None, "no_solution"
    for _ in range(_XIRR_BISECTION_STEPS):
        middle = (low + high) / 2
        value_middle = _npv(amounts, day_offsets, middle)
        if abs(value_middle) < _XIRR_TOLERANCE or (high - low) < 1e-12:
            return _quantize_rate(middle), "ok"
        if value_low * value_middle <= 0:
            high = middle
        else:
            low, value_low = middle, value_middle
    return _quantize_rate((low + high) / 2), "ok"
