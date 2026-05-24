from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import data_health_service

router = APIRouter()


@router.get("/health")
def data_health(db: Session = Depends(get_db)):
    return data_health_service.data_health_overview(db)
