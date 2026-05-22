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
    from app.db.models import alert, ai_report, fund, indicator, portfolio, score, watchlist  # noqa: F401

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
    if "fund_name" in columns:
        return

    with engine.begin() as conn:
        if engine.dialect.name == "postgresql":
            conn.execute(text("ALTER TABLE watchlist ADD COLUMN fund_name VARCHAR(255)"))
        elif engine.dialect.name == "sqlite":
            conn.execute(text("ALTER TABLE watchlist ADD COLUMN fund_name VARCHAR(255)"))
