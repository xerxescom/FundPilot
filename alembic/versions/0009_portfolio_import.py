"""Add portfolio cash events and CSV import batches with dedup columns.

Revision ID: 0009_portfolio_import
Revises: 0008_task_batch
Create Date: 2026-10-04
"""

from alembic import op
import sqlalchemy as sa


revision = "0009_portfolio_import"
down_revision = "0008_task_batch"
branch_labels = None
depends_on = None


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def _has_index(inspector, table_name: str, index_name: str) -> bool:
    return index_name in {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "portfolio_import_batch" not in tables:
        op.create_table(
            "portfolio_import_batch",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("source_kind", sa.String(length=30), nullable=False),
            sa.Column("file_name", sa.String(length=255), nullable=True),
            sa.Column("file_hash", sa.String(length=64), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False, server_default="previewed"),
            sa.Column("mapping_json", sa.JSON(), nullable=True),
            sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("imported_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("duplicate_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("error_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("notes_json", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("committed_at", sa.DateTime(), nullable=True),
        )
        op.create_index(op.f("ix_portfolio_import_batch_file_hash"), "portfolio_import_batch", ["file_hash"])
        op.create_index(op.f("ix_portfolio_import_batch_status"), "portfolio_import_batch", ["status"])

    if "portfolio_cash_event" not in tables:
        op.create_table(
            "portfolio_cash_event",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("event_date", sa.Date(), nullable=False),
            sa.Column("event_type", sa.String(length=20), nullable=False),
            sa.Column("amount", sa.Numeric(20, 4), nullable=False),
            sa.Column("asset_type", sa.String(length=20), nullable=True),
            sa.Column("asset_code", sa.String(length=30), nullable=True),
            sa.Column("note", sa.Text(), nullable=True),
            sa.Column("source", sa.String(length=20), nullable=False, server_default="manual"),
            sa.Column("external_ref", sa.String(length=120), nullable=True),
            sa.Column("import_batch_id", sa.Integer(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )
        op.create_index(op.f("ix_portfolio_cash_event_event_date"), "portfolio_cash_event", ["event_date"])
        op.create_index(op.f("ix_portfolio_cash_event_event_type"), "portfolio_cash_event", ["event_type"])
        op.create_index(op.f("ix_portfolio_cash_event_import_batch_id"), "portfolio_cash_event", ["import_batch_id"])
        op.create_index("ix_portfolio_cash_event_external_ref", "portfolio_cash_event", ["external_ref"], unique=True)

    if "portfolio_transaction" in tables:
        for column_name, column_type in (
            ("external_ref", sa.String(length=120)),
            ("source", sa.String(length=30)),
            ("import_batch_id", sa.Integer()),
            ("realized_pnl", sa.Numeric(20, 4)),
        ):
            if not _has_column(inspector, "portfolio_transaction", column_name):
                op.add_column("portfolio_transaction", sa.Column(column_name, column_type, nullable=True))
        if not _has_index(inspector, "portfolio_transaction", "ix_portfolio_transaction_import_batch_id"):
            op.create_index(
                op.f("ix_portfolio_transaction_import_batch_id"), "portfolio_transaction", ["import_batch_id"]
            )
        if not _has_index(inspector, "portfolio_transaction", "ix_portfolio_transaction_external_ref"):
            op.create_index(
                "ix_portfolio_transaction_external_ref", "portfolio_transaction", ["external_ref"], unique=True
            )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "portfolio_cash_event" in tables:
        op.drop_table("portfolio_cash_event")
    if "portfolio_import_batch" in tables:
        op.drop_table("portfolio_import_batch")
    # 与 0006/0007/0008 一致：新增列与索引在降级时保留，避免破坏性丢失。
