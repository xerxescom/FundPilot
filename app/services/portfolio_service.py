from decimal import Decimal

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FundNav, PortfolioPosition
from app.services.nav_service import latest_nav


def create_position(db: Session, data: dict) -> PortfolioPosition:
    position = PortfolioPosition(**data)
    position.fund_code = position.fund_code.zfill(6)
    db.add(position)
    db.commit()
    db.refresh(position)
    return position


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
    if latest is None or position.holding_share is None:
        return {
            "position": position,
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
