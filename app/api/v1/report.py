from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.report import ReportOut
from app.services.ai import report_service
from app.services.ai.ollama_client import OllamaClient

router = APIRouter()


@router.post("/daily", response_model=ReportOut)
def generate_daily_report(db: Session = Depends(get_db)):
    return report_service.generate_daily_report(db)


@router.get("/latest", response_model=ReportOut)
def latest_report(db: Session = Depends(get_db)):
    report = report_service.latest_report(db)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


@router.get("/history", response_model=list[ReportOut])
def report_history(limit: int = 30, db: Session = Depends(get_db)):
    return report_service.report_history(db, limit=limit)


@router.get("/context/latest")
def latest_report_context(db: Session = Depends(get_db)):
    return report_service.latest_daily_context(db)


@router.get("/ollama/status")
def ollama_status():
    return OllamaClient().check_model_available()


@router.post("/fund/{fund_code}", response_model=ReportOut)
def generate_fund_report(fund_code: str, db: Session = Depends(get_db)):
    return report_service.generate_fund_explanation(db, fund_code)


@router.get("/fund/{fund_code}", response_model=ReportOut)
def latest_fund_report(fund_code: str, db: Session = Depends(get_db)):
    report = report_service.latest_fund_report(db, fund_code)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report
