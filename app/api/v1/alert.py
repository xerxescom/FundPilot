from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.alert import AlertOut, AlertUpdate
from app.services import alert_service

router = APIRouter()


@router.post("/generate", response_model=list[AlertOut])
def generate_alerts(db: Session = Depends(get_db)):
    return alert_service.generate_alerts(db)


@router.get("/unread", response_model=list[AlertOut])
def unread_alerts(db: Session = Depends(get_db)):
    return alert_service.unread_alerts(db)


@router.patch("/{alert_id}", response_model=AlertOut)
def update_alert(alert_id: int, payload: AlertUpdate, db: Session = Depends(get_db)):
    try:
        alert = alert_service.update_alert_status(db, alert_id, payload.status)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return alert
