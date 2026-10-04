from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import get_settings


def _build_engine():
    settings = get_settings()
    url = settings.database_url
    if url.startswith("sqlite"):
        return create_engine(url, pool_pre_ping=True, poolclass=NullPool)
    return create_engine(
        url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=20,
        pool_timeout=30,
        pool_recycle=3600,
    )


engine = _build_engine()
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    settings = get_settings()
    if not settings.auto_create_tables:
        return

    from app.db.models import (  # noqa: F401
        alert,
        asset,
        ai_report,
        fund,
        indicator,
        market,
        portfolio,
        score,
        task_batch,
        task_log,
        trade_calendar,
        watchlist,
    )

    from app.db.base import Base

    Base.metadata.create_all(bind=engine)
    if settings.app_env == "dev":
        ensure_schema_compatibility()


def ensure_schema_compatibility() -> None:
    """Apply additive dev-only compatibility fixes for local databases."""

    inspector = inspect(engine)
    table_names = inspector.get_table_names()

    def columns_for(table_name: str) -> set[str]:
        if table_name not in table_names:
            return set()
        return {column["name"] for column in inspector.get_columns(table_name)}

    table_columns = {
        "watchlist": {
            "columns": columns_for("watchlist"),
            "missing": {
                "fund_name": "VARCHAR(255)",
                "industry": "VARCHAR(100)",
            },
        },
        "ai_report": {
            "columns": columns_for("ai_report"),
            "missing": {
                "is_fallback": "BOOLEAN DEFAULT FALSE",
                "fallback_reason": "TEXT",
                "input_snapshot": "TEXT",
                "batch_id": "INTEGER",
                "trade_date": "DATE",
            },
        },
        "alert_event": {
            "columns": columns_for("alert_event"),
            "missing": {
                "status": "VARCHAR(20) DEFAULT 'unread'",
            },
        },
        "portfolio_position": {
            "columns": columns_for("portfolio_position"),
            "missing": {
                "asset_type": "VARCHAR(20) DEFAULT 'fund'",
                "asset_code": "VARCHAR(30)",
            },
        },
        "portfolio_transaction": {
            "columns": columns_for("portfolio_transaction"),
            "missing": {
                "asset_type": "VARCHAR(20) DEFAULT 'fund'",
                "asset_code": "VARCHAR(30)",
                "external_ref": "VARCHAR(120)",
                "source": "VARCHAR(30)",
                "import_batch_id": "INTEGER",
                "realized_pnl": "NUMERIC(20, 4)",
            },
        },
        "task_run_log": {
            "columns": columns_for("task_run_log"),
            "missing": {
                "result_json": "JSON",
                "batch_id": "INTEGER",
            },
        },
    }

    # 唯一索引无法通过 ALTER TABLE 添加，单独补建（SQLite/PostgreSQL 都支持 IF NOT EXISTS）
    compat_indexes = (
        "CREATE UNIQUE INDEX IF NOT EXISTS ix_portfolio_transaction_external_ref "
        "ON portfolio_transaction (external_ref)",
    )

    with engine.begin() as conn:
        for table_name, config in table_columns.items():
            if table_name not in table_names:
                continue
            for column_name, column_type in config["missing"].items():
                if column_name in config["columns"]:
                    continue
                if engine.dialect.name in {"postgresql", "sqlite"}:
                    conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))
        if "portfolio_transaction" in table_names and engine.dialect.name in {"postgresql", "sqlite"}:
            for statement in compat_indexes:
                conn.execute(text(statement))
