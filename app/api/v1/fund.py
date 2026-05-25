from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import FundInfo
from app.db.session import get_db
from app.schemas.fund import FundInfoOut, FundNavOut
from app.schemas.indicator import IndicatorOut
from app.schemas.score import ScoreOut
from app.services import fund_analysis_service, indicator_service, nav_service, research_service, score_service

router = APIRouter()
recommendation_router = APIRouter()


@router.get("/compare")
def compare_funds(codes: str = Query(..., min_length=1), db: Session = Depends(get_db)):
    code_list = [code.strip() for code in codes.split(",") if code.strip()]
    if len(code_list) < 2 or len(code_list) > 5:
        raise HTTPException(status_code=400, detail="Please provide 2-5 fund codes")
    return research_service.compare_funds(db, code_list)


@router.get("/{fund_code}", response_model=FundInfoOut)
def get_fund(fund_code: str, db: Session = Depends(get_db)):
    fund = db.scalar(select(FundInfo).where(FundInfo.fund_code == fund_code.zfill(6)))
    if not fund:
        raise HTTPException(status_code=404, detail="Fund not found")
    return fund


@router.get("/{fund_code}/nav", response_model=list[FundNavOut])
def get_nav(fund_code: str, db: Session = Depends(get_db)):
    return nav_service.list_fund_nav(db, fund_code)


@router.post("/{fund_code}/sync-nav")
def sync_nav(fund_code: str, db: Session = Depends(get_db)):
    return nav_service.sync_fund_nav_detailed(db, fund_code)


@router.post("/{fund_code}/retry-sync")
def retry_sync_nav(fund_code: str, db: Session = Depends(get_db)):
    result = nav_service.sync_fund_nav_detailed(db, fund_code)
    result["status"] = "success"
    return result


@router.get("/{fund_code}/analysis-status")
def get_analysis_status(fund_code: str, db: Session = Depends(get_db)):
    return fund_analysis_service.analysis_status(db, fund_code)


@router.post("/{fund_code}/analyze")
def analyze_fund(
    fund_code: str,
    generate_report: bool = Query(default=False, description="是否同步生成耗时的基金 AI 解释"),
    db: Session = Depends(get_db),
):
    return fund_analysis_service.analyze_fund(db, fund_code, generate_report=generate_report)


@router.post("/{fund_code}/calc-indicators", response_model=IndicatorOut)
def calc_indicators(fund_code: str, db: Session = Depends(get_db)):
    return indicator_service.calculate_and_save_indicators(db, fund_code)


@router.get("/{fund_code}/indicators", response_model=IndicatorOut)
def get_indicators(fund_code: str, db: Session = Depends(get_db)):
    indicator = indicator_service.latest_indicator(db, fund_code)
    if not indicator:
        raise HTTPException(status_code=404, detail="Indicator not found")
    return indicator


@router.post("/{fund_code}/calc-score", response_model=ScoreOut)
def calc_score(fund_code: str, db: Session = Depends(get_db)):
    return score_service.calculate_and_save_score(db, fund_code)


@router.get("/{fund_code}/score", response_model=ScoreOut)
def get_score(fund_code: str, db: Session = Depends(get_db)):
    score = score_service.latest_score(db, fund_code)
    if not score:
        raise HTTPException(status_code=404, detail="Score not found")
    return score


@recommendation_router.get("/top", response_model=list[ScoreOut])
def recommendations_top(limit: int = Query(default=20, ge=1, le=100), db: Session = Depends(get_db)):
    return score_service.top_scores(db, limit=limit)
