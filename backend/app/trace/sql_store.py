"""Durable, user-scoped storage for agent execution traces."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, delete, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.core.logging import get_logger
from app.models.agent_trace import AgentTraceModel, TraceEventModel
from app.trace import (
    TRACE_LEGACY_SCHEMA_VERSION,
    AgentTrace,
    TraceStep,
)
from app.trace.redaction import UnsafeTraceDataError, sanitize_trace

logger = get_logger(__name__)

_MAX_TRACES = 1000
_DEFAULT_MAX_AGE = timedelta(days=30)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _encode_cursor(started_at: datetime, trace_id: str) -> str:
    payload = json.dumps(
        {"started_at": started_at.isoformat(), "trace_id": trace_id},
        separators=(",", ":"),
    ).encode()
    return base64.urlsafe_b64encode(payload).decode()


def _decode_cursor(cursor: str) -> tuple[datetime, str]:
    try:
        payload = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
        return datetime.fromisoformat(payload["started_at"]), str(payload["trace_id"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("invalid trace cursor") from exc


def _fallback_safe_trace(trace: AgentTrace) -> AgentTrace:
    """Keep correlation/error fields when the normal sanitizer rejects payloads."""
    payload = trace.model_dump(mode="json")
    payload["goal"] = "[REDACTED]"
    payload["error"] = None
    for step in payload.get("steps", []):
        step["input_summary"] = None
        step["output_summary"] = None
        for event in step.get("events", []):
            raw_data = event.get("data") or {}
            error_code = event.get("error_code")
            if error_code is None and isinstance(raw_data, dict):
                error_code = raw_data.get("error_code")
            event["data"] = {"redaction": "unsafe_payload_dropped"}
            if error_code is not None:
                event["data"]["error_code"] = str(error_code)
    return AgentTrace.model_validate(payload)


class SqlTraceStore:
    """Persistent trace store with bounded retention and stable pagination."""

    def __init__(
        self,
        session: AsyncSession,
        max_traces: int = _MAX_TRACES,
        max_age: timedelta | None = _DEFAULT_MAX_AGE,
    ) -> None:
        if max_traces < 1:
            raise ValueError("max_traces must be positive")
        self._session = session
        self._max_traces = max_traces
        self._max_age = max_age

    async def record(self, trace: AgentTrace) -> None:
        try:
            try:
                safe_trace = sanitize_trace(trace)
            except UnsafeTraceDataError:
                logger.warning(
                    "trace_payload_redaction_failed",
                    extra={"trace_id": trace.trace_id},
                )
                safe_trace = _fallback_safe_trace(trace)
            headers = safe_trace.model_dump(mode="json", exclude={"steps"})
            self._session.add(
                AgentTraceModel(
                    trace_id=safe_trace.trace_id,
                    user_id=safe_trace.user_id,
                    task_id=safe_trace.task_id,
                    agent_name=safe_trace.agent_name,
                    goal=safe_trace.goal,
                    status=safe_trace.status or "completed",
                    headers_json=json.dumps(headers, ensure_ascii=False),
                    started_at=safe_trace.started_at,
                )
            )

            for step in safe_trace.steps:
                step_data = step.model_dump(mode="json")
                self._session.add(
                    TraceEventModel(
                        trace_id=safe_trace.trace_id,
                        step_index=step.step_index,
                        step_label=step.step_label,
                        agent_name=step.agent_name,
                        status=step.status,
                        step_json=json.dumps(step_data, ensure_ascii=False),
                    )
                )

            await self._session.commit()
        except Exception:
            await self._session.rollback()
            raise
        await self._enforce_retention()

    async def query(
        self,
        trace_id: str,
        *,
        user_id: int | None = None,
    ) -> AgentTrace | None:
        if user_id is None:
            return None
        stmt = select(AgentTraceModel).where(
            AgentTraceModel.trace_id == trace_id,
            AgentTraceModel.user_id == user_id,
        )
        model = (await self._session.execute(stmt)).scalars().one_or_none()
        if model is None:
            return None
        return await self._model_to_trace(model)

    async def list_recent(
        self,
        limit: int = 20,
        user_id: int | None = None,
    ) -> list[AgentTrace]:
        traces, _ = await self.list_page(limit=limit, user_id=user_id)
        return traces

    async def list_page(
        self,
        *,
        limit: int = 20,
        user_id: int | None,
        cursor: str | None = None,
        task_id: int | None = None,
        status: str | None = None,
        started_after: datetime | None = None,
        started_before: datetime | None = None,
    ) -> tuple[list[AgentTrace], str | None]:
        if user_id is None:
            return [], None
        bounded_limit = max(1, min(limit, 100))
        stmt = select(AgentTraceModel).where(AgentTraceModel.user_id == user_id)
        if task_id is not None:
            stmt = stmt.where(AgentTraceModel.task_id == task_id)
        if status is not None:
            stmt = stmt.where(AgentTraceModel.status == status)
        if started_after is not None:
            stmt = stmt.where(AgentTraceModel.started_at >= started_after)
        if started_before is not None:
            stmt = stmt.where(AgentTraceModel.started_at < started_before)
        if cursor is not None:
            started_at, trace_id = _decode_cursor(cursor)
            stmt = stmt.where(
                or_(
                    AgentTraceModel.started_at < started_at,
                    and_(
                        AgentTraceModel.started_at == started_at,
                        AgentTraceModel.trace_id < trace_id,
                    ),
                )
            )
        stmt = stmt.order_by(
            AgentTraceModel.started_at.desc(),
            AgentTraceModel.trace_id.desc(),
        ).limit(bounded_limit + 1)
        models = list((await self._session.execute(stmt)).scalars().all())
        has_more = len(models) > bounded_limit
        models = models[:bounded_limit]
        traces = [await self._model_to_trace(model) for model in models]
        next_cursor = None
        if has_more and models:
            last = models[-1]
            next_cursor = _encode_cursor(last.started_at, last.trace_id)
        return traces, next_cursor

    async def _enforce_retention(self) -> None:
        try:
            delete_trace_ids: set[str] = set()
            if self._max_age is not None:
                cutoff = _utc_now() - self._max_age
                old_stmt = select(AgentTraceModel.trace_id).where(
                    AgentTraceModel.started_at < cutoff
                )
                delete_trace_ids.update(
                    (await self._session.execute(old_stmt)).scalars().all()
                )

            count_stmt = (
                select(AgentTraceModel.trace_id)
                .order_by(
                    AgentTraceModel.started_at.desc(),
                    AgentTraceModel.trace_id.desc(),
                )
                .offset(self._max_traces)
            )
            delete_trace_ids.update(
                (await self._session.execute(count_stmt)).scalars().all()
            )
            if not delete_trace_ids:
                return

            await self._session.execute(
                delete(TraceEventModel).where(
                    TraceEventModel.trace_id.in_(delete_trace_ids)
                )
            )
            await self._session.execute(
                delete(AgentTraceModel).where(
                    AgentTraceModel.trace_id.in_(delete_trace_ids)
                )
            )
            await self._session.commit()
        except Exception:
            await self._session.rollback()
            logger.exception("trace_retention_failed")

    async def _model_to_trace(self, model: AgentTraceModel) -> AgentTrace:
        headers: dict[str, Any] = {}
        if model.headers_json:
            headers = json.loads(model.headers_json)
        legacy_trace = "schema_version" not in headers
        if legacy_trace:
            headers["schema_version"] = TRACE_LEGACY_SCHEMA_VERSION
        event_stmt = (
            select(TraceEventModel)
            .where(TraceEventModel.trace_id == model.trace_id)
            .order_by(TraceEventModel.step_index, TraceEventModel.id)
        )
        event_models = (
            (await self._session.execute(event_stmt)).scalars().all()
        )
        steps: list[TraceStep] = []
        for event in event_models:
            if not event.step_json:
                continue
            step_payload = json.loads(event.step_json)
            for event_payload in step_payload.get("events", []):
                if (
                    legacy_trace
                    and "schema_version" not in event_payload
                ):
                    event_payload["schema_version"] = (
                        TRACE_LEGACY_SCHEMA_VERSION
                    )
            steps.append(TraceStep.model_validate(step_payload))
        headers["steps"] = steps
        headers["trace_id"] = model.trace_id
        headers["user_id"] = model.user_id
        headers["task_id"] = model.task_id
        headers["started_at"] = model.started_at
        headers["status"] = model.status
        return AgentTrace.model_validate(headers)
