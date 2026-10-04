from datetime import date, timedelta
from decimal import Decimal

from app.db.models import FundNav, MarketIndexDaily
from app.services import account_service, benchmark_service, portfolio_service

START = date(2026, 1, 1)


def _series(pair_count: int) -> tuple[list[Decimal], list[Decimal]]:
    """基准每日 ±1% 交替、账户波动恰为其两倍：beta=2、correlation=1 的解析样例。

    每轮循环产生两个日收益（+1% 与 −1%），pair_count=12 时得到 24 个日收益、25 个点。
    """
    account = [Decimal("1")]
    benchmark = [Decimal("1")]
    for _ in range(pair_count):
        benchmark.append(benchmark[-1] * Decimal("1.01"))
        account.append(account[-1] * Decimal("1.02"))
        benchmark.append(benchmark[-1] * Decimal("0.99"))
        account.append(account[-1] * Decimal("0.98"))
    return account, benchmark


def _performance(levels: list[Decimal]) -> dict:
    return {
        "returns": {
            "twr_index": [
                {"point_date": START + timedelta(days=index), "index": level}
                for index, level in enumerate(levels)
            ]
        }
    }


def _index_rows(levels: list[Decimal]) -> list[tuple[date, Decimal]]:
    return [(START + timedelta(days=index), level) for index, level in enumerate(levels)]


def test_compare_computes_documented_metrics():
    account, benchmark = _series(12)  # 24 个日收益、25 个对齐点
    result = benchmark_service.compare(
        _performance(account), _index_rows(benchmark), index_code="sh000300", index_name="沪深300"
    )

    assert result["status"] == "ok"
    assert result["coverage"]["aligned_days"] == 25
    metrics = result["metrics"]
    assert metrics["beta"] == Decimal("2.0000")
    assert metrics["correlation"] == Decimal("1.0000")
    assert metrics["account_cumulative"] == (account[-1] / account[0] - 1).quantize(
        Decimal("0.000001")
    )
    assert metrics["benchmark_cumulative"] == (benchmark[-1] / benchmark[0] - 1).quantize(
        Decimal("0.000001")
    )
    assert metrics["excess_return"] == metrics["account_cumulative"] - metrics["benchmark_cumulative"]
    # 最大回撤 = 历史峰值（首日 +2% 处）到之后最低点（序列末点）的跌幅
    assert metrics["account_max_drawdown"] == (
        Decimal("1") - account[-1] / max(account)
    ).quantize(Decimal("0.000001"))
    assert metrics["account_volatility"] > metrics["benchmark_volatility"]
    assert any("252" in note for note in result["notes"])
    assert len(result["series"]) == 25
    assert result["series"][0]["account_index"] == Decimal("1.000000")


def test_compare_without_index_rows_degrades_to_no_index_data():
    account, _ = _series(12)
    result = benchmark_service.compare(
        _performance(account), [], index_code="sh000300", index_name="沪深300"
    )

    assert result["status"] == "no_index_data"
    assert result["series"] == []
    assert all(value is None for value in result["metrics"].values())
    assert any("同步" in note for note in result["notes"])


def test_compare_requires_minimum_overlap():
    account, benchmark = _series(2)  # 只有 4 个日收益、5 个点
    result = benchmark_service.compare(
        _performance(account), _index_rows(benchmark), index_code="sh000300", index_name="沪深300"
    )

    assert result["status"] == "insufficient_overlap"
    assert result["coverage"]["aligned_days"] == 5
    assert result["metrics"]["beta"] is None
    assert any("共同交易日不足" in note for note in result["notes"])


def test_compare_excludes_days_missing_from_index():
    account, benchmark = _series(12)
    rows = [row for row in _index_rows(benchmark) if row[0] != START + timedelta(days=5)]
    result = benchmark_service.compare(
        _performance(account), rows, index_code="sh000300", index_name="沪深300"
    )

    assert result["status"] == "ok"
    assert result["coverage"]["aligned_days"] == 24
    assert result["coverage"]["missing_index_days"] == 1
    assert any("剔除" in note for note in result["notes"])


def test_compare_performance_reads_index_from_database(db_session):
    account, benchmark = _series(12)
    for day, close in _index_rows(benchmark):
        db_session.add(
            MarketIndexDaily(
                index_code="sh000300", index_name="沪深300", trade_date=day, close=close
            )
        )
    db_session.commit()

    result = benchmark_service.compare_performance(
        db_session, _performance(account), index_code="sh000300"
    )

    assert result["status"] == "ok"
    assert result["index_name"] == "沪深300"
    assert result["coverage"]["index_points"] == 25


def test_account_performance_benchmark_wiring(db_session):
    account_service.create_cash_event(
        db_session,
        {"event_date": START, "event_type": "opening_balance", "amount": Decimal("1000")},
    )
    portfolio_service.create_transaction(
        db_session,
        {
            "fund_code": "000021",
            "trade_date": START,
            "trade_type": "buy",
            "amount": Decimal("1000"),
            "nav": Decimal("1"),
        },
    )
    # 账户与基准使用同一组 4 位小数的价格序列（Numeric(20,4) 可精确表示）
    levels = [Decimal("1")]
    for step in range(24):
        factor = Decimal("1.01") if step % 2 == 0 else Decimal("0.99")
        levels.append((levels[-1] * factor).quantize(Decimal("0.0001")))
    for offset, level in enumerate(levels):
        day = START + timedelta(days=offset)
        db_session.add(FundNav(fund_code="000021", nav_date=day, unit_nav=level))
        db_session.add(
            MarketIndexDaily(
                index_code="sh000300", index_name="沪深300", trade_date=day, close=level
            )
        )
    db_session.commit()

    result = account_service.account_performance(
        db_session, end=START + timedelta(days=24), include_benchmark=True
    )

    assert result["coverage"]["points"] == 25
    benchmark = result["benchmark"]
    assert benchmark["status"] == "ok"
    assert benchmark["coverage"]["aligned_days"] == 25
    # 账户与基准同源（100% 持有该基金）：beta≈1、无超额
    assert benchmark["metrics"]["beta"] == Decimal("1.0000")
    assert benchmark["metrics"]["correlation"] == Decimal("1.0000")
    assert benchmark["metrics"]["excess_return"] == Decimal("0")

    # 汇总接口不带基准（避免 dashboard 等高频调用多算）
    summary = account_service.account_summary(db_session)
    assert "benchmark" not in account_service.account_performance(db_session)
    assert summary["returns"]["status"] == "ok"
