from collections.abc import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

engine = create_engine(get_settings().database_url, pool_pre_ping=True)
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
        return

    columns = {column["name"] for column in inspector.get_columns("watchlist")}
    missing_columns = {
        "fund_name": "VARCHAR(255)",
        "industry": "VARCHAR(100)",
    }

    with engine.begin() as conn:
        for column_name, column_type in missing_columns.items():
            if column_name in columns:
                continue
            if engine.dialect.name in {"postgresql", "sqlite"}:
                conn.execute(text(f"ALTER TABLE watchlist ADD COLUMN {column_name} {column_type}"))
