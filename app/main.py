from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

from apscheduler.schedulers.background import BackgroundScheduler
from fastapi import FastAPI, HTTPException, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.core.metrics import PrometheusMiddleware, get_registry
from app.db.session import engine, init_db
from app.jobs.scheduler import create_scheduler

configure_logging()
settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    scheduler: BackgroundScheduler | None = None
    if settings.enable_scheduler:
        scheduler = create_scheduler()
        scheduler.start()
        app.state.scheduler = scheduler
    try:
        yield
    finally:
        if scheduler and scheduler.running:
            scheduler.shutdown(wait=False)


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.add_middleware(PrometheusMiddleware)


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    """Prometheus 指标；仅本机可达，不经过 nginx 反向代理。"""
    return Response(content=generate_latest(get_registry()), media_type=CONTENT_TYPE_LATEST)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env}


@app.get("/livez")
def livez() -> dict[str, str]:
    """存活探针：只证明进程能响应，不触碰数据库。"""
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env}


@lru_cache
def _migration_head() -> str | None:
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
        return ScriptDirectory.from_config(config).get_current_head()
    except Exception:  # noqa: BLE001 - 读不到迁移脚本时降级为只检查数据库连通性
        return None


@app.get("/readyz")
def readyz() -> dict[str, str]:
    """就绪探针：数据库可连接且迁移已到 head，否则 503。"""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            revision = conn.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except Exception as exc:  # noqa: BLE001 - 任何数据库异常都视为未就绪
        raise HTTPException(status_code=503, detail=f"数据库未就绪：{exc}") from exc
    head = _migration_head()
    if head and revision != head:
        raise HTTPException(
            status_code=503, detail=f"数据库迁移未完成：当前 {revision}，期望 {head}，请执行 alembic upgrade head"
        )
    return {"status": "ready", "revision": revision or "", "head": head or ""}


app.include_router(api_router, prefix="/api/v1")
