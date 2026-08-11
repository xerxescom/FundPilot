"""Add unified asset metadata and price history.

Revision ID: 0006_unified_assets
Revises: 0005_fund_holding_stock
Create Date: 2026-08-11
"""

from alembic import op
import sqlalchemy as sa


revision = "0006_unified_assets"
down_revision = "0005_fund_holding_stock"
branch_labels = None
depends_on = None


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "asset_info" not in tables:
        op.create_table(
            "asset_info",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("asset_code", sa.String(length=30), nullable=False),
            sa.Column("asset_type", sa.String(length=20), nullable=False),
            sa.Column("asset_name", sa.String(length=255), nullable=False),
            sa.Column("market", sa.String(length=50), nullable=True),
            sa.Column("currency", sa.String(length=10), nullable=False, server_default="CNY"),
            sa.Column("industry", sa.String(length=100), nullable=True),
            sa.Column("source", sa.String(length=50), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("asset_code"),
        )
        op.create_index(op.f("ix_asset_info_asset_code"), "asset_info", ["asset_code"])
        op.create_index(op.f("ix_asset_info_asset_type"), "asset_info", ["asset_type"])
        op.create_index(op.f("ix_asset_info_industry"), "asset_info", ["industry"])

    if "asset_price_daily" not in tables:
        op.create_table(
            "asset_price_daily",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("asset_code", sa.String(length=30), nullable=False),
            sa.Column("price_date", sa.Date(), nullable=False),
            sa.Column("close", sa.Numeric(20, 6), nullable=True),
            sa.Column("daily_return", sa.Numeric(12, 6), nullable=True),
            sa.Column("source", sa.String(length=50), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("asset_code", "price_date", name="uq_asset_price_code_date"),
        )
        op.create_index(op.f("ix_asset_price_daily_asset_code"), "asset_price_daily", ["asset_code"])
        op.create_index(op.f("ix_asset_price_daily_price_date"), "asset_price_daily", ["price_date"])

    for table_name in ("portfolio_position", "portfolio_transaction"):
        if table_name not in tables:
            continue
        if not _has_column(inspector, table_name, "asset_type"):
            op.add_column(table_name, sa.Column("asset_type", sa.String(length=20), nullable=True, server_default="fund"))
            op.create_index(op.f(f"ix_{table_name}_asset_type"), table_name, ["asset_type"])
        if not _has_column(inspector, table_name, "asset_code"):
            op.add_column(table_name, sa.Column("asset_code", sa.String(length=30), nullable=True))
            op.create_index(op.f(f"ix_{table_name}_asset_code"), table_name, ["asset_code"])
        op.execute(sa.text(f"UPDATE {table_name} SET asset_type = 'fund' WHERE asset_type IS NULL"))
        op.execute(sa.text(f"UPDATE {table_name} SET asset_code = fund_code WHERE asset_code IS NULL"))


def downgrade() -> None:
    op.drop_table("asset_price_daily")
    op.drop_table("asset_info")
    # The added portfolio columns deliberately remain on downgrade to avoid destructive loss of asset identity.
