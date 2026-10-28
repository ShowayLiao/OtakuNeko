"""Establish the immutable current business schema before historical increments.

Revision ID: a10300000001
Revises: None
"""

from alembic import op

from app.db.migration_compatibility import bootstrap_business_schema
from app.db.migration_snapshot import BUSINESS_TABLES, METADATA

revision = "a10300000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bootstrap_business_schema(op.get_bind())


def downgrade() -> None:
    # Explicit destructive downgrade to base: callers must back up first.
    for table in reversed(METADATA.sorted_tables):
        if table.name in BUSINESS_TABLES:
            table.drop(op.get_bind())
