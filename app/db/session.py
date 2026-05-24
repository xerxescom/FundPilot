from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import NullPool

from app.core.config import get_settings


def _build_engine():
    settings = get_settings()
    url = settings.database_url
    # SQLite does not support the connection pool parameters below;
    # use NullPool (no-op pool) for SQLite to keep tests simple.
    if url.startswith("sqlite"):
        return create_engine(url, pool_pre_ping=True, poolclass=NullPool)
    return create_engine(
        url,
        pool_pre_ping=True,   # 检测失效连接，避免"断管道"错误
        pool_size=10,          # 保持的基础连接数
        max_overflow=20,       # pool_size 耗尽后允许额外开启的连接数
        pool_timeout=30,       # 等待空闲连接的超时时间（秒）
        pool_recycle=3600,     # 强制回收连接，防止 TCP 长连接被防火墙/PostgreSQL 踢掉
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
    from app.db.models import (  # noqa: F401
        alert,
        ai_report,
        fund,
        indicator,
        market,
        portfolio,
        score,
        task_log,
        watchlist,
    )

    from app.db.base import Base

    Base.metadata.create_all(bind=engine)
    ensure_schema_compatibility()


def ensure_schema_compatibility() -> None:
    """Apply tiny compatibility fixes before formal migrations exist.

    The first project version uses `create_all()` instead of Alembic. That does
    not alter existing tables, so additive columns introduced during early
    development need a small bridge for local databases.
    """

    inspector = inspect(engine)
    if "watchlist" not in inspector.get_table_names():
        watchlist_columns = set()
    else:
        watchlist_columns = {column["name"] for column in inspector.get_columns("watchlist")}
    table_columns = {
        "watchlist": {
            "columns": watchlist_columns,
            "missing": {
                "fund_name": "VARCHAR(255)",
                "industry": "VARCHAR(100)",
            },
        },
        "ai_report": {
            "columns": {column["name"] for column in inspector.get_columns("ai_report")}
            if "ai_report" in inspector.get_table_names()
            else set(),
            "missing": {
                "is_fallback": "BOOLEAN DEFAULT FALSE",
                "fallback_reason": "TEXT",
                "input_snapshot": "TEXT",
            },
        },
    }

    with engine.begin() as conn:
        for table_name, config in table_columns.items():
            if table_name not in inspector.get_table_names():
                continue
            for column_name, column_type in config["missing"].items():
                if column_name in config["columns"]:
                    continue
                if engine.dialect.name in {"postgresql", "sqlite"}:
                    conn.execute(text(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_type}"))
