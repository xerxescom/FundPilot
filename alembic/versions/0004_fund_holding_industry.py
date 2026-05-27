"""Add fund holding industry table.

Revision ID: 0004_fund_holding_industry
Revises: 0003_market_valuation
Create Date: 2026-05-27
"""

from alembic import op
import sqlalchemy as sa

revision = "0004_fund_holding_industry"
down_revision = "0003_market_valuation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "fund_holding_industry" in inspector.get_table_names():
        return
    op.create_table(
        "fund_holding_industry",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fund_code", sa.String(length=20), nullable=False),
        sa.Column("report_date", sa.Date(), nullable=False),
        sa.Column("industry", sa.String(length=100), nullable=False),
        sa.Column("weight", sa.Numeric(12, 6), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("fund_code", "report_date", "industry", name="uq_fund_holding_industry"),
    )
    op.create_index(op.f("ix_fund_holding_industry_fund_code"), "fund_holding_industry", ["fund_code"])
    op.create_index(op.f("ix_fund_holding_industry_report_date"), "fund_holding_industry", ["report_date"])
    op.create_index(op.f("ix_fund_holding_industry_industry"), "fund_holding_industry", ["industry"])


def downgrade() -> None:
    op.drop_index(op.f("ix_fund_holding_industry_industry"), table_name="fund_holding_industry")
    op.drop_index(op.f("ix_fund_holding_industry_report_date"), table_name="fund_holding_industry")
    op.drop_index(op.f("ix_fund_holding_industry_fund_code"), table_name="fund_holding_industry")
    op.drop_table("fund_holding_industry")
