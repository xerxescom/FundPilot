from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import correlation_service

router = APIRouter()


@router.get("/matrix")
def correlation_matrix(db: Session = Depends(get_db)):
    corr = correlation_service.calculate_correlation(db)
    if corr.empty:
        return {"matrix": {}, "name_map": {}}
    matrix = corr.round(4).to_dict()
    codes = list(corr.columns)
    name_map = correlation_service._build_name_map(db, codes)
    return {"matrix": matrix, "name_map": name_map}



@router.get("/pairs")
def high_correlation_pairs(db: Session = Depends(get_db)):
    return correlation_service.high_correlation_pairs(db)


@router.get("/returns")
def fund_return_series(fund_a: str, fund_b: str, limit: int = 180, db: Session = Depends(get_db)):
    fund_a = fund_a.zfill(6)
    fund_b = fund_b.zfill(6)
    if fund_a == fund_b:
        raise HTTPException(status_code=400, detail="Please provide two different fund codes")
    matrix = correlation_service.fund_return_matrix(db)
    if matrix.empty or fund_a not in matrix.columns or fund_b not in matrix.columns:
        return []
    pair = matrix[[fund_a, fund_b]].dropna().tail(limit).reset_index()
    return [
        {
            "nav_date": row["nav_date"],
            "fund_a": fund_a,
            "fund_b": fund_b,
            "return_a": float(row[fund_a]),
            "return_b": float(row[fund_b]),
        }
        for _, row in pair.iterrows()
    ]


@router.post("/alerts")
def generate_correlation_alerts(db: Session = Depends(get_db)):
    return correlation_service.generate_correlation_alerts(db)
