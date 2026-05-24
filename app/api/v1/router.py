from fastapi import APIRouter

from app.api.v1 import alert, data, fund, market, portfolio, report, score, task, watchlist

api_router = APIRouter()
api_router.include_router(fund.router, prefix="/funds", tags=["funds"])
api_router.include_router(watchlist.router, prefix="/watchlist", tags=["watchlist"])
api_router.include_router(portfolio.router, prefix="/portfolio", tags=["portfolio"])
api_router.include_router(alert.router, prefix="/alerts", tags=["alerts"])
api_router.include_router(market.router, prefix="/market", tags=["market"])
api_router.include_router(report.router, prefix="/reports", tags=["reports"])
api_router.include_router(data.router, prefix="/data", tags=["data"])
api_router.include_router(score.router, prefix="/scores", tags=["scores"])
api_router.include_router(task.router, prefix="/tasks", tags=["tasks"])
api_router.include_router(fund.recommendation_router, prefix="/recommendations", tags=["recommendations"])
