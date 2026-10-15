"""Immutable A-L1-03 current-business compatibility snapshot, baseline revision a10300000001."""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    Time,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSON as PostgreSQLJSON

BUSINESS_TABLES = (
    "users",
    "subject",
    "collection",
    "schedules",
    "anime_broadcast_metadata",
)
METADATA = MetaData()
Table(
    "agent_trace",
    METADATA,
    Column("id", Integer(), nullable=False, primary_key=True),
    Column("trace_id", String(), nullable=False, unique=True, index=True),
    Column("user_id", Integer(), index=True),
    Column("task_id", Integer(), index=True),
    Column("agent_name", String(), nullable=False),
    Column("goal", String(), nullable=False),
    Column("status", String(), nullable=False, index=True),
    Column("headers_json", String()),
    Column("started_at", DateTime(timezone=True), nullable=False, index=True),
    Column("created_at", DateTime(timezone=True), nullable=False, index=True),
)
Table(
    "anime_broadcast_metadata",
    METADATA,
    Column("bangumi_id", Integer(), nullable=False, primary_key=True),
    Column("title", String(), nullable=False),
    Column("broadcast_begin", DateTime(), nullable=False),
    Column("broadcast_tz", String(), nullable=False),
    Column("year", Integer(), nullable=False),
    Column("season", Integer(), nullable=False),
    Column("updated_at", DateTime(), nullable=False),
)
Table(
    "subject",
    METADATA,
    Column("id", Integer(), nullable=False, primary_key=True),
    Column("source", String(), nullable=False, index=True),
    Column("source_id", String(), nullable=False, index=True),
    Column(
        "type",
        Enum(
            "BOOK",
            "ANIME",
            "MUSIC",
            "GAME",
            "REAL",
            name="subjecttype",
            native_enum=True,
            create_constraint=False,
            validate_strings=False,
            length=5,
        ),
        nullable=False,
        index=True,
    ),
    Column("name", String(), nullable=False),
    Column("name_cn", String()),
    Column("summary", Text()),
    Column("date", String()),
    Column("platform", String()),
    Column("images", PostgreSQLJSON(astext_type=Text())),
    Column("image", String()),
    Column("tags", PostgreSQLJSON(astext_type=Text())),
    Column("meta_tags", PostgreSQLJSON(astext_type=Text())),
    Column("infobox", PostgreSQLJSON(astext_type=Text())),
    Column("rating", PostgreSQLJSON(astext_type=Text())),
    Column("collection", PostgreSQLJSON(astext_type=Text())),
    Column("eps", Integer()),
    Column("volumes", Integer()),
    Column("series", Boolean(), nullable=False),
    Column("locked", Boolean(), nullable=False),
    Column("nsfw", Boolean(), nullable=False),
    Column("air_time", DateTime()),
    Column("air_weekday", Integer()),
    Column("last_sync", DateTime(), nullable=False),
    UniqueConstraint("source", "source_id", name="uq_source_source_id"),
)
Table(
    "users",
    METADATA,
    Column("id", Integer(), nullable=False, primary_key=True),
    Column("username", String(), nullable=False, unique=True, index=True),
    Column("avatar_url", String()),
    Column("bangumi_id", Integer(), index=True),
    Column("bangumi_name", String()),
    Column("sign", String()),
    Column("created_at", DateTime(), nullable=False),
)
Table(
    "agent_memory",
    METADATA,
    Column("id", Integer(), nullable=False, primary_key=True),
    Column("fact_id", String(), nullable=False, index=True),
    Column("user_id", Integer(), ForeignKey("users.id"), nullable=False, index=True),
    Column("thread_id", String(), index=True),
    Column("kind", String(), nullable=False, index=True),
    Column("content", String(), nullable=False),
    Column("importance", Float(), nullable=False),
    Column("source", String(), nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False, index=True),
    Column("metadata_json", String()),
    CheckConstraint(
        "importance >= 0 AND importance <= 1", name="ck_agent_memory_importance"
    ),
    CheckConstraint(
        "kind IN ('episodic', 'semantic', 'profile')", name="ck_agent_memory_kind"
    ),
    UniqueConstraint(
        "user_id", "thread_id", "fact_id", name="uq_agent_memory_user_thread_fact"
    ),
)
Table(
    "agent_run",
    METADATA,
    Column("run_id", String(), nullable=False, primary_key=True),
    Column("user_id", Integer(), ForeignKey("users.id"), index=True),
    Column("thread_id", String(), index=True),
    Column("status", String(), nullable=False, index=True),
    Column("goal_hash", String(), nullable=False),
    Column("model", String(), nullable=False),
    Column("started_at", DateTime(timezone=True)),
    Column("finished_at", DateTime(timezone=True)),
    Column("error_code", String(), index=True),
    Column("created_at", DateTime(timezone=True), nullable=False, index=True),
)
Table(
    "agent_task_def",
    METADATA,
    Column("id", Integer(), nullable=False, primary_key=True),
    Column("user_id", Integer(), ForeignKey("users.id"), nullable=False, index=True),
    Column("task_type", String(), nullable=False),
    Column("payload", String(), nullable=False),
    Column("schedule_expr", String(), nullable=False),
    Column("timezone", String(), nullable=False),
    Column("enabled", Boolean(), nullable=False),
    Column("deleted_at", DateTime()),
    Column("next_run", DateTime()),
    Column("catch_up", String(), nullable=False),
    Column("policy", String(), nullable=False),
    Column("idempotency_key", String(), index=True),
    Column("created_at", DateTime(), nullable=False),
    Column("updated_at", DateTime(), nullable=False),
)
Table(
    "collection",
    METADATA,
    Column("id", Integer(), nullable=False, primary_key=True, index=True),
    Column("user_id", Integer(), ForeignKey("users.id"), nullable=False, index=True),
    Column("source", String(), nullable=False, index=True),
    Column("source_id", String(), nullable=False, index=True),
    Column(
        "type",
        Enum(
            "WISH",
            "COLLECT",
            "DO",
            "ON_HOLD",
            "DROPPED",
            name="collectionstatus",
            native_enum=True,
            create_constraint=False,
            validate_strings=False,
            length=7,
        ),
        nullable=False,
    ),
    Column("rate", Integer()),
    Column("comment", String()),
    Column("updated_at", DateTime(), nullable=False, index=True),
    Column("private", Boolean(), nullable=False),
    Column("tags", PostgreSQLJSON(astext_type=Text())),
    Column("vol_status", Integer(), nullable=False),
    Column("ep_status", Integer(), nullable=False),
    Column("subject_type", Integer(), nullable=False),
    UniqueConstraint("user_id", "source", "source_id", name="uq_user_collection"),
)
Table(
    "schedules",
    METADATA,
    Column("id", Integer(), nullable=False, primary_key=True),
    Column("source", String(), nullable=False),
    Column("source_id", String(), nullable=False),
    Column("day_of_week", Integer(), nullable=False),
    Column("start_time", Time(), nullable=False),
    Column("watch_day", Integer()),
    Column("watch_time", Time()),
    Column("duration", Integer()),
    Column("user_id", Integer(), ForeignKey("users.id"), nullable=False),
    Column(
        "watch_type",
        Enum(
            "MEAL",
            "LEISURE",
            "LONG_GRASS",
            "NEW",
            name="watchtype",
            native_enum=True,
            create_constraint=False,
            validate_strings=False,
            length=10,
        ),
    ),
    UniqueConstraint(
        "user_id", "source", "source_id", name="unique_user_source_source_id"
    ),
)
Table(
    "trace_event",
    METADATA,
    Column("id", Integer(), nullable=False, primary_key=True),
    Column(
        "trace_id",
        String(),
        ForeignKey("agent_trace.trace_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    ),
    Column("step_index", Integer(), nullable=False),
    Column("step_label", String(), nullable=False),
    Column("agent_name", String(), nullable=False),
    Column("status", String(), nullable=False),
    Column("step_json", String()),
    Column("created_at", DateTime(timezone=True), nullable=False),
)
Table(
    "agent_invocation",
    METADATA,
    Column("invocation_id", String(), nullable=False, primary_key=True),
    Column(
        "run_id", String(), ForeignKey("agent_run.run_id"), nullable=False, index=True
    ),
    Column("sequence", Integer(), nullable=False),
    Column("capability", String(), nullable=False),
    Column("capability_version", String(), nullable=False),
    Column("status", String(), nullable=False, index=True),
    Column("input_hash", String(), nullable=False),
    Column("idempotency_key", String(), index=True),
    Column("started_at", DateTime(timezone=True)),
    Column("finished_at", DateTime(timezone=True)),
    Column("error_code", String()),
    UniqueConstraint("run_id", "sequence", name="uq_agent_invocation_run_sequence"),
    UniqueConstraint(
        "run_id", "idempotency_key", name="uq_agent_invocation_run_idempotency_key"
    ),
)
Table(
    "agent_run_event",
    METADATA,
    Column("event_id", String(), nullable=False, primary_key=True),
    Column(
        "run_id", String(), ForeignKey("agent_run.run_id"), nullable=False, index=True
    ),
    Column("sequence", Integer(), nullable=False),
    Column("event_type", String(), nullable=False),
    Column("invocation_id", String(), index=True),
    Column("payload_json", String(), nullable=False),
    Column("occurred_at", DateTime(timezone=True), nullable=False, index=True),
    UniqueConstraint("run_id", "sequence", name="uq_agent_run_event_run_sequence"),
)
Table(
    "agent_task_run",
    METADATA,
    Column("id", Integer(), nullable=False, primary_key=True),
    Column(
        "task_def_id",
        Integer(),
        ForeignKey("agent_task_def.id"),
        nullable=False,
        index=True,
    ),
    Column("user_id", Integer(), ForeignKey("users.id"), nullable=False, index=True),
    Column("scheduled_slot", DateTime(), nullable=False),
    Column("attempt", Integer(), nullable=False),
    Column("lease_id", String()),
    Column("lease_expires_at", DateTime()),
    Column("status", String(), nullable=False),
    Column("trace_id", String()),
    Column("error_category", String()),
    Column("started_at", DateTime()),
    Column("finished_at", DateTime()),
    Column("created_at", DateTime(), nullable=False),
    UniqueConstraint("task_def_id", "scheduled_slot", name="uq_agent_task_run_slot"),
)
Index(
    "ix_agent_run_status_created_at",
    METADATA.tables["agent_run"].c.status,
    METADATA.tables["agent_run"].c.created_at,
)
Index(
    "ix_agent_invocation_run_sequence",
    METADATA.tables["agent_invocation"].c.run_id,
    METADATA.tables["agent_invocation"].c.sequence,
)
Index(
    "ix_agent_run_event_run_sequence",
    METADATA.tables["agent_run_event"].c.run_id,
    METADATA.tables["agent_run_event"].c.sequence,
)
__all__ = ["BUSINESS_TABLES", "METADATA"]


# PostgreSQL's canonical deparsing of the frozen CHECK expressions. Keep these
# strict: whitespace-only normalization cannot account for dialect casts/ANY.
POSTGRES_CHECKS = {
    "agent_memory": (
        "importance >= 0::double precision AND importance <= 1::double precision",
        "kind::text = ANY (ARRAY['episodic'::character varying, "
        "'semantic'::character varying, 'profile'::character varying]::text[])",
    ),
}
