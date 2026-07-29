"""Add agent_trace and trace_event tables

Revision ID: 5ae716ad749d
Revises: bf40dc9e653e
Create Date: 2026-07-29 20:12:37.901152

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '5ae716ad749d'
down_revision: Union[str, Sequence[str], None] = 'bf40dc9e653e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_trace",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trace_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("task_id", sa.Integer(), nullable=True),
        sa.Column("agent_name", sa.String(), nullable=False, server_default=sa.text("''")),
        sa.Column("goal", sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'completed'")),
        sa.Column("headers_json", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("trace_id", name="uq_agent_trace_trace_id"),
    )
    op.create_index("ix_agent_trace_trace_id", "agent_trace", ["trace_id"])
    op.create_index("ix_agent_trace_user_id", "agent_trace", ["user_id"])
    op.create_index("ix_agent_trace_task_id", "agent_trace", ["task_id"])
    op.create_index("ix_agent_trace_status", "agent_trace", ["status"])
    op.create_index(
        "ix_agent_trace_started_at_trace_id",
        "agent_trace",
        ["started_at", "trace_id"],
    )
    op.create_table(
        "trace_event",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("trace_id", sa.String(), nullable=False),
        sa.Column("step_index", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("step_label", sa.String(), nullable=False, server_default=sa.text("''")),
        sa.Column("agent_name", sa.String(), nullable=False, server_default=sa.text("''")),
        sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'completed'")),
        sa.Column("step_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["trace_id"],
            ["agent_trace.trace_id"],
            name="fk_trace_event_trace_id_agent_trace",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_trace_event_trace_id_step_index",
        "trace_event",
        ["trace_id", "step_index"],
    )


def downgrade() -> None:
    op.drop_index("ix_trace_event_trace_id_step_index", table_name="trace_event")
    op.drop_table("trace_event")
    op.drop_index("ix_agent_trace_started_at_trace_id", table_name="agent_trace")
    op.drop_index("ix_agent_trace_status", table_name="agent_trace")
    op.drop_index("ix_agent_trace_task_id", table_name="agent_trace")
    op.drop_index("ix_agent_trace_user_id", table_name="agent_trace")
    op.drop_index("ix_agent_trace_trace_id", table_name="agent_trace")
    op.drop_table("agent_trace")
