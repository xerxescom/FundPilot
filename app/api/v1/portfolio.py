from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.schemas.portfolio import (
    PortfolioCreate,
    PortfolioBuySimulationIn,
    HoldingScreenshotImportIn,
    HoldingScreenshotImportOut,
    HoldingScreenshotRecognitionOut,
    PortfolioOut,
    PortfolioOverview,
    PortfolioSummary,
    PortfolioTransactionCreate,
    PortfolioTransactionOut,
    PortfolioUpdate,
)
from app.services import correlation_service, portfolio_service
from app.services.ai.qwen_vision_client import QwenVisionClient

router = APIRouter()


@router.post("/screenshot/recognize", response_model=HoldingScreenshotRecognitionOut)
async def recognize_holding_screenshot(file: UploadFile = File(...)):
    content_type = file.content_type or ""
    try:
        image_bytes = await file.read()
        client = QwenVisionClient()
        holdings = client.recognize_holdings(image_bytes, content_type)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        status_code = 503 if "API key is not configured" in str(exc) else 502
        raise HTTPException(status_code=status_code, detail=str(exc)) from exc
    finally:
        await file.close()
    return HoldingScreenshotRecognitionOut(
        provider=client.provider,
        model=client.model_name,
        holdings=holdings,
        warning="识别结果仅为草稿，请核对代码、数量和成本后再确认导入。原图不会保存到数据库。",
    )


@router.post("/screenshot/import", response_model=HoldingScreenshotImportOut)
def import_holding_screenshot(payload: HoldingScreenshotImportIn, db: Session = Depends(get_db)):
    return portfolio_service.import_screenshot_holdings(db, payload.holdings, payload.as_of_date)


@router.post("", response_model=PortfolioOut)
def create_position(payload: PortfolioCreate, db: Session = Depends(get_db)):
    return portfolio_service.create_position(db, payload.model_dump())


@router.post("/transactions", response_model=PortfolioTransactionOut)
def create_transaction(payload: PortfolioTransactionCreate, db: Session = Depends(get_db)):
    try:
        return portfolio_service.create_transaction(db, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/transactions", response_model=list[PortfolioTransactionOut])
def list_transactions(
    fund_code: str | None = None, asset_code: str | None = None, db: Session = Depends(get_db)
):
    return portfolio_service.list_transactions(db, fund_code, asset_code)


@router.delete("/transactions/{transaction_id}")
def delete_transaction(transaction_id: int, db: Session = Depends(get_db)):
    if not portfolio_service.delete_transaction(db, transaction_id):
        raise HTTPException(status_code=404, detail="Transaction not found")
    return {"detail": "deleted"}


@router.get("", response_model=list[PortfolioOut])
def list_positions(db: Session = Depends(get_db)):
    return portfolio_service.list_positions(db)


@router.get("/summary", response_model=list[PortfolioSummary])
def list_position_summaries(db: Session = Depends(get_db)):
    return [portfolio_service.position_summary(db, item) for item in portfolio_service.list_positions(db)]


@router.get("/overview", response_model=PortfolioOverview)
def portfolio_overview(db: Session = Depends(get_db)):
    return portfolio_service.portfolio_overview(db)


@router.get("/diagnosis")
def portfolio_diagnosis(db: Session = Depends(get_db)):
    return portfolio_service.portfolio_diagnosis(db)


@router.post("/simulate-buy")
def simulate_buy(payload: PortfolioBuySimulationIn, db: Session = Depends(get_db)):
    try:
        return portfolio_service.simulate_buy(db, payload.fund_code, payload.amount)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/correlation")
def portfolio_correlation(db: Session = Depends(get_db)):
    corr = correlation_service.calculate_correlation(db)
    return {} if corr.empty else corr.round(4).to_dict()


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
