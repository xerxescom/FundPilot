"""Add rollback bookkeeping columns to portfolio import batches.

Revision ID: 0010_import_batch_rollback
Revises: 0009_portfolio_import
Create Date: 2026-10-04
"""

from alembic import op
import sqlalchemy as sa


revision = "0010_import_batch_rollback"
down_revision = "0009_portfolio_import"
branch_labels = None
depends_on = None


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if "portfolio_import_batch" not in set(inspector.get_table_names()):
        # 0001 的 create_all 已按当前模型建表时无需处理；表缺失说明 0009 未跑过，加列也无从谈起。
        return
    for column_name, column_type in (
        ("rolled_back_at", sa.DateTime()),
        ("rollback_reason", sa.Text()),
    ):
        if not _has_column(inspector, "portfolio_import_batch", column_name):
            op.add_column(
                "portfolio_import_batch", sa.Column(column_name, column_type, nullable=True)
            )


def downgrade() -> None:
    # 与 0006/0007/0008 一致：新增列在降级时保留，避免破坏性丢失。
    return None
