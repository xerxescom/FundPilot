from __future__ import annotations

from decimal import Decimal

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.thresholds import get_thresholds
from app.db.models import AssetInfo, AssetPriceDaily, FundNav, PortfolioPosition, PortfolioTransaction
from app.db.models.fund import FundInfo
from app.services import asset_service
from app.services.nav_service import latest_nav

AUTO_SUMMARY_NOTE = "由交易记录自动汇总"
SELL_TYPES = {"sell", "redemption"}
BUY_TYPES = {"buy", "subscription"}


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


def _rebuild_position_from_transactions(db: Session, asset_type: str, asset_code: str) -> PortfolioPosition | None:
    transactions = list(
        db.scalars(
            select(PortfolioTransaction)
            .where(
                PortfolioTransaction.asset_type == asset_type,
                PortfolioTransaction.asset_code == asset_code,
            )
            .order_by(PortfolioTransaction.trade_date.asc(), PortfolioTransaction.id.asc())
        )
    )
    if not transactions:
        return None

    holding_share = Decimal("0")
    holding_cost = Decimal("0")
    for transaction in transactions:
        share = Decimal(transaction.share)
        amount = Decimal(transaction.amount)
        fee = Decimal(transaction.fee or 0)
        if transaction.trade_type in SELL_TYPES:
            if share > holding_share:
                raise ValueError("卖出份额超过当前可用持仓")
            average_cost = holding_cost / holding_share if holding_share else Decimal("0")
            holding_cost -= average_cost * share
            holding_share -= share
        else:
            holding_share += share
            holding_cost += amount + fee

    position = db.scalar(
        select(PortfolioPosition).where(
            PortfolioPosition.asset_type == asset_type,
            PortfolioPosition.asset_code == asset_code,
        )
    )
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
    db.commit()
    db.refresh(position)
    return position


def create_transaction(db: Session, data: dict) -> PortfolioTransaction:
    asset_type, asset_code = _payload_identity(data)
    amount = Decimal(data["amount"])
    price = Decimal(data["nav"])
    fee = Decimal(data.get("fee") or 0)
    trade_type = data.get("trade_type") or "buy"
    if trade_type not in BUY_TYPES | SELL_TYPES:
        raise ValueError("trade_type must be buy, sell, subscription or redemption")
    if amount <= 0 or price <= 0 or fee < 0:
        raise ValueError("amount and price must be positive, and fee cannot be negative")
    share = Decimal(data.get("share") or 0)
    if share <= 0:
        share = amount / price

    if trade_type in SELL_TYPES:
        position = db.scalar(
            select(PortfolioPosition).where(
                PortfolioPosition.asset_type == asset_type,
                PortfolioPosition.asset_code == asset_code,
            )
        )
        available_share = Decimal(position.holding_share or 0) if position else Decimal("0")
        if share > available_share:
            raise ValueError("卖出份额超过当前可用持仓")

    _ensure_listed_asset(db, asset_type, asset_code)
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
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    _rebuild_position_from_transactions(db, asset_type, asset_code)
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
    db.delete(transaction)
    db.commit()
    rebuilt = _rebuild_position_from_transactions(db, asset_type, asset_code)
    if rebuilt is None:
        position = db.scalar(
            select(PortfolioPosition).where(
                PortfolioPosition.asset_type == asset_type,
                PortfolioPosition.asset_code == asset_code,
            )
        )
        if position and position.note == AUTO_SUMMARY_NOTE:
            db.delete(position)
            db.commit()
    return True


def list_positions(db: Session) -> list[PortfolioPosition]:
    return list(db.scalars(select(PortfolioPosition).order_by(PortfolioPosition.created_at.desc())))


def update_position(db: Session, position_id: int, data: dict) -> PortfolioPosition | None:
    position = db.get(PortfolioPosition, position_id)
    if not position:
        return None
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


def _asset_name_and_price(db: Session, asset_type: str, asset_code: str) -> tuple[str | None, Decimal | None]:
    if asset_type == "fund":
        nav = latest_nav(db, asset_code)
        fund = db.scalar(select(FundInfo).where(FundInfo.fund_code == asset_code))
        return (fund.fund_name if fund else None, Decimal(nav.unit_nav) if nav and nav.unit_nav is not None else None)
    asset = asset_service.get_asset(db, asset_code)
    price = asset_service.latest_price(db, asset_code)
    return (asset.asset_name if asset else None, Decimal(price.close) if price and price.close is not None else None)


def position_summary(db: Session, position: PortfolioPosition) -> dict:
    asset_type, asset_code = _identity(position)
    asset_name, latest = _asset_name_and_price(db, asset_type, asset_code)
    if latest is None or position.holding_share is None:
        return {
            "position": position,
            "asset_type": asset_type,
            "asset_code": asset_code,
            "asset_name": asset_name,
            "fund_name": asset_name if asset_type == "fund" else None,
            "latest_price": latest,
            "latest_nav": latest if asset_type == "fund" else None,
            "current_value": None,
            "profit_amount": None,
            "profit_rate": None,
        }
    current_value = Decimal(position.holding_share) * latest
    cost = Decimal(position.holding_amount) if position.holding_amount is not None else None
    if cost is None and position.cost_nav is not None:
        cost = Decimal(position.holding_share) * Decimal(position.cost_nav)
    profit = current_value - cost if cost is not None else None
    return {
        "position": position,
        "asset_type": asset_type,
        "asset_code": asset_code,
        "asset_name": asset_name,
        "fund_name": asset_name if asset_type == "fund" else None,
        "latest_price": latest,
        "latest_nav": latest if asset_type == "fund" else None,
        "current_value": current_value,
        "profit_amount": profit,
        "profit_rate": profit / cost if profit is not None and cost else None,
    }


def portfolio_overview(db: Session) -> dict:
    summaries = [position_summary(db, item) for item in list_positions(db)]
    total_value = sum((item["current_value"] or Decimal("0")) for item in summaries)
    total_cost = sum(
        (
            Decimal(summary["position"].holding_amount)
            if summary["position"].holding_amount is not None
            else Decimal(summary["position"].holding_share or 0) * Decimal(summary["position"].cost_nav or 0)
        )
        for summary in summaries
    )
    profit_amount = total_value - total_cost if total_cost else None
    weights = [(summary["current_value"] or Decimal("0")) / total_value for summary in summaries] if total_value else []
    return {
        "total_value": total_value,
        "total_cost": total_cost if total_cost else None,
        "profit_amount": profit_amount,
        "profit_rate": profit_amount / total_cost if profit_amount is not None and total_cost else None,
        "max_weight": max(weights) if weights else None,
        "drawdown_1m": portfolio_drawdown_1m(db),
        "positions": summaries,
    }


def portfolio_drawdown_1m(db: Session) -> Decimal | None:
    positions = [item for item in list_positions(db) if item.holding_share is not None]
    if not positions:
        return None
    rows: list[dict] = []
    for position in positions:
        asset_type, asset_code = _identity(position)
        share = Decimal(position.holding_share)
        if asset_type == "fund":
            prices = db.scalars(
                select(FundNav)
                .where(FundNav.fund_code == asset_code, FundNav.unit_nav.is_not(None))
                .order_by(FundNav.nav_date.asc())
            )
            rows.extend(
                {"date": item.nav_date, "asset_code": asset_code, "value": float(Decimal(item.unit_nav) * share)}
                for item in prices
            )
        else:
            prices = db.scalars(
                select(AssetPriceDaily)
                .where(AssetPriceDaily.asset_code == asset_code, AssetPriceDaily.close.is_not(None))
                .order_by(AssetPriceDaily.price_date.asc())
            )
            rows.extend(
                {"date": item.price_date, "asset_code": asset_code, "value": float(Decimal(item.close) * share)}
                for item in prices
            )
    if not rows:
        return None
    frame = pd.DataFrame(rows)
    daily_value = frame.pivot_table(index="date", columns="asset_code", values="value").sum(axis=1)
    one_month = daily_value.tail(30)
    if len(one_month) < 2:
        return None
    return Decimal(str(float((one_month / one_month.cummax() - 1).min()))).quantize(Decimal("0.000001"))


def portfolio_diagnosis(db: Session) -> dict:
    thresholds = get_thresholds()
    overview = portfolio_overview(db)
    positions = overview["positions"]
    risk_items = []
    max_weight = overview["max_weight"]
    drawdown_1m = overview["drawdown_1m"]
    stale_positions = [item for item in positions if item["latest_price"] is None]
    if max_weight is not None and max_weight >= Decimal(str(thresholds.portfolio_concentration)):
        risk_items.append({"level": "medium", "title": "持仓集中度偏高", "description": f"单一资产估算占比达到 {max_weight:.2%}，建议重点观察其对组合波动的影响。"})
    if drawdown_1m is not None and drawdown_1m <= Decimal(str(thresholds.portfolio_drawdown_alert)):
        risk_items.append({"level": "medium", "title": "组合近 1 月回撤较大", "description": f"组合近 1 月估算最大回撤为 {drawdown_1m:.2%}，建议结合市场环境复盘。"})
    if stale_positions:
        risk_items.append({"level": "low", "title": "部分持仓缺少最新行情", "description": f"{len(stale_positions)} 个持仓暂时无法估算最新市值，请先同步对应行情或净值。"})
    if not risk_items:
        risk_items.append({"level": "info", "title": "暂无突出组合风险", "description": "当前组合未触发集中度、回撤或行情缺失规则，仍建议持续观察预警变化。"})
    return {
        "summary": {"position_count": len(positions), "total_value": overview["total_value"], "profit_rate": overview["profit_rate"], "max_weight": max_weight, "drawdown_1m": drawdown_1m},
        "risk_items": risk_items,
        "observation": "组合诊断仅用于风险观察和复盘，不构成买入或卖出建议。",
    }


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
