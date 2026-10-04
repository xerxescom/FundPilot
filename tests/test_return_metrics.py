from datetime import date
from decimal import Decimal

from app.services import return_metrics


def test_link_returns_geometric_and_skips_missing_segments():
    assert return_metrics.link_returns([Decimal("0.1"), Decimal("0.1")]) == Decimal("0.21")
    assert return_metrics.link_returns([Decimal("0.1"), None]) == Decimal("0.1")
    assert return_metrics.link_returns([None, None]) is None
    assert return_metrics.link_returns([]) is None
    assert return_metrics.link_returns([Decimal("-1")]) is None  # (1+r)<=0 无法连乘


def test_period_return_uses_end_of_period_flow_convention():
    # 期末口径：期间流入不计当段收益
    assert return_metrics.period_return(
        Decimal("1000"), Decimal("1600"), Decimal("500")
    ) == Decimal("0.1")
    assert return_metrics.period_return(
        Decimal("1000"), Decimal("1100"), Decimal("0")
    ) == Decimal("0.1")
    assert return_metrics.period_return(Decimal("0"), Decimal("100"), Decimal("100")) is None


def test_annualize_known_values_and_guards():
    assert return_metrics.annualize(Decimal("0.1"), 365) == Decimal("0.1")
    assert return_metrics.annualize(Decimal("0.21"), 730) == Decimal("0.1")
    assert return_metrics.annualize(Decimal("-0.5"), 365) == Decimal("-0.5")
    assert return_metrics.annualize(None, 365) is None
    assert return_metrics.annualize(Decimal("0.1"), 0) is None


def test_xirr_known_cases():
    rate, status = return_metrics.xirr(
        [(date(2025, 1, 1), Decimal("-1000")), (date(2026, 1, 1), Decimal("1100"))]
    )
    assert status == "ok"
    assert rate == Decimal("0.1")

    rate, status = return_metrics.xirr(
        [(date(2025, 1, 1), Decimal("-1000")), (date(2027, 1, 1), Decimal("1210"))]
    )
    assert status == "ok"
    assert rate == Decimal("0.1")  # 730 天正好两年

    rate, status = return_metrics.xirr(
        [(date(2025, 1, 1), Decimal("-1000")), (date(2026, 1, 1), Decimal("900"))]
    )
    assert status == "ok"
    assert rate == Decimal("-0.1")


def test_xirr_intermediate_flows_reproduce_zero_npv():
    flows = [
        (date(2025, 1, 1), Decimal("-1000")),
        (date(2025, 7, 1), Decimal("-500")),
        (date(2026, 1, 1), Decimal("1700")),
    ]
    rate, status = return_metrics.xirr(flows)
    assert status == "ok"

    start = date(2025, 1, 1)
    npv = sum(
        float(amount) / (1 + float(rate)) ** ((day - start).days / 365.0)
        for day, amount in flows
    )
    assert abs(npv) < 0.01


def test_xirr_status_paths():
    assert return_metrics.xirr([])[1] == "insufficient_flows"
    assert return_metrics.xirr([(date(2025, 1, 1), Decimal("100"))])[1] == "insufficient_flows"
    same_day = [(date(2025, 1, 1), Decimal("-1000")), (date(2025, 1, 1), Decimal("1000"))]
    assert return_metrics.xirr(same_day)[1] == "zero_days"
    all_out = [(date(2025, 1, 1), Decimal("-1000")), (date(2025, 6, 1), Decimal("-500"))]
    assert return_metrics.xirr(all_out)[1] == "all_same_sign"
    # 一天内 +10% 无法年化出可解释的利率：应报告无解而不是天文数字
    short = [(date(2025, 1, 1), Decimal("-1000")), (date(2025, 1, 2), Decimal("1100"))]
    rate, status = return_metrics.xirr(short)
    assert rate is None or abs(rate) < Decimal("100")
    assert status in {"ok", "no_solution"}
    assert return_metrics.XIRR_STATUS_LABELS["short_window"]
