"""Add daily task batch tables, trade calendar and report/idempotency links.

Revision ID: 0008_task_batch
Revises: 0007_task_result_json
Create Date: 2026-10-04
"""

from alembic import op
import sqlalchemy as sa


revision = "0008_task_batch"
down_revision = "0007_task_result_json"
branch_labels = None
depends_on = None


def _has_column(inspector, table_name: str, column_name: str) -> bool:
    return column_name in {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())

    if "task_batch" not in tables:
        op.create_table(
            "task_batch",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("batch_type", sa.String(length=50), nullable=False),
            sa.Column("idempotency_key", sa.String(length=120), nullable=False),
            sa.Column("status", sa.String(length=30), nullable=False),
            sa.Column("trade_date", sa.Date(), nullable=True),
            sa.Column("params_json", sa.JSON(), nullable=True),
            sa.Column("total_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("success_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("failure_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("skipped_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("pending_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("interrupted_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("coverage_json", sa.JSON(), nullable=True),
            sa.Column("lease_owner", sa.String(length=100), nullable=True),
            sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
            sa.Column("heartbeat_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("idempotency_key", name="uq_task_batch_idempotency_key"),
        )
        op.create_index(op.f("ix_task_batch_batch_type"), "task_batch", ["batch_type"])
        op.create_index(op.f("ix_task_batch_status"), "task_batch", ["status"])
        op.create_index(op.f("ix_task_batch_trade_date"), "task_batch", ["trade_date"])

    if "task_batch_item" not in tables:
        op.create_table(
            "task_batch_item",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column("batch_id", sa.Integer(), sa.ForeignKey("task_batch.id", ondelete="CASCADE"), nullable=False),
            sa.Column("step", sa.String(length=50), nullable=False),
            sa.Column("asset_type", sa.String(length=20), nullable=False, server_default=""),
            sa.Column("asset_code", sa.String(length=30), nullable=False, server_default=""),
            sa.Column("display_name", sa.String(length=255), nullable=True),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("error_class", sa.String(length=50), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("retry_count", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("max_retries", sa.Integer(), nullable=False, server_default="3"),
            sa.Column("idempotency_key", sa.String(length=200), nullable=False),
            sa.Column("result_json", sa.JSON(), nullable=True),
            sa.Column("lease_owner", sa.String(length=100), nullable=True),
            sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
            sa.Column("heartbeat_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
            sa.Column("started_at", sa.DateTime(), nullable=True),
            sa.Column("finished_at", sa.DateTime(), nullable=True),
            sa.UniqueConstraint("idempotency_key", name="uq_task_batch_item_idempotency_key"),
            sa.UniqueConstraint("batch_id", "step", "asset_type", "asset_code", name="uq_task_batch_item_key"),
        )
        op.create_index(op.f("ix_task_batch_item_batch_id"), "task_batch_item", ["batch_id"])
        op.create_index(op.f("ix_task_batch_item_step"), "task_batch_item", ["step"])
        op.create_index(op.f("ix_task_batch_item_status"), "task_batch_item", ["status"])
        op.create_index(op.f("ix_task_batch_item_asset_type"), "task_batch_item", ["asset_type"])
        op.create_index(op.f("ix_task_batch_item_asset_code"), "task_batch_item", ["asset_code"])

    if "trade_calendar" not in tables:
        op.create_table(
            "trade_calendar",
            sa.Column("trade_date", sa.Date(), primary_key=True),
            sa.Column("is_open", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("source", sa.String(length=50), nullable=True),
            sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        )

    if "task_run_log" in tables and not _has_column(inspector, "task_run_log", "batch_id"):
        op.add_column("task_run_log", sa.Column("batch_id", sa.Integer(), nullable=True))
        op.create_index(op.f("ix_task_run_log_batch_id"), "task_run_log", ["batch_id"])

    if "ai_report" in tables:
        if not _has_column(inspector, "ai_report", "batch_id"):
            op.add_column("ai_report", sa.Column("batch_id", sa.Integer(), nullable=True))
            op.create_index(op.f("ix_ai_report_batch_id"), "ai_report", ["batch_id"])
        if not _has_column(inspector, "ai_report", "trade_date"):
            op.add_column("ai_report", sa.Column("trade_date", sa.Date(), nullable=True))
            op.create_index(op.f("ix_ai_report_trade_date"), "ai_report", ["trade_date"])
        constraint_names = {item["name"] for item in inspector.get_unique_constraints("ai_report")}
        if "uq_ai_report_batch_daily" not in constraint_names:
            op.create_unique_constraint("uq_ai_report_batch_daily", "ai_report", ["report_type", "batch_id"])


def downgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    tables = set(inspector.get_table_names())
    if "task_batch_item" in tables:
        op.drop_table("task_batch_item")
    if "task_batch" in tables:
        op.drop_table("task_batch")
    if "trade_calendar" in tables:
        op.drop_table("trade_calendar")
    # The additive columns and the report uniqueness constraint deliberately remain on
    # downgrade, matching the 0006/0007 policy of avoiding destructive loss.
