from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.task import TaskLogOut
from app.services.task_log_service import latest_task_logs
from app.services.task_runner_service import available_tasks, enqueue_task, run_queued_task, run_task

router = APIRouter()


@router.get("/logs", response_model=list[TaskLogOut])
def task_logs(limit: int = Query(default=50, ge=1, le=200), db: Session = Depends(get_db)):
    return latest_task_logs(db, limit=limit)


@router.get("/available")
def list_tasks():
    return available_tasks()


@router.post("/run/{task_name}")
def run_named_task(task_name: str, db: Session = Depends(get_db)):
    try:
        return run_task(db, task_name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/enqueue/{task_name}", response_model=TaskLogOut)
def enqueue_named_task(
    task_name: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    try:
        log = enqueue_task(db, task_name)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    background_tasks.add_task(run_queued_task, log.id, task_name)
    return log
