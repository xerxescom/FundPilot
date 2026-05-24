from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.market import MarketContextOut
from app.services import market_service

router = APIRouter()


@router.get("/context", response_model=list[MarketContextOut])
def get_market_context(db: Session = Depends(get_db)):
    return market_service.latest_market_context(db)


@router.post("/sync")
def sync_market_context(db: Session = Depends(get_db)):
    return market_service.sync_market_context(db)
