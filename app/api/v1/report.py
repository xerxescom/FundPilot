from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.report import ReportOut
from app.services.ai import report_service

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


@router.post("/fund/{fund_code}", response_model=ReportOut)
def generate_fund_report(fund_code: str, db: Session = Depends(get_db)):
    return report_service.generate_fund_explanation(db, fund_code)


@router.get("/fund/{fund_code}", response_model=ReportOut)
def latest_fund_report(fund_code: str, db: Session = Depends(get_db)):
    report = report_service.latest_fund_report(db, fund_code)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report
