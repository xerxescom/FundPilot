"""Add structured task result payload.

Revision ID: 0007_task_result_json
Revises: 0006_unified_assets
Create Date: 2026-10-04
"""

from alembic import op
import sqlalchemy as sa


revision = "0007_task_result_json"
down_revision = "0006_unified_assets"
branch_labels = None
depends_on = None


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "task_run_log" not in set(inspector.get_table_names()):
        return
    if not _has_column(inspector, "task_run_log", "result_json"):
        op.add_column("task_run_log", sa.Column("result_json", sa.JSON(), nullable=True))


def downgrade() -> None:
    # The added column deliberately remains on downgrade to avoid destructive loss of task results.
    return None
