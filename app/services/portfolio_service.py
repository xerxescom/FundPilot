from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import PortfolioPosition
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
