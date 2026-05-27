"""Add fund holding stock table.

Revision ID: 0005_fund_holding_stock
Revises: 0004_fund_holding_industry
Create Date: 2026-05-27
"""

from alembic import op
import sqlalchemy as sa

revision = "0005_fund_holding_stock"
down_revision = "0004_fund_holding_industry"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "fund_holding_stock" in inspector.get_table_names():
        return
    op.create_table(
        "fund_holding_stock",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fund_code", sa.String(length=20), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("stock_code", sa.String(length=30), nullable=False),
        sa.Column("stock_name", sa.String(length=100), nullable=False),
        sa.Column("industry", sa.String(length=100), nullable=True),
        sa.Column("weight", sa.Numeric(12, 6), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("fund_code", "report_date", "stock_code", name="uq_fund_holding_stock"),
    )
    op.create_index(op.f("ix_fund_holding_stock_fund_code"), "fund_holding_stock", ["fund_code"])
    op.create_index(op.f("ix_fund_holding_stock_report_date"), "fund_holding_stock", ["report_date"])
    op.create_index(op.f("ix_fund_holding_stock_stock_code"), "fund_holding_stock", ["stock_code"])
    op.create_index(op.f("ix_fund_holding_stock_industry"), "fund_holding_stock", ["industry"])


def downgrade() -> None:
    op.drop_index(op.f("ix_fund_holding_stock_industry"), table_name="fund_holding_stock")
    op.drop_index(op.f("ix_fund_holding_stock_stock_code"), table_name="fund_holding_stock")
    op.drop_index(op.f("ix_fund_holding_stock_report_date"), table_name="fund_holding_stock")
    op.drop_index(op.f("ix_fund_holding_stock_fund_code"), table_name="fund_holding_stock")
    op.drop_table("fund_holding_stock")
