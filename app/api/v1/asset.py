from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.asset import AssetOut, AssetPriceOut, AssetSyncOut, ListedAssetSyncIn
from app.services import asset_service


router = APIRouter()


@router.get("", response_model=list[AssetOut])
def list_assets(asset_type: str | None = None, db: Session = Depends(get_db)):
    return asset_service.list_assets(db, asset_type)


@router.get("/{asset_code}", response_model=AssetOut)
def get_asset(asset_code: str, db: Session = Depends(get_db)):
    asset = asset_service.get_asset(db, asset_code)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset


@router.get("/{asset_code}/prices", response_model=list[AssetPriceOut])
def get_prices(asset_code: str, db: Session = Depends(get_db)):
    return asset_service.price_history(db, asset_code)


@router.post("/{asset_code}/sync", response_model=AssetSyncOut)
def sync_listed_asset(asset_code: str, payload: ListedAssetSyncIn, db: Session = Depends(get_db)):
    try:
        return asset_service.sync_listed_asset(db, asset_code, payload.asset_type)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
