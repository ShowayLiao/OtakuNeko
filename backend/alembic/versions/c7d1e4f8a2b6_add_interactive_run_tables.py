"""Add interactive Run, Invocation and Event tables."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c7d1e4f8a2b6"
down_revision: Union[str, Sequence[str], None] = "5ae716ad749d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_run",
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("thread_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("goal_hash", sa.String(), nullable=False),
        sa.Column("model", sa.String(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("run_id"),
    )
    op.create_index("ix_agent_run_user_id", "agent_run", ["user_id"])
    op.create_index("ix_agent_run_thread_id", "agent_run", ["thread_id"])
    op.create_index("ix_agent_run_status", "agent_run", ["status"])
    op.create_index("ix_agent_run_error_code", "agent_run", ["error_code"])
    op.create_index("ix_agent_run_created_at", "agent_run", ["created_at"])
    op.create_index(
        "ix_agent_run_status_created_at",
        "agent_run",
        ["status", "created_at"],
    )

    op.create_table(
        "agent_invocation",
        sa.Column("invocation_id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("capability", sa.String(), nullable=False),
        sa.Column("capability_version", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("input_hash", sa.String(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(
            ["run_id"], ["agent_run.run_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("invocation_id"),
        sa.UniqueConstraint(
            "run_id", "sequence", name="uq_agent_invocation_run_sequence"
        ),
        sa.UniqueConstraint(
            "run_id",
            "idempotency_key",
            name="uq_agent_invocation_run_idempotency_key",
        ),
    )
    op.create_index("ix_agent_invocation_run_id", "agent_invocation", ["run_id"])
    op.create_index("ix_agent_invocation_status", "agent_invocation", ["status"])
    op.create_index(
        "ix_agent_invocation_idempotency_key",
        "agent_invocation",
        ["idempotency_key"],
    )
    op.create_index(
        "ix_agent_invocation_run_sequence",
        "agent_invocation",
        ["run_id", "sequence"],
    )

    op.create_table(
        "agent_run_event",
        sa.Column("event_id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("invocation_id", sa.String(), nullable=True),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"], ["agent_run.run_id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("event_id"),
        sa.UniqueConstraint(
            "run_id", "sequence", name="uq_agent_run_event_run_sequence"
        ),
    )
    op.create_index("ix_agent_run_event_run_id", "agent_run_event", ["run_id"])
    op.create_index(
        "ix_agent_run_event_invocation_id",
        "agent_run_event",
        ["invocation_id"],
    )
    op.create_index(
        "ix_agent_run_event_occurred_at",
        "agent_run_event",
        ["occurred_at"],
    )
    op.create_index(
        "ix_agent_run_event_run_sequence",
        "agent_run_event",
        ["run_id", "sequence"],
    )


def downgrade() -> None:
    op.drop_index("ix_agent_run_event_run_sequence", table_name="agent_run_event")
    op.drop_index("ix_agent_run_event_occurred_at", table_name="agent_run_event")
    op.drop_index("ix_agent_run_event_invocation_id", table_name="agent_run_event")
    op.drop_index("ix_agent_run_event_run_id", table_name="agent_run_event")
    op.drop_table("agent_run_event")

    op.drop_index("ix_agent_invocation_run_sequence", table_name="agent_invocation")
    op.drop_index(
        "ix_agent_invocation_idempotency_key", table_name="agent_invocation"
    )
    op.drop_index("ix_agent_invocation_status", table_name="agent_invocation")
    op.drop_index("ix_agent_invocation_run_id", table_name="agent_invocation")
    op.drop_table("agent_invocation")

    op.drop_index("ix_agent_run_status_created_at", table_name="agent_run")
    op.drop_index("ix_agent_run_created_at", table_name="agent_run")
    op.drop_index("ix_agent_run_error_code", table_name="agent_run")
    op.drop_index("ix_agent_run_status", table_name="agent_run")
    op.drop_index("ix_agent_run_thread_id", table_name="agent_run")
    op.drop_index("ix_agent_run_user_id", table_name="agent_run")
    op.drop_table("agent_run")
