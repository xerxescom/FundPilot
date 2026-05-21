from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.alert import AlertOut
from app.services import alert_service

router = APIRouter()


@router.post("/generate", response_model=list[AlertOut])
def generate_alerts(db: Session = Depends(get_db)):
    return alert_service.generate_alerts(db)


@router.get("/unread", response_model=list[AlertOut])
def unread_alerts(db: Session = Depends(get_db)):
    return alert_service.unread_alerts(db)
