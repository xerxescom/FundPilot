from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import research_service

router = APIRouter()


@router.get("/trend/{fund_code}")
def score_trend(fund_code: str, db: Session = Depends(get_db)):
    return research_service.score_trend(db, fund_code)
