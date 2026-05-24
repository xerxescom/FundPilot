from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import research_service

router = APIRouter()


@router.get("/industry-overview")
def industry_overview(db: Session = Depends(get_db)):
    return research_service.industry_overview(db)


@router.get("/risk-return")
def risk_return_points(db: Session = Depends(get_db)):
    return research_service.risk_return_points(db)
