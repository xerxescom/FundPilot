"""Historical compatibility marker for legacy additive schema changes.

Some existing FundPilot databases were created while this revision existed
locally but before it was committed to the repository.  Those databases have
already applied the additive columns (watchlist names/industries, AI report
metadata and alert status).  Keeping this marker restores the migration graph
without attempting to reapply destructive changes.

Revision ID: 0002_schema_additive_columns
Revises: 0001_initial_schema
Create Date: 2026-05-24
"""


revision = "0002_schema_additive_columns"
down_revision = "0001_initial_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # This revision is intentionally a no-op. The columns were created in the
    # historical local migration that databases at this revision already ran.
    return None


def downgrade() -> None:
    return None
