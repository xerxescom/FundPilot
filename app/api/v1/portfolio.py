from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.portfolio import PortfolioCreate, PortfolioOut, PortfolioSummary, PortfolioUpdate
from app.services import portfolio_service

router = APIRouter()


@router.post("", response_model=PortfolioOut)
def create_position(payload: PortfolioCreate, db: Session = Depends(get_db)):
    return portfolio_service.create_position(db, payload.model_dump())


@router.get("", response_model=list[PortfolioOut])
def list_positions(db: Session = Depends(get_db)):
    return portfolio_service.list_positions(db)


@router.get("/summary", response_model=list[PortfolioSummary])
def list_position_summaries(db: Session = Depends(get_db)):
    return [portfolio_service.position_summary(db, item) for item in portfolio_service.list_positions(db)]


@router.put("/{position_id}", response_model=PortfolioOut)
def update_position(position_id: int, payload: PortfolioUpdate, db: Session = Depends(get_db)):
    position = portfolio_service.update_position(db, position_id, payload.model_dump(exclude_unset=True))
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")
    return position


@router.delete("/{position_id}")
def delete_position(position_id: int, db: Session = Depends(get_db)):
    if not portfolio_service.delete_position(db, position_id):
        raise HTTPException(status_code=404, detail="Position not found")
    return {"detail": "deleted"}
