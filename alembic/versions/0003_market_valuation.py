"""Add market valuation table.

Revision ID: 0003_market_valuation
Revises: 0002_alert_status
Create Date: 2026-05-26
"""

from alembic import op
import sqlalchemy as sa

revision = "0003_market_valuation"
down_revision = "0002_alert_status"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "market_valuation_daily" in inspector.get_table_names():
        return
    op.create_table(
        "market_valuation_daily",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("index_code", sa.String(length=30), nullable=False),
        sa.Column("index_name", sa.String(length=100), nullable=False),
        sa.Column("trade_date", sa.Date(), nullable=False),
        sa.Column("pe_ttm", sa.Numeric(12, 4), nullable=True),
        sa.Column("pe_percentile", sa.Numeric(8, 4), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("index_code", "trade_date", name="uq_market_valuation_date"),
    )
    op.create_index(op.f("ix_market_valuation_daily_index_code"), "market_valuation_daily", ["index_code"])
    op.create_index(op.f("ix_market_valuation_daily_trade_date"), "market_valuation_daily", ["trade_date"])


def downgrade() -> None:
    op.drop_index(op.f("ix_market_valuation_daily_trade_date"), table_name="market_valuation_daily")
    op.drop_index(op.f("ix_market_valuation_daily_index_code"), table_name="market_valuation_daily")
    op.drop_table("market_valuation_daily")
