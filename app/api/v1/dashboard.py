from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.services import alert_service, data_health_service, market_service, score_service, watchlist_service
from app.services.ai.report_service import latest_report

router = APIRouter()


@router.get("/overview")
def dashboard_overview(db: Session = Depends(get_db)):
    watchlist = watchlist_service.list_watchlist_items(db)
    scores = score_service.top_scores(db, limit=5)
    alerts = alert_service.unread_alerts(db)
    report = latest_report(db)
    market_context = market_service.latest_market_context(db)
    health = data_health_service.data_health_overview(db)
    fund_names = {item.fund_code: item.fund_name or item.fund_code for item in watchlist}
    return {
        "watchlist_count": len(watchlist),
        "top_scores": [
            {
                "fund_code": item.fund_code,
                "fund_name": fund_names.get(item.fund_code, item.fund_code),
                "total_score": float(item.total_score) if item.total_score is not None else None,
                "rating": item.rating,
                "reason": item.reason,
                "score_date": item.score_date,
            }
            for item in scores
        ],
        "unread_alerts": alerts,
        "latest_report": report,
        "market_context": market_context,
        "data_health": health,
    }
