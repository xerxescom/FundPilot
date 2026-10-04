import json
from datetime import date

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import PortfolioImportBatch
from app.db.session import get_db
from app.schemas.portfolio import (
    CashEventCreateIn,
    CashEventOut,
    ImportBatchDetailOut,
    ImportBatchOut,
    ImportCommitIn,
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
from app.services import account_service, correlation_service, csv_import_service, portfolio_service
from app.services.ai.qwen_vision_client import QwenVisionClient

router = APIRouter()


def _serialize_cash_event(event) -> dict:
    return {
        "id": event.id,
        "event_date": event.event_date,
        "event_type": event.event_type,
        "event_type_label": account_service.CASH_EVENT_LABELS.get(event.event_type, event.event_type),
        "amount": event.amount,
        "asset_type": event.asset_type,
        "asset_code": event.asset_code,
        "note": event.note,
        "source": event.source,
        "external_ref": event.external_ref,
        "import_batch_id": event.import_batch_id,
        "created_at": event.created_at,
    }


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
    try:
        deleted = portfolio_service.delete_transaction(db, transaction_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not deleted:
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
    try:
        position = portfolio_service.update_position(db, position_id, payload.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if not position:
        raise HTTPException(status_code=404, detail="Position not found")
    return position


@router.delete("/{position_id}")
def delete_position(position_id: int, db: Session = Depends(get_db)):
    if not portfolio_service.delete_position(db, position_id):
        raise HTTPException(status_code=404, detail="Position not found")
    return {"detail": "deleted"}


# ---------------------------------------------------------------- CSV 导入


@router.post("/imports/preview")
async def preview_portfolio_import(
    file: UploadFile = File(...),
    source_kind: str | None = Form(default=None),
    mapping_json: str | None = Form(default=None),
    header_row: int | None = Form(default=None),
    default_asset_type: str = Form(default="auto"),
    db: Session = Depends(get_db),
):
    content = await file.read()
    try:
        await file.close()
        override = json.loads(mapping_json) if mapping_json else None
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail=f"mapping_json 不是合法 JSON：{exc}") from exc
    try:
        return csv_import_service.preview_import(
            db,
            file_name=file.filename or "upload.csv",
            content=content,
            source_kind=source_kind or None,
            mapping_override=override,
            header_row=header_row,
            default_asset_type=default_asset_type,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/imports/commit")
def commit_portfolio_import(payload: ImportCommitIn, db: Session = Depends(get_db)):
    try:
        return csv_import_service.commit_import(
            db, batch_id=payload.batch_id, rows=[row.model_dump() for row in payload.rows]
        )
    except ValueError as exc:
        detail = str(exc)
        status = 409 if "已入账" in detail else 404 if "不存在" in detail else 400
        raise HTTPException(status_code=status, detail=detail) from exc


@router.get("/imports", response_model=list[ImportBatchOut])
def list_portfolio_imports(limit: int = Query(default=20, ge=1, le=100), db: Session = Depends(get_db)):
    return list(
        db.scalars(
            select(PortfolioImportBatch)
            .order_by(PortfolioImportBatch.created_at.desc(), PortfolioImportBatch.id.desc())
            .limit(limit)
        )
    )


@router.get("/imports/{batch_id}", response_model=ImportBatchDetailOut)
def get_portfolio_import(batch_id: int, db: Session = Depends(get_db)):
    batch = db.get(PortfolioImportBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="Import batch not found")
    return batch


# ---------------------------------------------------------------- 现金事件


@router.get("/cash-events", response_model=list[CashEventOut])
def list_cash_events(
    start: date | None = None,
    end: date | None = None,
    limit: int = Query(default=500, ge=1, le=2000),
    db: Session = Depends(get_db),
):
    return [
        _serialize_cash_event(event)
        for event in account_service.list_cash_events(db, start=start, end=end, limit=limit)
    ]


@router.post("/cash-events", response_model=CashEventOut)
def create_cash_event(payload: CashEventCreateIn, db: Session = Depends(get_db)):
    try:
        event = account_service.create_cash_event(db, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _serialize_cash_event(event)


@router.delete("/cash-events/{event_id}")
def delete_cash_event(event_id: int, db: Session = Depends(get_db)):
    if not account_service.delete_cash_event(db, event_id):
        raise HTTPException(status_code=404, detail="Cash event not found")
    return {"detail": "deleted"}


# ---------------------------------------------------------------- 账户口径


@router.get("/account/summary")
def account_summary(db: Session = Depends(get_db)):
    return account_service.account_summary(db)


@router.get("/account/performance")
def account_performance(
    start: date | None = None, end: date | None = None, db: Session = Depends(get_db)
):
    return account_service.account_performance(db, start=start, end=end)
