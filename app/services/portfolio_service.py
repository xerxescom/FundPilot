from decimal import Decimal

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FundNav, PortfolioPosition, PortfolioTransaction
from app.db.models.fund import FundInfo
from app.services.nav_service import latest_nav

AUTO_SUMMARY_NOTE = "由买入记录自动汇总"


def create_position(db: Session, data: dict) -> PortfolioPosition:
    position = PortfolioPosition(**data)
    position.fund_code = position.fund_code.zfill(6)
    db.add(position)
    db.commit()
    db.refresh(position)
    return position


def _quantize(value: Decimal, places: str) -> Decimal:
    return value.quantize(Decimal(places))


def _rebuild_position_from_transactions(db: Session, fund_code: str) -> PortfolioPosition | None:
    fund_code = fund_code.zfill(6)
    transactions = list(
        db.scalars(
            select(PortfolioTransaction)
            .where(PortfolioTransaction.fund_code == fund_code)
            .order_by(PortfolioTransaction.trade_date.asc(), PortfolioTransaction.id.asc())
        )
    )
    if not transactions:
        return None
    total_amount = sum((Decimal(item.amount) for item in transactions), Decimal("0"))
    total_fee = sum((Decimal(item.fee or 0) for item in transactions), Decimal("0"))
    total_share = sum((Decimal(item.share) for item in transactions), Decimal("0"))
    cost_nav = (total_amount + total_fee) / total_share if total_share else None
    position = db.scalar(select(PortfolioPosition).where(PortfolioPosition.fund_code == fund_code))
    values = {
        "holding_amount": _quantize(total_amount + total_fee, "0.0001"),
        "holding_share": _quantize(total_share, "0.0001"),
        "cost_nav": _quantize(cost_nav, "0.000001") if cost_nav else None,
        "buy_date": transactions[0].trade_date,
        "note": AUTO_SUMMARY_NOTE,
    }
    if position:
        for key, value in values.items():
            setattr(position, key, value)
    else:
        position = PortfolioPosition(fund_code=fund_code, **values)
        db.add(position)
    db.commit()
    db.refresh(position)
    return position


def create_transaction(db: Session, data: dict) -> PortfolioTransaction:
    fund_code = data["fund_code"].zfill(6)
    amount = Decimal(data["amount"])
    nav = Decimal(data["nav"])
    fee = Decimal(data.get("fee") or 0)
    if amount <= 0 or nav <= 0:
        raise ValueError("amount and nav must be positive")
    share = Decimal(data.get("share") or 0)
    if share <= 0:
        share = amount / nav
    transaction = PortfolioTransaction(
        fund_code=fund_code,
        trade_date=data["trade_date"],
        trade_type=data.get("trade_type") or "buy",
        amount=_quantize(amount, "0.0001"),
        nav=_quantize(nav, "0.000001"),
        share=_quantize(share, "0.0001"),
        fee=_quantize(fee, "0.0001"),
        note=data.get("note"),
    )
    db.add(transaction)
    db.commit()
    db.refresh(transaction)
    _rebuild_position_from_transactions(db, fund_code)
    return transaction


def list_transactions(db: Session, fund_code: str | None = None) -> list[PortfolioTransaction]:
    stmt = select(PortfolioTransaction).order_by(PortfolioTransaction.trade_date.desc(), PortfolioTransaction.id.desc())
    if fund_code:
        stmt = stmt.where(PortfolioTransaction.fund_code == fund_code.zfill(6))
    return list(db.scalars(stmt))


def delete_transaction(db: Session, transaction_id: int) -> bool:
    transaction = db.get(PortfolioTransaction, transaction_id)
    if not transaction:
        return False
    fund_code = transaction.fund_code
    db.delete(transaction)
    db.commit()
    rebuilt = _rebuild_position_from_transactions(db, fund_code)
    if rebuilt is None:
        position = db.scalar(select(PortfolioPosition).where(PortfolioPosition.fund_code == fund_code))
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


def position_summary(db: Session, position: PortfolioPosition) -> dict:
    nav = latest_nav(db, position.fund_code)
    latest = nav.unit_nav if nav else None
    fund_info = db.scalar(select(FundInfo).where(FundInfo.fund_code == position.fund_code))
    fund_name = fund_info.fund_name if fund_info else None
    if latest is None or position.holding_share is None:
        return {
            "position": position,
            "fund_name": fund_name,
            "latest_nav": latest,
            "current_value": None,
            "profit_amount": None,
            "profit_rate": None,
        }
    current_value = Decimal(position.holding_share) * Decimal(latest)
    cost = position.holding_amount
    if cost is None and position.cost_nav is not None:
        cost = Decimal(position.holding_share) * Decimal(position.cost_nav)
    profit = current_value - cost if cost is not None else None
    return {
        "position": position,
        "fund_name": fund_name,
        "latest_nav": latest,
        "current_value": current_value,
        "profit_amount": profit,
        "profit_rate": profit / cost if profit is not None and cost else None,
    }


def portfolio_overview(db: Session) -> dict:
    summaries = [position_summary(db, item) for item in list_positions(db)]
    total_value = sum((item["current_value"] or Decimal("0")) for item in summaries)
    total_cost = Decimal("0")
    for summary in summaries:
        position = summary["position"]
        if position.holding_amount is not None:
            total_cost += Decimal(position.holding_amount)
        elif position.holding_share is not None and position.cost_nav is not None:
            total_cost += Decimal(position.holding_share) * Decimal(position.cost_nav)
    profit_amount = total_value - total_cost if total_cost else None
    max_weight = None
    if total_value:
        weights = [(summary["current_value"] or Decimal("0")) / total_value for summary in summaries]
        max_weight = max(weights) if weights else None
    return {
        "total_value": total_value,
        "total_cost": total_cost if total_cost else None,
        "profit_amount": profit_amount,
        "profit_rate": profit_amount / total_cost if profit_amount is not None and total_cost else None,
        "max_weight": max_weight,
        "drawdown_1m": portfolio_drawdown_1m(db),
        "positions": summaries,
    }


def portfolio_drawdown_1m(db: Session) -> Decimal | None:
    positions = [item for item in list_positions(db) if item.holding_share is not None]
    if not positions:
        return None
    shares = {item.fund_code: Decimal(item.holding_share) for item in positions}
    rows = db.scalars(
        select(FundNav)
        .where(FundNav.fund_code.in_(shares.keys()), FundNav.unit_nav.is_not(None))
        .order_by(FundNav.nav_date.asc())
    ).all()
    if not rows:
        return None
    df = pd.DataFrame(
        [
            {
                "nav_date": row.nav_date,
                "fund_code": row.fund_code,
                "value": float(Decimal(row.unit_nav) * shares[row.fund_code]),
            }
            for row in rows
        ]
    )
    daily_value = df.pivot_table(index="nav_date", columns="fund_code", values="value").sum(axis=1)
    one_month = daily_value.tail(30)
    if len(one_month) < 2:
        return None
    drawdown = one_month / one_month.cummax() - 1
    return Decimal(str(float(drawdown.min()))).quantize(Decimal("0.000001"))


def portfolio_diagnosis(db: Session) -> dict:
    overview = portfolio_overview(db)
    positions = overview["positions"]
    max_weight = overview["max_weight"]
    drawdown_1m = overview["drawdown_1m"]
    risk_items = []
    stale_positions = [item for item in positions if item["latest_nav"] is None]

    if max_weight is not None and max_weight >= Decimal("0.30"):
        risk_items.append(
            {
                "level": "medium",
                "title": "持仓集中度偏高",
                "description": f"单只基金估算占比达到 {max_weight:.2%}，建议重点观察该基金波动对组合的影响。",
            }
        )
    if drawdown_1m is not None and drawdown_1m <= Decimal("-0.08"):
        risk_items.append(
            {
                "level": "medium",
                "title": "组合近 1 月回撤较大",
                "description": f"组合近 1 月估算最大回撤为 {drawdown_1m:.2%}，建议结合市场环境复盘。",
            }
        )
    if stale_positions:
        risk_items.append(
            {
                "level": "low",
                "title": "部分持仓缺少最新净值",
                "description": f"{len(stale_positions)} 只持仓暂时无法估算最新市值，请先同步净值。",
            }
        )
    if not risk_items:
        risk_items.append(
            {
                "level": "info",
                "title": "暂无突出组合风险",
                "description": "当前组合未触发集中度、回撤或净值缺失规则，仍建议持续观察评分和预警变化。",
            }
        )

    return {
        "summary": {
            "position_count": len(positions),
            "total_value": overview["total_value"],
            "profit_rate": overview["profit_rate"],
            "max_weight": max_weight,
            "drawdown_1m": drawdown_1m,
        },
        "risk_items": risk_items,
        "observation": "组合诊断仅用于风险观察和复盘，不构成买入或卖出建议。",
    }
