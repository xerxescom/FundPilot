from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.task import TaskLogOut
from app.services.task_log_service import latest_task_logs

router = APIRouter()


@router.get("/logs", response_model=list[TaskLogOut])
def task_logs(limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db)):
    return latest_task_logs(db, limit=limit)
