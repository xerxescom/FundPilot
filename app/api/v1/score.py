from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import research_service, score_service

router = APIRouter()


@router.get("/trend/{fund_code}")
def score_trend(fund_code: str, db: Session = Depends(get_db)):
    return research_service.score_trend(db, fund_code)


@router.get("/strategies")
def score_strategies():
    return score_service.available_strategies()


@router.get("/summary")
def score_signal_summary(db: Session = Depends(get_db)):
    return score_service.score_signal_summary(db)


@router.get("/top")
def top_scores_by_strategy(
    strategy: str = Query(default="default"),
    limit: int = Query(default=100, ge=1, le=200),
    db: Session = Depends(get_db),
):
    try:
        return score_service.top_scores_by_strategy(db, strategy=strategy, limit=limit)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
