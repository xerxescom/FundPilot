from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.watchlist import WatchlistCreate, WatchlistOut
from app.services import nav_service, watchlist_service

router = APIRouter()


@router.post("", response_model=WatchlistOut)
def add_watchlist(payload: WatchlistCreate, db: Session = Depends(get_db)):
    return watchlist_service.add_watchlist_item(
        db, payload.fund_code, payload.group_name, payload.note, payload.fund_name
    )


@router.get("", response_model=list[WatchlistOut])
def list_watchlist(db: Session = Depends(get_db)):
    return watchlist_service.list_watchlist_items(db)


@router.delete("/{fund_code}")
def remove_watchlist(fund_code: str, db: Session = Depends(get_db)):
    if not watchlist_service.remove_watchlist_item(db, fund_code):
        raise HTTPException(status_code=404, detail="Watchlist item not found")
    return {"detail": "removed"}


@router.post("/sync-nav")
def sync_watchlist_nav(db: Session = Depends(get_db)):
    return nav_service.sync_watchlist_nav(db)
