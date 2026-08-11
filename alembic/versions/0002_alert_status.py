"""Add alert status.

Revision ID: 0002_alert_status
Revises: 0002_schema_additive_columns
Create Date: 2026-05-25
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_alert_status"
down_revision = "0002_schema_additive_columns"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "status" in {column["name"] for column in inspector.get_columns("alert_event")}:
        return
    op.add_column(
        "alert_event",
        sa.Column("status", sa.String(length=20), server_default="unread", nullable=False),
    )
    op.create_index(op.f("ix_alert_event_status"), "alert_event", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_alert_event_status"), table_name="alert_event")
    op.drop_column("alert_event", "status")
