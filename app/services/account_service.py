"""账户口径：现金事件、现金余额（推导值）、账户汇总与账户资产曲线。

现金不落库：余额 = 现金事件 + 交易现金流（买/申购 −(金额+费用)，卖/赎回 +(金额−费用)，
期初/拆分/红利再投不动现金）。账户盈亏恒等式：
    累计盈亏 = 已实现盈亏 + 未实现盈亏 + 其他收益（分红/利息/费用/调整/红利再投）
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db.models import AssetPriceDaily, FundNav, PortfolioCashEvent, PortfolioPosition, PortfolioTransaction
from app.services import asset_service, benchmark_service, portfolio_service, return_metrics

CASH_EVENT_TYPES = {"deposit", "withdraw", "dividend", "interest", "fee", "adjustment", "opening_balance"}
CASH_EVENT_LABELS = {
    "deposit": "入金",
    "withdraw": "出金",
    "dividend": "现金分红",
    "interest": "利息",
    "fee": "费用",
    "adjustment": "调整",
    "opening_balance": "期初现金",
}
_POSITIVE_TYPES = {"deposit", "dividend", "interest", "opening_balance"}
_NEGATIVE_TYPES = {"withdraw", "fee"}
_CASH_OUT_TYPES = {"buy", "subscription"}
_OTHER_INCOME_TYPES = {"dividend", "interest", "fee", "adjustment"}

MAX_PERFORMANCE_DAYS = 1095  # 3 年，超出时截断并在 coverage 中说明
MAX_PERFORMANCE_POINTS = 1500
RECONCILIATION_TOLERANCE = Decimal("0.01")
RETURNS_BASIS = "twr_daily_linked + xirr_newton"


# ---------------------------------------------------------------- 现金事件


def normalize_cash_event(db: Session, data: dict) -> dict:
    """校验并规范化现金事件字段（带符号、资产归属、类型白名单），不落库。"""
    event_type = data.get("event_type")
    if event_type not in CASH_EVENT_TYPES:
        raise ValueError(f"event_type must be one of {sorted(CASH_EVENT_TYPES)}")
    amount = Decimal(data["amount"])
    if amount == 0:
        raise ValueError("金额不能为 0")
    if event_type in _POSITIVE_TYPES:
        amount = abs(amount)
    elif event_type in _NEGATIVE_TYPES:
        amount = -abs(amount)

    asset_type = data.get("asset_type") or None
    asset_code = data.get("asset_code") or None
    if asset_code and not asset_type:
        asset_type = "fund"
    if asset_type and not asset_code:
        raise ValueError("填写资产归属时必须同时提供 asset_type 与 asset_code")
    if asset_code and asset_type:
        asset_code = asset_service.normalize_asset_code(asset_code, asset_type)

    return {
        "event_date": data["event_date"],
        "event_type": event_type,
        "amount": portfolio_service._quantize(amount, "0.0001"),
        "asset_type": asset_type,
        "asset_code": asset_code,
        "note": data.get("note"),
        "source": data.get("source") or "manual",
        "external_ref": data.get("external_ref"),
        "import_batch_id": data.get("import_batch_id"),
    }


def create_cash_event(db: Session, data: dict) -> PortfolioCashEvent:
    values = normalize_cash_event(db, data)
    if values["event_type"] == "opening_balance":
        existing = db.scalar(
            select(func.count())
            .select_from(PortfolioCashEvent)
            .where(PortfolioCashEvent.event_type == "opening_balance")
        )
        if existing:
            raise ValueError("期初现金只能设置一次；如需修改请先删除原记录")
    event = PortfolioCashEvent(**values)
    db.add(event)
    db.commit()
    db.refresh(event)
    return event


def list_cash_events(
    db: Session, start: date | None = None, end: date | None = None, limit: int = 500
) -> list[PortfolioCashEvent]:
    stmt = select(PortfolioCashEvent).order_by(PortfolioCashEvent.event_date.desc(), PortfolioCashEvent.id.desc())
    if start:
        stmt = stmt.where(PortfolioCashEvent.event_date >= start)
    if end:
        stmt = stmt.where(PortfolioCashEvent.event_date <= end)
    return list(db.scalars(stmt.limit(limit)))


def delete_cash_event(db: Session, event_id: int) -> bool:
    event = db.get(PortfolioCashEvent, event_id)
    if event is None:
        return False
    db.delete(event)
    db.commit()
    return True


# ---------------------------------------------------------------- 现金与账户口径


def _trade_cash_delta(transaction: PortfolioTransaction) -> Decimal:
    amount = Decimal(transaction.amount)
    fee = Decimal(transaction.fee or 0)
    if transaction.trade_type in _CASH_OUT_TYPES:
        return -(amount + fee)
    if transaction.trade_type in portfolio_service.SELL_TYPES:
        return amount - fee
    return Decimal("0")  # opening / split / dividend_reinvest 不动现金


def _all_transactions(db: Session, as_of: date | None = None) -> list[PortfolioTransaction]:
    stmt = select(PortfolioTransaction).order_by(
        PortfolioTransaction.trade_date.asc(), PortfolioTransaction.id.asc()
    )
    if as_of:
        stmt = stmt.where(PortfolioTransaction.trade_date <= as_of)
    return list(db.scalars(stmt))


def _all_cash_events(db: Session, as_of: date | None = None) -> list[PortfolioCashEvent]:
    stmt = select(PortfolioCashEvent).order_by(
        PortfolioCashEvent.event_date.asc(), PortfolioCashEvent.id.asc()
    )
    if as_of:
        stmt = stmt.where(PortfolioCashEvent.event_date <= as_of)
    return list(db.scalars(stmt))


def cash_balance(db: Session, as_of: date | None = None) -> Decimal:
    events = _all_cash_events(db, as_of)
    total = sum((Decimal(item.amount) for item in events), Decimal("0"))
    for transaction in _all_transactions(db, as_of):
        total += _trade_cash_delta(transaction)
    return portfolio_service._quantize(total, "0.0001")


def _materialized_opening_cost(db: Session, as_of: date | None = None) -> Decimal:
    stmt = select(func.coalesce(func.sum(PortfolioTransaction.amount), 0)).where(
        PortfolioTransaction.trade_type == "opening"
    )
    if as_of:
        stmt = stmt.where(PortfolioTransaction.trade_date <= as_of)
    return Decimal(db.scalar(stmt) or 0)


def _pending_opening_cost(db: Session, as_of: date | None = None) -> Decimal:
    """尚未物化为期初事件的手工/截图持仓成本（只读推导，不写库）。"""
    total = Decimal("0")
    for position in portfolio_service.list_positions(db):
        asset_type, asset_code = portfolio_service._identity(position)
        has_transactions = db.scalar(
            select(PortfolioTransaction.id)
            .where(*portfolio_service._transaction_criteria(asset_type, asset_code))
            .limit(1)
        )
        if has_transactions:
            continue
        values = portfolio_service.opening_values(position)
        if values is None:
            continue
        if as_of and values["trade_date"] > as_of:
            continue
        total += Decimal(values["amount"])
    return total


def _cash_event_totals(db: Session) -> dict[str, Decimal]:
    totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for event in _all_cash_events(db):
        totals[event.event_type] += Decimal(event.amount)
    return totals


def account_summary(db: Session) -> dict:
    """当前账户口径汇总（历史曲线见 account_performance）。"""
    overview = portfolio_service.portfolio_overview(db)
    cash = cash_balance(db)
    totals = _cash_event_totals(db)

    opening_balance = totals.get("opening_balance", Decimal("0"))
    deposits_total = totals.get("deposit", Decimal("0"))
    withdrawals_total = -totals.get("withdraw", Decimal("0"))
    initial_investment = (
        _materialized_opening_cost(db) + _pending_opening_cost(db) + opening_balance
    )
    net_invested = initial_investment + deposits_total - withdrawals_total

    market_value = overview["total_value"]
    known_market_value = overview["known_value"]
    total_assets = market_value + cash if market_value is not None else None
    known_total_assets = known_market_value + cash

    realized_total = Decimal(
        db.scalar(
            select(func.coalesce(func.sum(PortfolioTransaction.realized_pnl), 0))
        )
        or 0
    )
    reinvest_total = Decimal(
        db.scalar(
            select(func.coalesce(func.sum(PortfolioTransaction.amount), 0)).where(
                PortfolioTransaction.trade_type == "dividend_reinvest"
            )
        )
        or 0
    )
    other_income = (
        sum((totals.get(kind, Decimal("0")) for kind in _OTHER_INCOME_TYPES), Decimal("0")) + reinvest_total
    )

    unrealized_total: Decimal | None = None
    if overview["is_complete"] and not overview["missing_cost_assets"]:
        unrealized_total = sum(
            (summary["profit_amount"] for summary in overview["positions"]), Decimal("0")
        )

    cumulative_pnl = total_assets - net_invested if total_assets is not None else None
    return_rate = (
        cumulative_pnl / net_invested
        if cumulative_pnl is not None and net_invested > 0
        else None
    )
    reconciliation = None
    if cumulative_pnl is not None and unrealized_total is not None:
        reconciliation = cumulative_pnl - (realized_total + unrealized_total + other_income)

    notes: list[str] = []
    if unrealized_total is None:
        notes.append("持仓估值不完整，未实现盈亏与恒等式核对暂不可用")
    if return_rate is not None:
        notes.append("收益率按累计盈亏/净投入计算，未剔除出入金时点影响；时间加权/资金加权收益见 returns")
    if overview["missing_price_assets"]:
        notes.append(f"{len(overview['missing_price_assets'])} 个持仓缺少行情，账户总资产按已知部分展示")
    if overview["missing_cost_assets"]:
        notes.append("存在缺少成本信息的持仓，未实现盈亏暂不可用")

    return {
        "as_of": date.today(),
        "valuation_status": overview["valuation_status"],
        "is_complete": overview["is_complete"] and unrealized_total is not None,
        "cash_balance": cash,
        "market_value": market_value,
        "known_market_value": known_market_value,
        "total_assets": total_assets,
        "known_total_assets": known_total_assets,
        "initial_investment": initial_investment,
        "opening_balance": opening_balance,
        "deposits_total": deposits_total,
        "withdrawals_total": withdrawals_total,
        "net_invested": net_invested,
        "cumulative_pnl": cumulative_pnl,
        "return_rate": return_rate,
        "realized_pnl_total": realized_total,
        "unrealized_pnl_total": unrealized_total,
        "other_income_total": portfolio_service._quantize(other_income, "0.0001"),
        "reconciliation_difference": reconciliation,
        "missing_price_assets": overview["missing_price_assets"],
        "notes": notes,
        "returns": account_returns(db, include_index=False),
    }


# ---------------------------------------------------------------- 账户收益（TWR / XIRR）


def _returns_quality(is_complete: bool, coverage: dict) -> dict:
    return {
        "is_complete": bool(is_complete),
        "cost_fallback_days": coverage.get("cost_fallback_days", 0),
        "missing_price_assets": coverage.get("missing_price_assets", []),
    }


def _returns_block(
    points: list[dict], *, is_complete: bool, coverage: dict, notes: list[str]
) -> dict:
    """从账户曲线推导 TWR（逐段连乘）与 XIRR（外部现金流取净投入的逐点变化）。

    单段收益按期末口径：``(期末估值 − 当日外部流入) / 期初估值 − 1``。
    净投入 = 期初投入 + 入金 − 出金，因此买卖/分红/利息/费用/调整都是内部收益，
    不会被误当作现金流（与账户盈亏恒等式同口径）。
    """
    block_notes = list(notes)
    quality = _returns_quality(is_complete, coverage)
    if len(points) < 2:
        block_notes.append(
            "账户曲线点数不足，无法计算 TWR/XIRR" if points else "账户暂无任何事件，无法计算 TWR/XIRR"
        )
        return {
            "status": "no_data",
            "twr": None,
            "twr_annualized": None,
            "xirr": None,
            "xirr_status": "insufficient_flows",
            "twr_index": [],
            "start_date": points[0]["point_date"] if points else None,
            "end_date": points[-1]["point_date"] if points else None,
            "days": 0,
            "flow_count": 0,
            "flow_total": Decimal("0"),
            "quality": quality,
            "notes": block_notes,
            "basis": RETURNS_BASIS,
        }

    start_date = points[0]["point_date"]
    end_date = points[-1]["point_date"]
    days = (end_date - start_date).days
    start_value = Decimal(points[0]["total_assets"])
    xirr_flows: list[tuple[date, Decimal]] = []
    if start_value > 0:
        xirr_flows.append((start_date, -start_value))

    sub_returns: list[Decimal | None] = []
    index_points: list[dict] = [{"point_date": start_date, "index": Decimal("1")}]
    index = Decimal("1")
    skipped_segments = 0
    truncated = False
    flow_count = 0
    flow_total = Decimal("0")

    for position in range(1, len(points)):
        previous_point = points[position - 1]
        point = points[position]
        flow = Decimal(point["net_invested"]) - Decimal(previous_point["net_invested"])
        if flow != 0:
            flow_count += 1
            flow_total += flow
            xirr_flows.append((point["point_date"], -flow))
        segment = return_metrics.period_return(
            Decimal(previous_point["total_assets"]), Decimal(point["total_assets"]), flow
        )
        if segment is None:
            skipped_segments += 1
            index_points.append({"point_date": point["point_date"], "index": None})
            continue
        factor = Decimal("1") + segment
        if truncated or factor <= 0:
            truncated = True
            index_points.append({"point_date": point["point_date"], "index": None})
            continue
        sub_returns.append(segment)
        index *= factor
        index_points.append({"point_date": point["point_date"], "index": index})

    if skipped_segments:
        block_notes.append(
            f"有 {skipped_segments} 段区间期初估值为 0（资金尚未投入），TWR 已跳过这些区间"
        )
    if truncated:
        block_notes.append("出现过非正收益区间，TWR 已在该处停止连乘")
    if quality["cost_fallback_days"]:
        block_notes.append("存在按成本估值的日期，TWR/XIRR 与实际市值口径存在偏差")
    if quality["missing_price_assets"]:
        block_notes.append(
            f"{len(quality['missing_price_assets'])} 个持仓缺少行情，收益指标按成本口径计算"
        )

    twr = return_metrics.link_returns(sub_returns)
    if days >= return_metrics.MIN_ANNUALIZE_DAYS:
        xirr_flows.append((end_date, Decimal(points[-1]["total_assets"])))
        xirr_value, xirr_status = return_metrics.xirr(xirr_flows)
        twr_annualized = return_metrics.annualize(twr, days)
    else:
        xirr_value, xirr_status = None, "short_window"
        twr_annualized = None
    if xirr_status != "ok":
        label = return_metrics.XIRR_STATUS_LABELS.get(xirr_status, xirr_status)
        block_notes.append(f"XIRR 与年化收益未计算：{label}")

    return {
        "status": "ok",
        "twr": twr,
        "twr_annualized": twr_annualized,
        "xirr": xirr_value,
        "xirr_status": xirr_status,
        "twr_index": index_points,
        "start_date": start_date,
        "end_date": end_date,
        "days": days,
        "flow_count": flow_count,
        "flow_total": portfolio_service._quantize(flow_total, "0.0001"),
        "quality": quality,
        "notes": block_notes,
        "basis": RETURNS_BASIS,
    }


def account_returns(
    db: Session,
    *,
    start: date | None = None,
    end: date | None = None,
    performance: dict | None = None,
    include_index: bool = True,
) -> dict:
    """账户收益指标（TWR/XIRR）；不传 performance 时自行回放账户曲线。"""
    source = performance if performance is not None else account_performance(db, start=start, end=end)
    returns = dict(source.get("returns") or {})
    if not include_index:
        returns.pop("twr_index", None)
    return returns


# ---------------------------------------------------------------- 账户曲线


def _asset_key(asset_type: str, asset_code: str) -> tuple[str, str]:
    return (asset_type or "fund", asset_code)


def _price_series(db: Session, asset_type: str, asset_code: str, until: date) -> list[tuple[date, Decimal]]:
    if asset_type == "fund":
        rows = db.scalars(
            select(FundNav)
            .where(FundNav.fund_code == asset_code, FundNav.unit_nav.is_not(None), FundNav.nav_date <= until)
            .order_by(FundNav.nav_date.asc())
        )
        return [(item.nav_date, Decimal(item.unit_nav)) for item in rows]
    rows = db.scalars(
        select(AssetPriceDaily)
        .where(
            AssetPriceDaily.asset_code == asset_code,
            AssetPriceDaily.close.is_not(None),
            AssetPriceDaily.price_date <= until,
        )
        .order_by(AssetPriceDaily.price_date.asc())
    )
    return [(item.price_date, Decimal(item.close)) for item in rows]


def _first_event_date(db: Session) -> date | None:
    candidates: list[date] = []
    first_tx = db.scalar(select(func.min(PortfolioTransaction.trade_date)))
    if first_tx:
        candidates.append(first_tx)
    first_cash = db.scalar(select(func.min(PortfolioCashEvent.event_date)))
    if first_cash:
        candidates.append(first_cash)
    for position in portfolio_service.list_positions(db):
        values = portfolio_service.opening_values(position)
        if values and not _position_has_transactions(db, position):
            candidates.append(values["trade_date"])
    return min(candidates) if candidates else None


def _position_has_transactions(db: Session, position: PortfolioPosition) -> bool:
    asset_type, asset_code = portfolio_service._identity(position)
    return (
        db.scalar(
            select(PortfolioTransaction.id)
            .where(*portfolio_service._transaction_criteria(asset_type, asset_code))
            .limit(1)
        )
        is not None
    )


def _attach_benchmark(
    db: Session, result: dict, include_benchmark: bool, index_code: str | None
) -> dict:
    if include_benchmark:
        settings = get_settings()
        result["benchmark"] = benchmark_service.compare_performance(
            db, result, index_code=index_code or settings.benchmark_index_code
        )
    return result


def account_performance(
    db: Session,
    start: date | None = None,
    end: date | None = None,
    *,
    include_benchmark: bool = False,
    benchmark_index_code: str | None = None,
) -> dict:
    """账户资产曲线：现金 + 各持仓按最近收盘估值（尚无行情时用成本代替并标记不完整）。"""
    end = end or date.today()
    first_event = _first_event_date(db)
    notes: list[str] = []

    if start is None:
        start = first_event or end
    if first_event and start < first_event:
        start = first_event  # 曲线从可验证期初开始
        notes.append(f"起点已对齐到最早可验证日期 {first_event.isoformat()}")
    if (end - start).days > MAX_PERFORMANCE_DAYS:
        start = end - timedelta(days=MAX_PERFORMANCE_DAYS)
        notes.append(f"区间超过 {MAX_PERFORMANCE_DAYS} 天，已截断显示")

    transactions = _all_transactions(db, end)
    cash_events = _all_cash_events(db, end)
    if first_event is None:
        empty_coverage = {
            "start_date": None,
            "end_date": end.isoformat(),
            "points": 0,
            "included_assets": 0,
            "excluded_assets": [],
            "cost_fallback_days": 0,
            "missing_price_assets": [],
        }
        empty_notes = ["账户暂无任何事件，曲线为空"]
        return _attach_benchmark(
            db,
            {
                "points": [],
                "coverage": empty_coverage,
                "is_complete": True,
                "basis": "account_balance_replay",
                "label": "账户资产重放（现金 + 持仓市值）",
                "notes": empty_notes,
                "returns": _returns_block(
                    [], is_complete=True, coverage=empty_coverage, notes=empty_notes
                ),
            },
            include_benchmark,
            benchmark_index_code,
        )

    # 每个资产的份额/成本与价格序列
    shares: dict[tuple[str, str], Decimal] = defaultdict(lambda: Decimal("0"))
    costs: dict[tuple[str, str], Decimal] = defaultdict(lambda: Decimal("0"))

    price_series: dict[tuple[str, str], list[tuple[date, Decimal]]] = {}
    price_pointer: dict[tuple[str, str], int] = {}
    latest_price: dict[tuple[str, str], Decimal | None] = {}
    missing_price_assets: list[str] = []

    def ensure_asset(key: tuple[str, str]) -> None:
        if key in price_series:
            return
        series = _price_series(db, key[0], key[1], end)
        price_series[key] = series
        price_pointer[key] = -1
        latest_price[key] = None
        if not series:
            missing_price_assets.append(key[1])

    def apply_event(trade_type: str, share: Decimal, amount: Decimal, fee: Decimal, key: tuple[str, str]) -> None:
        if trade_type in portfolio_service.SELL_TYPES:
            held = shares[key]
            average_cost = costs[key] / held if held else Decimal("0")
            costs[key] -= average_cost * share
            shares[key] -= share
        elif trade_type == "split":
            shares[key] += share
        elif trade_type == "dividend_reinvest":
            shares[key] += share
            costs[key] += amount
        else:  # buy / subscription / opening
            shares[key] += share
            costs[key] += amount + fee

    # 先登记全部相关资产并加载价格序列，日期集合才能包含区间内的行情日
    relevant_keys: set[tuple[str, str]] = {
        _asset_key(transaction.asset_type or "fund", transaction.asset_code or transaction.fund_code)
        for transaction in transactions
    }
    for position in portfolio_service.list_positions(db):
        if not _position_has_transactions(db, position) and portfolio_service.opening_values(position):
            relevant_keys.add(portfolio_service._identity(position))
    for key in sorted(relevant_keys):
        ensure_asset(key)

    # start 之前的事件折叠为初始状态
    cash = Decimal("0")
    basis = Decimal("0")  # 期初投入（持仓成本 + 期初现金）
    deposits = Decimal("0")
    withdrawals = Decimal("0")
    tx_index = 0
    cash_index = 0
    for transaction in transactions:
        if transaction.trade_date >= start:
            break
        key = _asset_key(transaction.asset_type or "fund", transaction.asset_code or transaction.fund_code)
        ensure_asset(key)
        apply_event(
            transaction.trade_type,
            Decimal(transaction.share),
            Decimal(transaction.amount),
            Decimal(transaction.fee or 0),
            key,
        )
        cash += _trade_cash_delta(transaction)
        if transaction.trade_type == "opening":
            basis += Decimal(transaction.amount)
        tx_index += 1
    for event in cash_events:
        if event.event_date >= start:
            break
        cash += Decimal(event.amount)
        if event.event_type == "opening_balance":
            basis += Decimal(event.amount)
        elif event.event_type == "deposit":
            deposits += Decimal(event.amount)
        elif event.event_type == "withdraw":
            withdrawals += -Decimal(event.amount)
        cash_index += 1
    # 尚未物化的手工/截图持仓：<= start 的折进初值（start 可能恰好等于它的日期），
    # > start 的作为有日期的期初事件参与回放。此前用 >= start 跳过会让这类持仓整体缺席，曲线记 0。
    pending_events: list[dict] = []
    for position in portfolio_service.list_positions(db):
        if _position_has_transactions(db, position):
            continue
        values = portfolio_service.opening_values(position)
        if values is None:
            continue
        key = portfolio_service._identity(position)
        ensure_asset(key)
        if values["trade_date"] <= start:
            shares[key] += Decimal(values["share"])
            costs[key] += Decimal(values["amount"])
            basis += Decimal(values["amount"])
        elif values["trade_date"] <= end:
            pending_events.append({"trade_date": values["trade_date"], "key": key, **values})
    pending_events.sort(key=lambda item: item["trade_date"])

    # 日期集合：行情日 ∪ 事件日（区间内）
    date_set: set[date] = set()
    for series in price_series.values():
        for day, _ in series:
            if start <= day <= end:
                date_set.add(day)
    for transaction in transactions[tx_index:]:
        if transaction.trade_date <= end:
            date_set.add(transaction.trade_date)
    for event in cash_events[cash_index:]:
        if event.event_date <= end:
            date_set.add(event.event_date)
    for item in pending_events:
        date_set.add(item["trade_date"])
    dates = sorted(date_set)
    if not dates:
        dates = [start]

    cost_fallback_days = 0
    points: list[dict] = []
    pending_index = 0
    for current in dates:
        while (
            pending_index < len(pending_events)
            and pending_events[pending_index]["trade_date"] <= current
        ):
            item = pending_events[pending_index]
            shares[item["key"]] += Decimal(item["share"])
            costs[item["key"]] += Decimal(item["amount"])
            basis += Decimal(item["amount"])
            pending_index += 1
        while tx_index < len(transactions) and transactions[tx_index].trade_date <= current:
            transaction = transactions[tx_index]
            key = _asset_key(transaction.asset_type or "fund", transaction.asset_code or transaction.fund_code)
            ensure_asset(key)
            apply_event(
                transaction.trade_type,
                Decimal(transaction.share),
                Decimal(transaction.amount),
                Decimal(transaction.fee or 0),
                key,
            )
            cash += _trade_cash_delta(transaction)
            if transaction.trade_type == "opening":
                basis += Decimal(transaction.amount)
            tx_index += 1
        while cash_index < len(cash_events) and cash_events[cash_index].event_date <= current:
            event = cash_events[cash_index]
            cash += Decimal(event.amount)
            if event.event_type == "opening_balance":
                basis += Decimal(event.amount)
            elif event.event_type == "deposit":
                deposits += Decimal(event.amount)
            elif event.event_type == "withdraw":
                withdrawals += -Decimal(event.amount)
            cash_index += 1

        market_value = Decimal("0")
        day_fallback = False
        for key, held in shares.items():
            if held <= 0:
                continue
            series = price_series.get(key, [])
            pointer = price_pointer[key]
            while pointer + 1 < len(series) and series[pointer + 1][0] <= current:
                pointer += 1
            price_pointer[key] = pointer
            if pointer >= 0:
                price = series[pointer][1]
            else:
                price = (costs[key] / held) if held else Decimal("0")  # 尚无行情：用成本代替
                day_fallback = True
            market_value += held * price
        if day_fallback:
            cost_fallback_days += 1

        total = cash + market_value
        net_invested = basis + deposits - withdrawals
        cumulative = total - net_invested
        points.append(
            {
                "point_date": current,
                "total_assets": portfolio_service._quantize(total, "0.0001"),
                "cash": portfolio_service._quantize(cash, "0.0001"),
                "market_value": portfolio_service._quantize(market_value, "0.0001"),
                "net_invested": portfolio_service._quantize(net_invested, "0.0001"),
                "cumulative_pnl": portfolio_service._quantize(cumulative, "0.0001"),
                "return_rate": (cumulative / net_invested) if net_invested > 0 else None,
            }
        )
        if len(points) >= MAX_PERFORMANCE_POINTS:
            notes.append(f"点数超过 {MAX_PERFORMANCE_POINTS}，已截断")
            break

    if cost_fallback_days:
        notes.append(f"有 {cost_fallback_days} 个日期缺少持仓行情，已按成本估值")
    if missing_price_assets:
        notes.append(f"{len(missing_price_assets)} 个持仓没有任何行情数据，始终按成本估值")

    included = sorted({key[1] for key in price_series if price_series[key]})
    excluded = sorted(set(missing_price_assets))
    coverage = {
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "points": len(points),
        "included_assets": len(included),
        "excluded_assets": excluded,
        "cost_fallback_days": cost_fallback_days,
        "missing_price_assets": excluded,
    }
    is_complete = cost_fallback_days == 0 and not excluded
    return _attach_benchmark(
        db,
        {
            "points": points,
            "coverage": coverage,
            "is_complete": is_complete,
            "basis": "account_balance_replay",
            "label": "账户资产重放（现金 + 持仓市值）",
            "notes": notes,
            "returns": _returns_block(points, is_complete=is_complete, coverage=coverage, notes=notes),
        },
        include_benchmark,
        benchmark_index_code,
    )
