"""Persistent scheduled agent task model — PROACTIVE-001.

Each row represents an autonomously scheduled task configuration owned
by a user.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from typing import Any, Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import model_validator
from sqlalchemy import UniqueConstraint
from sqlmodel import Field, SQLModel


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AgentTaskDef(SQLModel, table=True):
    """Definition of a scheduled autonomous task."""

    __tablename__ = "agent_task_def"

    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(foreign_key="users.id", index=True, nullable=False)
    task_type: str = Field(nullable=False)  # e.g. "seasonal_scan", "weekly_recommendation"
    payload: str = Field(default="{}")  # JSON, validated at creation
    schedule_expr: str = Field(default="* * * * *", nullable=False)  # cron-like: "0 9 * * 1"
    timezone: str = Field(default="Asia/Shanghai")
    enabled: bool = Field(default=True)
    deleted_at: Optional[datetime] = Field(default=None)
    next_run: Optional[datetime] = Field(default=None)
    catch_up: str = Field(default="latest", nullable=False)  # skip | latest | all
    policy: str = Field(default="{}", nullable=False)  # JSON policy, validated at creation
    idempotency_key: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now, sa_column_kwargs={"onupdate": _utc_now})

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)
        self.validate_definition()

    @model_validator(mode="after")
    def validate_definition(self) -> "AgentTaskDef":
        _validate_schedule(self.schedule_expr)
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValueError(f"invalid timezone: {self.timezone}") from exc
        _validate_json_payload(self.payload)
        _validate_json_payload(self.policy)
        if self.catch_up not in {"skip", "latest", "all"}:
            raise ValueError("catch_up must be skip, latest, or all")
        return self


class AgentTaskRun(SQLModel, table=True):
    """Execution record for a single scheduled slot."""

    __tablename__ = "agent_task_run"
    __table_args__ = (UniqueConstraint("task_def_id", "scheduled_slot", name="uq_agent_task_run_slot"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    task_def_id: int = Field(foreign_key="agent_task_def.id", index=True, nullable=False)
    user_id: int = Field(foreign_key="users.id", index=True, nullable=False)
    scheduled_slot: datetime = Field(nullable=False)  # the UTC slot this run belongs to
    attempt: int = Field(default=0)
    lease_id: Optional[str] = Field(default=None)
    lease_expires_at: Optional[datetime] = Field(default=None)
    status: str = Field(default="pending")  # pending | running | success | failed | cancelled
    trace_id: Optional[str] = Field(default=None)
    error_category: Optional[str] = Field(default=None)
    started_at: Optional[datetime] = Field(default=None)
    finished_at: Optional[datetime] = Field(default=None)
    created_at: datetime = Field(default_factory=_utc_now)


_CRON_TOKEN = re.compile(r"^(\*|\d{1,2})(/(\d{1,2}))?(,((\*|\d{1,2})(/(\d{1,2}))?))*$")
_SECRET_KEYS = {"api_key", "apikey", "token", "secret", "password", "credential", "credentials"}


def _validate_schedule(schedule_expr: str) -> None:
    fields = schedule_expr.split()
    if len(fields) != 5 or any(not _CRON_TOKEN.fullmatch(field) for field in fields):
        raise ValueError("schedule_expr must be a five-field cron expression")
    limits = ((0, 59), (0, 23), (1, 31), (1, 12), (0, 7))
    for field, (minimum, maximum) in zip(fields, limits):
        for part in field.split(","):
            if "/" in part and int(part.split("/", 1)[1]) < 1:
                raise ValueError("cron step must be greater than zero")
            base = part.split("/", 1)[0]
            if base != "*" and not minimum <= int(base) <= maximum:
                raise ValueError("schedule_expr contains a value outside its field range")


def _validate_json_payload(raw: str) -> None:
    try:
        value: Any = json.loads(raw or "{}")
    except json.JSONDecodeError as exc:
        raise ValueError("payload and policy must be valid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError("payload and policy must be JSON objects")

    def walk(item: Any) -> None:
        if isinstance(item, dict):
            for key, child in item.items():
                if str(key).lower().replace("-", "_") in _SECRET_KEYS:
                    raise ValueError("provider credentials are not allowed in scheduled task data")
                walk(child)
        elif isinstance(item, list):
            for child in item:
                walk(child)

    walk(value)
