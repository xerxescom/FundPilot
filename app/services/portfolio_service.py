from __future__ import annotations

from datetime import date
from decimal import Decimal

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.thresholds import get_thresholds
from app.db.models import AssetInfo, AssetPriceDaily, FundNav, PortfolioPosition, PortfolioTransaction
from app.db.models.fund import FundInfo
from app.schemas.portfolio import HoldingScreenshotDraft
from app.services import asset_service
from app.services.nav_service import latest_nav

AUTO_SUMMARY_NOTE = "由交易记录自动汇总"
OPENING_NOTE = "期初持仓"
SELL_TYPES = {"sell", "redemption"}
BUY_TYPES = {"buy", "subscription", "opening"}
REINVEST_TYPES = {"dividend_reinvest"}
SPLIT_TYPES = {"split"}
ALL_TRADE_TYPES = BUY_TYPES | SELL_TYPES | REINVEST_TYPES | SPLIT_TYPES
LEDGER_MANAGED_FIELDS = {"holding_amount", "holding_share", "cost_nav", "buy_date"}
DRAWDOWN_WINDOW = 30
MIN_DRAWDOWN_DAYS = 2


def _quantize(value: Decimal, places: str) -> Decimal:
    return value.quantize(Decimal(places))


def _identity(item: PortfolioPosition | PortfolioTransaction) -> tuple[str, str]:
    asset_type = item.asset_type or "fund"
    asset_code = item.asset_code or item.fund_code
    return asset_type, asset_service.normalize_asset_code(asset_code, asset_type)


def _payload_identity(data: dict) -> tuple[str, str]:
    asset_type = data.get("asset_type") or "fund"
    if asset_type not in {"fund", "stock", "etf"}:
        raise ValueError("asset_type must be fund, stock or etf")
    raw_code = data.get("asset_code") or data.get("fund_code")
    if not raw_code:
        raise ValueError("asset_code is required")
    return asset_type, asset_service.normalize_asset_code(str(raw_code), asset_type)


def _ensure_listed_asset(db: Session, asset_type: str, asset_code: str) -> None:
    if asset_type not in asset_service.LISTED_ASSET_TYPES:
        return
    asset = asset_service.get_asset(db, asset_code)
    if asset is None:
        db.add(
            AssetInfo(
                asset_code=asset_code,
                asset_type=asset_type,
                asset_name=asset_code,
                market="CN",
                currency="CNY",
                source="manual",
            )
        )


def _position_criteria(asset_type: str, asset_code: str):
    # asset_code is NULL on legacy rows; fund_code keeps the code for those.
    return (
        PortfolioPosition.asset_type == asset_type,
        (PortfolioPosition.asset_code == asset_code)
        | (PortfolioPosition.asset_code.is_(None) & (PortfolioPosition.fund_code == asset_code)),
    )


def _transaction_criteria(asset_type: str, asset_code: str):
    return (
        PortfolioTransaction.asset_type == asset_type,
        (PortfolioTransaction.asset_code == asset_code)
        | (PortfolioTransaction.asset_code.is_(None) & (PortfolioTransaction.fund_code == asset_code)),
    )


def _position_row(
    db: Session, asset_type: str, asset_code: str, for_update: bool = False
) -> PortfolioPosition | None:
    stmt = select(PortfolioPosition).where(*_position_criteria(asset_type, asset_code))
    if for_update:
        stmt = stmt.with_for_update()
    return db.scalar(stmt)


def _asset_transactions(db: Session, asset_type: str, asset_code: str) -> list[PortfolioTransaction]:
    return list(
        db.scalars(
            select(PortfolioTransaction)
            .where(*_transaction_criteria(asset_type, asset_code))
            .order_by(PortfolioTransaction.trade_date.asc(), PortfolioTransaction.id.asc())
        )
    )


def create_position(db: Session, data: dict) -> PortfolioPosition:
    asset_type, asset_code = _payload_identity(data)
    _ensure_listed_asset(db, asset_type, asset_code)
    position = PortfolioPosition(
        **{
            **data,
            "fund_code": asset_code,
            "asset_type": asset_type,
            "asset_code": asset_code,
        }
    )
    db.add(position)
    db.commit()
    db.refresh(position)
    return position


def replay_ledger_events(events: list) -> tuple[Decimal, Decimal, list[tuple[object, Decimal]]]:
    """按时间顺序重放账本事件；卖出超过当日可用份额时抛错。

    返回 (holding_share, holding_cost, [(卖出事件, 已实现盈亏), ...])。
    事件只要求具备 trade_type / share / amount / fee / trade_date 属性，
    因此 CSV 预览可以对未落库的行做只读模拟。
    """
    holding_share = Decimal("0")
    holding_cost = Decimal("0")
    realized: list[tuple[object, Decimal]] = []
    for event in events:
        share = Decimal(event.share)
        amount = Decimal(event.amount)
        fee = Decimal(event.fee or 0)
        trade_type = event.trade_type
        if trade_type in SELL_TYPES:
            if share > holding_share:
                raise ValueError(
                    f"卖出份额超过 {event.trade_date} 可用持仓：需要 {share} 份，当日仅有 {holding_share} 份"
                )
            average_cost = holding_cost / holding_share if holding_share else Decimal("0")
            realized.append((event, _quantize((amount - fee) - average_cost * share, "0.0001")))
            holding_cost -= average_cost * share
            holding_share -= share
        elif trade_type in SPLIT_TYPES:
            if holding_share + share < 0:
                raise ValueError(
                    f"拆分后份额为负：{event.trade_date} 变动 {share} 份，拆分前 {holding_share} 份"
                )
            holding_share += share  # 拆分只改变份额，成本不变
        elif trade_type in REINVEST_TYPES:
            holding_share += share
            holding_cost += amount  # 红利再投：分红被资本化，无现金进出、无费用
        else:  # buy / subscription / opening
            holding_share += share
            holding_cost += amount + fee
    return holding_share, holding_cost, realized


def _replay_transactions(transactions: list[PortfolioTransaction]) -> tuple[Decimal, Decimal]:
    holding_share, holding_cost, _ = replay_ledger_events(transactions)
    return holding_share, holding_cost


def _rebuild_position_from_transactions(
    db: Session, asset_type: str, asset_code: str
) -> PortfolioPosition | None:
    """Rebuild the position from the ledger. Flushes only; the caller owns commit/rollback."""
    transactions = _asset_transactions(db, asset_type, asset_code)
    if not transactions:
        return None

    holding_share, holding_cost, realized_entries = replay_ledger_events(transactions)
    for event, realized_value in realized_entries:
        event.realized_pnl = realized_value  # 每次重建确定性重算，后补/删除流水都会自动修正
    position = _position_row(db, asset_type, asset_code)
    cost_nav = holding_cost / holding_share if holding_share else None
    values = {
        "holding_amount": _quantize(holding_cost, "0.0001"),
        "holding_share": _quantize(holding_share, "0.0001"),
        "cost_nav": _quantize(cost_nav, "0.000001") if cost_nav else None,
        "buy_date": transactions[0].trade_date,
        "note": AUTO_SUMMARY_NOTE,
    }
    if position:
        for key, value in values.items():
            setattr(position, key, value)
    else:
        position = PortfolioPosition(
            fund_code=asset_code,
            asset_type=asset_type,
            asset_code=asset_code,
            **values,
        )
        db.add(position)
    db.flush()
    return position


def opening_values(position: PortfolioPosition) -> dict | None:
    """纯函数：从手工/截图持仓推导期初事件数值；成本缺失或份额为 0 时返回 None（不编造成本）。"""
    share = Decimal(position.holding_share or 0)
    if share <= 0:
        return None
    nav = Decimal(position.cost_nav) if position.cost_nav is not None else None
    amount = Decimal(position.holding_amount) if position.holding_amount is not None else None
    if nav is None and amount is not None:
        nav = amount / share
    if amount is None and nav is not None:
        amount = share * nav
    if nav is None or nav <= 0 or amount is None or amount <= 0:
        return None
    trade_date = position.buy_date or (position.created_at.date() if position.created_at else date.today())
    note = f"{OPENING_NOTE}；来源：{position.note}" if position.note else OPENING_NOTE
    return {
        "trade_date": trade_date,
        "amount": _quantize(amount, "0.0001"),
        "nav": _quantize(nav, "0.000001"),
        "share": _quantize(share, "0.0001"),
        "note": note,
    }


def _build_opening_transaction(position: PortfolioPosition) -> PortfolioTransaction | None:
    """Build the dated opening event for a manual/screenshot holding without inventing cost."""
    values = opening_values(position)
    if values is None:
        return None
    asset_type, asset_code = _identity(position)
    return PortfolioTransaction(
        fund_code=asset_code,
        asset_type=asset_type,
        asset_code=asset_code,
        trade_date=values["trade_date"],
        trade_type="opening",
        amount=values["amount"],
        nav=values["nav"],
        share=values["share"],
        fee=Decimal("0"),
        note=values["note"],
        source="opening",
    )


def ensure_opening_transaction(db: Session, position: PortfolioPosition | None) -> PortfolioTransaction | None:
    """Materialize manual/screenshot holdings as the first ledger event before replaying transactions."""
    if position is None or position.note == AUTO_SUMMARY_NOTE:
        return None
    asset_type, asset_code = _identity(position)
    has_transactions = db.scalar(
        select(PortfolioTransaction.id).where(*_transaction_criteria(asset_type, asset_code)).limit(1)
    )
    if has_transactions:
        return None
    opening = _build_opening_transaction(position)
    if opening is None:
        if Decimal(position.holding_share or 0) > 0:
            raise ValueError("该持仓缺少成本信息，无法自动生成期初记录；请先补全持仓成本后再记录交易")
        return None
    db.add(opening)
    return opening


def create_transaction(db: Session, data: dict) -> PortfolioTransaction:
    asset_type, asset_code = _payload_identity(data)
    amount = Decimal(data["amount"])
    price = Decimal(data["nav"]) if data.get("nav") is not None else Decimal("0")
    fee = Decimal(data.get("fee") or 0)
    trade_type = data.get("trade_type") or "buy"
    if trade_type not in ALL_TRADE_TYPES:
        raise ValueError(
            "trade_type must be buy, sell, subscription, redemption, opening, dividend_reinvest or split"
        )
    share = Decimal(data.get("share") or 0)
    if trade_type in SPLIT_TYPES:
        if amount != 0:
            raise ValueError("拆分交易金额必须为 0")
        if fee != 0:
            raise ValueError("拆分交易不支持手续费")
        if share == 0:
            raise ValueError("拆分交易必须填写份额变动（正数增加，负数减少）")
        price = price or Decimal("1")  # 拆分没有成交价，占位避免空值
    elif trade_type in REINVEST_TYPES:
        if amount <= 0 or price <= 0:
            raise ValueError("红利再投的金额与净值必须为正")
        if fee != 0:
            raise ValueError("红利再投暂不支持手续费")
        if share <= 0:
            share = amount / price
    else:
        if amount <= 0 or price <= 0 or fee < 0:
            raise ValueError("amount and price must be positive, and fee cannot be negative")
        if share <= 0:
            share = amount / price

    _ensure_listed_asset(db, asset_type, asset_code)
    try:
        position = _position_row(db, asset_type, asset_code, for_update=True)
        if trade_type == "opening":
            existing_opening = db.scalar(
                select(PortfolioTransaction.id)
                .where(*_transaction_criteria(asset_type, asset_code))
                .where(PortfolioTransaction.trade_type == "opening")
                .limit(1)
            )
            if existing_opening:
                raise ValueError("该资产已存在期初持仓记录，不能重复添加")
            if position is not None and Decimal(position.holding_share or 0) > 0:
                raise ValueError("该资产已有手工或截图持仓，请先删除该持仓或用交易记录调整")
        else:
            ensure_opening_transaction(db, position)

        transaction = PortfolioTransaction(
            # fund_code remains populated as a legacy-compatible alias for old database rows and APIs.
            fund_code=asset_code,
            asset_type=asset_type,
            asset_code=asset_code,
            trade_date=data["trade_date"],
            trade_type=trade_type,
            amount=_quantize(amount, "0.0001"),
            nav=_quantize(price, "0.000001"),
            share=_quantize(share, "0.0001"),
            fee=_quantize(fee, "0.0001"),
            note=data.get("note"),
            source="manual",
        )
        db.add(transaction)
        db.flush()
        _rebuild_position_from_transactions(db, asset_type, asset_code)
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(transaction)
    return transaction


def list_transactions(
    db: Session, fund_code: str | None = None, asset_code: str | None = None
) -> list[PortfolioTransaction]:
    stmt = select(PortfolioTransaction).order_by(PortfolioTransaction.trade_date.desc(), PortfolioTransaction.id.desc())
    code = asset_code or fund_code
    if code:
        stmt = stmt.where(
            (PortfolioTransaction.asset_code == code) | (PortfolioTransaction.fund_code == code.zfill(6))
        )
    return list(db.scalars(stmt))


def delete_transaction(db: Session, transaction_id: int) -> bool:
    transaction = db.get(PortfolioTransaction, transaction_id)
    if not transaction:
        return False
    asset_type, asset_code = _identity(transaction)
    try:
        db.delete(transaction)
        db.flush()
        rebuilt = _rebuild_position_from_transactions(db, asset_type, asset_code)
        if rebuilt is None:
            position = _position_row(db, asset_type, asset_code)
            if position and position.note == AUTO_SUMMARY_NOTE:
                db.delete(position)
        db.commit()
    except Exception:
        db.rollback()
        raise
    return True


def list_positions(db: Session) -> list[PortfolioPosition]:
    return list(db.scalars(select(PortfolioPosition).order_by(PortfolioPosition.created_at.desc())))


def update_position(db: Session, position_id: int, data: dict) -> PortfolioPosition | None:
    position = db.get(PortfolioPosition, position_id)
    if not position:
        return None
    if LEDGER_MANAGED_FIELDS & set(data):
        asset_type, asset_code = _identity(position)
        has_transactions = db.scalar(
            select(PortfolioTransaction.id).where(*_transaction_criteria(asset_type, asset_code)).limit(1)
        )
        if has_transactions:
            raise ValueError("该持仓已由交易流水管理，不能直接修改份额、成本或买入日期；请通过交易记录调整")
    for key, value in data.items():
        if value is not None:
            setattr(position, key, value)
    db.commit()
    db.refresh(position)
    return position


def delete_position(db: Session, position_id: int) -> bool:
    position = db.get(PortfolioPosition, position_id)
    if not position:
        return False
    db.delete(position)
    db.commit()
    return True


def _asset_snapshot(db: Session, asset_type: str, asset_code: str) -> dict:
    if asset_type == "fund":
        nav = latest_nav(db, asset_code)
        fund = db.scalar(select(FundInfo).where(FundInfo.fund_code == asset_code))
        usable = nav is not None and nav.unit_nav is not None
        return {
            "name": fund.fund_name if fund else None,
            "price": Decimal(nav.unit_nav) if usable else None,
            "price_date": nav.nav_date if usable else None,
            "price_source": nav.source if usable else None,
        }
    asset = asset_service.get_asset(db, asset_code)
    price = asset_service.latest_price(db, asset_code)
    usable = price is not None and price.close is not None
    return {
        "name": asset.asset_name if asset else None,
        "price": Decimal(price.close) if usable else None,
        "price_date": price.price_date if usable else None,
        "price_source": price.source if usable else None,
    }


def _position_cost(position: PortfolioPosition) -> Decimal | None:
    if position.holding_amount is not None:
        return Decimal(position.holding_amount)
    if position.cost_nav is not None and position.holding_share is not None:
        return Decimal(position.holding_share) * Decimal(position.cost_nav)
    return None


def position_summary(db: Session, position: PortfolioPosition) -> dict:
    asset_type, asset_code = _identity(position)
    snapshot = _asset_snapshot(db, asset_type, asset_code)
    latest = snapshot["price"]
    share = Decimal(position.holding_share) if position.holding_share is not None else None
    cost = _position_cost(position)

    missing_reason = None
    current_value = None
    if share is None:
        missing_reason = "缺少持仓份额"
    elif share == 0:
        current_value = Decimal("0")
    elif latest is None:
        missing_reason = "缺少最新净值" if asset_type == "fund" else "缺少最新行情"
    else:
        current_value = share * latest

    profit = None
    profit_rate = None
    if current_value is not None and cost is not None:
        profit = current_value - cost
        profit_rate = profit / cost if cost else None

    return {
        "position": position,
        "asset_type": asset_type,
        "asset_code": asset_code,
        "asset_name": snapshot["name"],
        "fund_name": snapshot["name"] if asset_type == "fund" else None,
        "latest_price": latest,
        "latest_nav": latest if asset_type == "fund" else None,
        "price_date": snapshot["price_date"],
        "price_source": snapshot["price_source"],
        "missing_reason": missing_reason,
        "current_value": current_value,
        "profit_amount": profit,
        "profit_rate": profit_rate,
    }


def portfolio_overview(db: Session) -> dict:
    summaries = [position_summary(db, item) for item in list_positions(db)]
    missing_price_assets = [
        {
            "asset_type": summary["asset_type"],
            "asset_code": summary["asset_code"],
            "asset_name": summary["asset_name"],
            "reason": summary["missing_reason"],
        }
        for summary in summaries
        if summary["missing_reason"]
    ]
    missing_cost_assets = [
        {
            "asset_type": summary["asset_type"],
            "asset_code": summary["asset_code"],
            "asset_name": summary["asset_name"],
            "reason": "缺少成本信息",
        }
        for summary in summaries
        if _position_cost(summary["position"]) is None
        and Decimal(summary["position"].holding_share or 0) > 0
    ]
    priced = [summary for summary in summaries if summary["current_value"] is not None]
    known_value = sum((summary["current_value"] for summary in priced), Decimal("0"))
    total_cost = sum((_position_cost(summary["position"]) or Decimal("0") for summary in summaries), Decimal("0"))
    is_complete = not missing_price_assets
    if not summaries:
        valuation_status = "empty"
    elif is_complete:
        valuation_status = "complete"
    else:
        valuation_status = "partial"

    price_dates = [summary["price_date"] for summary in priced if summary["price_date"]]
    price_as_of = max(price_dates) if price_dates else None
    total_value = known_value if is_complete else None

    profit_amount = None
    profit_rate = None
    if is_complete and not missing_cost_assets and total_cost:
        profit_amount = total_value - total_cost
        profit_rate = profit_amount / total_cost
    weights = [summary["current_value"] / total_value for summary in priced] if total_value else []

    detail = portfolio_drawdown_detail(db)
    return {
        "as_of": date.today(),
        "price_as_of": price_as_of,
        "valuation_status": valuation_status,
        "is_complete": is_complete,
        "known_value": known_value,
        "priced_position_count": len(priced),
        "missing_price_assets": missing_price_assets,
        "missing_cost_assets": missing_cost_assets,
        "total_value": total_value,
        "total_cost": total_cost if total_cost else None,
        "profit_amount": profit_amount,
        "profit_rate": profit_rate,
        "max_weight": max(weights) if weights else None,
        "drawdown_1m": detail["drawdown_1m"],
        "drawdown_basis": detail["basis"],
        "positions": summaries,
    }


def portfolio_drawdown_detail(db: Session) -> dict:
    """Current-holdings historical simulation.

    Values today's holdings at each past price; only dates on which every included
    asset has a price are used, so missing quotes never fabricate a drop.
    """
    positions = [
        item
        for item in list_positions(db)
        if item.holding_share is not None and Decimal(item.holding_share) > 0
    ]
    series: dict[str, pd.Series] = {}
    excluded: list[str] = []
    for position in positions:
        asset_type, asset_code = _identity(position)
        share = Decimal(position.holding_share)
        if asset_type == "fund":
            price_rows = db.scalars(
                select(FundNav)
                .where(FundNav.fund_code == asset_code, FundNav.unit_nav.is_not(None))
                .order_by(FundNav.nav_date.asc())
            )
            rows = [(item.nav_date, Decimal(item.unit_nav)) for item in price_rows]
        else:
            price_rows = db.scalars(
                select(AssetPriceDaily)
                .where(AssetPriceDaily.asset_code == asset_code, AssetPriceDaily.close.is_not(None))
                .order_by(AssetPriceDaily.price_date.asc())
            )
            rows = [(item.price_date, Decimal(item.close)) for item in price_rows]
        if not rows:
            excluded.append(asset_code)
            continue
        series[asset_code] = pd.Series({day: float(value * share) for day, value in rows})

    basis = {
        "basis": "current_holdings_simulation",
        "label": "当前持仓历史模拟",
        "window": f"最近{DRAWDOWN_WINDOW}个共同交易日",
        "window_days": DRAWDOWN_WINDOW,
        "aligned_days": 0,
        "included_asset_count": len(series),
        "excluded_asset_codes": excluded,
        "start_date": None,
        "end_date": None,
    }
    if not series:
        return {"drawdown_1m": None, "basis": basis}

    frame = pd.DataFrame(series)
    aligned = frame.dropna(how="any")
    window = aligned.tail(DRAWDOWN_WINDOW)
    basis["aligned_days"] = len(window)
    if len(window):
        basis["start_date"] = pd.Timestamp(window.index[0]).date()
        basis["end_date"] = pd.Timestamp(window.index[-1]).date()
    if len(window) < MIN_DRAWDOWN_DAYS:
        return {"drawdown_1m": None, "basis": basis}

    daily_value = window.sum(axis=1)
    drawdown = Decimal(str(float((daily_value / daily_value.cummax() - 1).min()))).quantize(Decimal("0.000001"))
    return {"drawdown_1m": drawdown, "basis": basis}


def portfolio_drawdown_1m(db: Session) -> Decimal | None:
    return portfolio_drawdown_detail(db)["drawdown_1m"]


def portfolio_diagnosis(db: Session) -> dict:
    thresholds = get_thresholds()
    overview = portfolio_overview(db)
    positions = overview["positions"]
    risk_items = []
    max_weight = overview["max_weight"]
    drawdown_1m = overview["drawdown_1m"]
    basis = overview["drawdown_basis"]
    stale_positions = [item for item in positions if item["missing_reason"]]
    if max_weight is not None and max_weight >= Decimal(str(thresholds.portfolio_concentration)):
        risk_items.append({"level": "medium", "title": "持仓集中度偏高", "description": f"单一资产估算占比达到 {max_weight:.2%}，建议重点观察其对组合波动的影响。"})
    if drawdown_1m is not None and drawdown_1m <= Decimal(str(thresholds.portfolio_drawdown_alert)):
        risk_items.append(
            {
                "level": "medium",
                "title": "组合近 1 月回撤较大",
                "description": f"组合近 1 月估算最大回撤为 {drawdown_1m:.2%}（{basis['label']}口径，{basis['window']}），建议结合市场环境复盘。",
            }
        )
    if stale_positions:
        risk_items.append({"level": "low", "title": "部分持仓缺少最新行情", "description": f"{len(stale_positions)} 个持仓暂时无法估算最新市值，请先同步对应行情或净值。"})
    if not risk_items:
        risk_items.append({"level": "info", "title": "暂无突出组合风险", "description": "当前组合未触发集中度、回撤或行情缺失规则，仍建议持续观察预警变化。"})
    return {
        "summary": {
            "position_count": len(positions),
            "total_value": overview["total_value"],
            "known_value": overview["known_value"],
            "is_complete": overview["is_complete"],
            "valuation_status": overview["valuation_status"],
            "missing_price_count": len(overview["missing_price_assets"]),
            "profit_rate": overview["profit_rate"],
            "max_weight": max_weight,
            "drawdown_1m": drawdown_1m,
            "drawdown_basis": basis,
        },
        "risk_items": risk_items,
        "observation": "组合诊断仅用于风险观察和复盘，不构成买入或卖出建议。",
    }


def import_screenshot_holdings(
    db: Session, holdings: list[HoldingScreenshotDraft], as_of_date: date
) -> dict:
    """Upsert confirmed broker snapshots without inventing transaction history."""
    created = 0
    updated = 0
    skipped: list[dict[str, str]] = []
    for holding in holdings:
        asset_type = holding.asset_type
        asset_code = asset_service.normalize_asset_code(holding.asset_code, asset_type)
        has_transactions = db.scalar(
            select(PortfolioTransaction.id).where(*_transaction_criteria(asset_type, asset_code)).limit(1)
        )
        if has_transactions:
            skipped.append({"asset_code": asset_code, "reason": "已有交易流水，未用截图覆盖成本与持仓"})
            continue

        _upsert_screenshot_asset_metadata(db, holding, asset_code, as_of_date)
        position = _position_row(db, asset_type, asset_code)
        cost_price = Decimal(holding.cost_price) if holding.cost_price is not None else None
        values = {
            "holding_share": _quantize(Decimal(holding.holding_share), "0.0001"),
            "holding_amount": _quantize(Decimal(holding.holding_share) * cost_price, "0.0001")
            if cost_price is not None
            else None,
            "cost_nav": _quantize(cost_price, "0.000001") if cost_price is not None else None,
            "buy_date": as_of_date,
        }
        if position:
            for key, value in values.items():
                setattr(position, key, value)
            if not position.note:
                position.note = f"由中信证券持仓截图导入（{as_of_date.isoformat()}）"
            updated += 1
        else:
            db.add(
                PortfolioPosition(
                    fund_code=asset_code,
                    asset_type=asset_type,
                    asset_code=asset_code,
                    note=f"由中信证券持仓截图导入（{as_of_date.isoformat()}）",
                    **values,
                )
            )
            created += 1
    db.commit()
    return {"created": created, "updated": updated, "skipped": skipped}


def _upsert_screenshot_asset_metadata(
    db: Session, holding: HoldingScreenshotDraft, asset_code: str, as_of_date: date
) -> None:
    """Persist confirmed labels and the dated screenshot price until regular sync replaces it."""
    snapshot_price = holding.current_price
    if snapshot_price is None and holding.market_value is not None:
        snapshot_price = Decimal(holding.market_value) / Decimal(holding.holding_share)
    if holding.asset_type == "fund":
        fund = db.scalar(select(FundInfo).where(FundInfo.fund_code == asset_code))
        if fund is None:
            db.add(FundInfo(fund_code=asset_code, fund_name=holding.asset_name or asset_code, fund_type="未知", source="citic_screenshot"))
        elif holding.asset_name:
            fund.fund_name = holding.asset_name
        if snapshot_price is not None:
            nav = db.scalar(select(FundNav).where(FundNav.fund_code == asset_code, FundNav.nav_date == as_of_date))
            if nav is None:
                db.add(FundNav(fund_code=asset_code, nav_date=as_of_date, unit_nav=_quantize(Decimal(snapshot_price), "0.000001"), accumulated_nav=None, daily_return=None, source="citic_screenshot"))
            else:
                nav.unit_nav = _quantize(Decimal(snapshot_price), "0.000001")
                nav.source = "citic_screenshot"
        return

    asset = asset_service.get_asset(db, asset_code)
    if asset is None:
        asset = AssetInfo(asset_code=asset_code, asset_type=holding.asset_type, asset_name=holding.asset_name or asset_code, market="CN", currency="CNY", source="citic_screenshot")
        db.add(asset)
    elif holding.asset_name:
        asset.asset_name = holding.asset_name
    if snapshot_price is not None:
        price = db.scalar(select(AssetPriceDaily).where(AssetPriceDaily.asset_code == asset_code, AssetPriceDaily.price_date == as_of_date))
        if price is None:
            db.add(AssetPriceDaily(asset_code=asset_code, price_date=as_of_date, close=_quantize(Decimal(snapshot_price), "0.000001"), daily_return=None, source="citic_screenshot"))
        else:
            price.close = _quantize(Decimal(snapshot_price), "0.000001")
            price.source = "citic_screenshot"


def _portfolio_value_by_fund(db: Session) -> dict[str, Decimal]:
    values: dict[str, Decimal] = {}
    for summary in [position_summary(db, item) for item in list_positions(db)]:
        if summary["asset_type"] != "fund" or summary["current_value"] is None:
            continue
        code = summary["asset_code"]
        values[code] = values.get(code, Decimal("0")) + Decimal(summary["current_value"])
    return values


def _fund_name_map(db: Session, codes: list[str]) -> dict[str, str]:
    if not codes:
        return {}
    infos = db.scalars(select(FundInfo).where(FundInfo.fund_code.in_(codes))).all()
    return {item.fund_code: item.fund_name for item in infos}


def simulate_buy(db: Session, fund_code: str, amount: Decimal) -> dict:
    """Keep the existing fund-only correlation simulation separate from the unified ledger."""
    thresholds = get_thresholds()
    fund_code = fund_code.zfill(6)
    amount = Decimal(amount)
    if amount <= 0:
        raise ValueError("amount must be positive")
    before_values = _portfolio_value_by_fund(db)
    total_before = sum(before_values.values(), Decimal("0"))
    after_values = dict(before_values)
    after_values[fund_code] = after_values.get(fund_code, Decimal("0")) + amount
    total_after = total_before + amount
    max_weight_before = max((value / total_before for value in before_values.values()), default=None) if total_before else None
    max_weight_after = max((value / total_after for value in after_values.values()), default=None) if total_after else None
    target_weight_before = before_values.get(fund_code, Decimal("0")) / total_before if total_before else Decimal("0")
    target_weight_after = after_values[fund_code] / total_after

    current_codes = sorted(before_values)
    high_corr_threshold = Decimal(str(thresholds.correlation_high))
    nav_rows = db.scalars(select(FundNav).where(FundNav.fund_code.in_(sorted(set(current_codes + [fund_code]))), FundNav.daily_return.is_not(None)).order_by(FundNav.nav_date.asc())).all()
    frame = pd.DataFrame([{"nav_date": row.nav_date, "fund_code": row.fund_code, "daily_return": float(row.daily_return)} for row in nav_rows])
    corr = frame.pivot_table(index="nav_date", columns="fund_code", values="daily_return").corr(min_periods=5) if not frame.empty else pd.DataFrame()
    corr_pairs: list[dict] = []
    correlations: list[Decimal] = []
    if not corr.empty and fund_code in corr.columns:
        name_map = _fund_name_map(db, current_codes + [fund_code])
        for code in current_codes:
            if code == fund_code or code not in corr.columns:
                continue
            value = corr.loc[fund_code, code]
            if pd.notna(value):
                corr_value = Decimal(str(float(value))).quantize(Decimal("0.0001"))
                correlations.append(corr_value)
                if corr_value >= high_corr_threshold:
                    corr_pairs.append({"fund_code": code, "fund_name": name_map.get(code, code), "correlation": corr_value})
    max_correlation = max(correlations) if correlations else None
    avg_correlation = (sum(correlations, Decimal("0")) / Decimal(len(correlations))).quantize(Decimal("0.0001")) if correlations else None
    risk_items = []
    if max_weight_after is not None and max_weight_after >= Decimal(str(thresholds.portfolio_concentration)):
        risk_items.append({"level": "medium", "title": "买入后持仓集中度偏高", "description": f"买入后单只基金最大占比约 {max_weight_after:.2%}，需要关注组合对单一基金波动的敏感度。"})
    if target_weight_after >= Decimal(str(thresholds.portfolio_concentration)):
        risk_items.append({"level": "medium", "title": "目标基金占比偏高", "description": f"拟买入后该基金占组合约 {target_weight_after:.2%}，可能放大单一标的影响。"})
    if max_correlation is not None and max_correlation >= high_corr_threshold:
        risk_items.append({"level": "medium", "title": "与现有持仓相关性偏高", "description": f"该基金与现有持仓最高相关性约 {max_correlation:.2f}，可能带来重复配置。"})
    if not risk_items:
        risk_items.append({"level": "info", "title": "未触发明显新增风险", "description": "按当前净值和相关性样本估算，拟买入未显著放大集中度或高相关风险。"})
    name_map = _fund_name_map(db, [fund_code])
    return {"fund_code": fund_code, "fund_name": name_map.get(fund_code), "amount": amount, "total_value_before": total_before, "total_value_after": total_after, "target_weight_before": target_weight_before, "target_weight_after": target_weight_after, "max_weight_before": max_weight_before, "max_weight_after": max_weight_after, "position_count_before": len(before_values), "position_count_after": len(after_values), "max_correlation": max_correlation, "avg_correlation": avg_correlation, "high_correlation_positions": corr_pairs, "risk_items": risk_items, "observation": "买入模拟仅用于观察集中度和相关性变化，不构成买入或卖出建议。"}
