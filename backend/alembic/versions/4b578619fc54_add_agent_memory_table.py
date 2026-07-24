"""Add agent_memory table

Revision ID: 4b578619fc54
Revises: bbd93366421b
Create Date: 2026-07-23 01:16:12.588508

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4b578619fc54'
down_revision: Union[str, Sequence[str], None] = 'bbd93366421b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "agent_memory",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("fact_id", sa.String(), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("thread_id", sa.String(), nullable=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("importance", sa.Float(), nullable=False, server_default=sa.text("0.5")),
        sa.Column("source", sa.String(), nullable=False, server_default=sa.text("'conversation'")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "kind IN ('episodic', 'semantic', 'profile')",
            name="ck_agent_memory_kind",
        ),
        sa.CheckConstraint(
            "importance >= 0 AND importance <= 1",
            name="ck_agent_memory_importance",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "user_id",
            "thread_id",
            "fact_id",
            name="uq_agent_memory_user_thread_fact",
        ),
    )
    op.create_index("ix_agent_memory_fact_id", "agent_memory", ["fact_id"])
    op.create_index("ix_agent_memory_user_id", "agent_memory", ["user_id"])
    op.create_index("ix_agent_memory_thread_id", "agent_memory", ["thread_id"])
    op.create_index("ix_agent_memory_kind", "agent_memory", ["kind"])
    op.create_index("ix_agent_memory_created_at", "agent_memory", ["created_at"])


def downgrade() -> None:
    op.drop_index("ix_agent_memory_created_at", table_name="agent_memory")
    op.drop_index("ix_agent_memory_kind", table_name="agent_memory")
    op.drop_index("ix_agent_memory_thread_id", table_name="agent_memory")
    op.drop_index("ix_agent_memory_user_id", table_name="agent_memory")
    op.drop_index("ix_agent_memory_fact_id", table_name="agent_memory")
    op.drop_table("agent_memory")
