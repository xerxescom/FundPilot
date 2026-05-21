from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Watchlist


def add_watchlist_item(
    db: Session, fund_code: str, group_name: str = "default", note: str | None = None
) -> Watchlist:
    fund_code = fund_code.zfill(6)
    item = db.scalar(
        select(Watchlist).where(
            Watchlist.fund_code == fund_code,
            Watchlist.group_name == group_name,
        )
    )
    if item:
        item.is_active = True
        item.note = note
    else:
        item = Watchlist(fund_code=fund_code, group_name=group_name, note=note, is_active=True)
        db.add(item)
    db.commit()
    db.refresh(item)
    return item


def list_watchlist_items(db: Session, active_only: bool = True) -> list[Watchlist]:
    stmt = select(Watchlist).order_by(Watchlist.created_at.desc())
    if active_only:
        stmt = stmt.where(Watchlist.is_active.is_(True))
    return list(db.scalars(stmt))


def remove_watchlist_item(db: Session, fund_code: str, group_name: str = "default") -> bool:
    item = db.scalar(
        select(Watchlist).where(
            Watchlist.fund_code == fund_code.zfill(6),
            Watchlist.group_name == group_name,
            Watchlist.is_active.is_(True),
        )
    )
    if not item:
        return False
    item.is_active = False
    db.commit()
    return True
