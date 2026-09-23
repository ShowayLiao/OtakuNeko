"""Add agent_task_def and agent_task_run tables

Revision ID: bf40dc9e653e
Revises: 4b578619fc54
Create Date: 2026-07-29 17:26:24.174229

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = 'bf40dc9e653e'
down_revision: Union[str, Sequence[str], None] = '4b578619fc54'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_task_def",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("task_type", sa.String(), nullable=False),
        sa.Column("payload", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("schedule_expr", sa.String(), nullable=False),
        sa.Column("timezone", sa.String(), nullable=False, server_default=sa.text("'Asia/Shanghai'")),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("deleted_at", sa.DateTime(), nullable=True),
        sa.Column("next_run", sa.DateTime(), nullable=True),
        sa.Column("catch_up", sa.String(), nullable=False, server_default=sa.text("'latest'")),
        sa.Column("policy", sa.Text(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("idempotency_key", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "agent_task_run",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_def_id", sa.Integer(), sa.ForeignKey("agent_task_def.id"), nullable=False, index=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("scheduled_slot", sa.DateTime(), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("lease_id", sa.String(), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'pending'")),
        sa.Column("trace_id", sa.String(), nullable=True),
        sa.Column("error_category", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("task_def_id", "scheduled_slot", name="uq_agent_task_run_slot"),
    )
    op.create_index("ix_agent_task_def_idempotency_key", "agent_task_def", ["idempotency_key"])


def downgrade() -> None:
    op.drop_index("ix_agent_task_def_idempotency_key", table_name="agent_task_def")
    op.drop_table("agent_task_run")
    op.drop_table("agent_task_def")
