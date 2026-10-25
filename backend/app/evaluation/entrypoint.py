"""Deterministic headless entrypoint using the production Runtime composition."""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Sequence
from contextlib import asynccontextmanager
import json
from pathlib import Path
import tempfile
import time
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel

from app.capabilities.base import BaseCapability
from app.capabilities.registry import CapabilityRegistry
from app.capabilities.types import ActionDescriptor, CapabilityResult
from app.evaluation.adapter import (
    FixtureMemory,
    classify_route,
    normalize_events,
)
from app.evaluation.scripted_llm import ScriptedLLM, ScriptedObservationError
from app.evaluation.types import ApprovalFixture, EvalCase, ExecutionResult
from app.harness.budget import CancellationToken, RunBudget
from app.harness.checkpoint import SqliteCheckpointStore
from app.harness.contracts import ExecutionContext
from app.harness.execution import build_runtime
from app.harness.model_gateway import ModelGateway
from app.harness.policy import Approval
from app.harness.task import AgentTask
from app.schemas.user import UserRead
from app.trace.sql_store import SqlTraceStore
from app.models import User


_TERMINAL_EVENTS = {
    "run_completed": ("completed", "succeeded", "run.succeeded"),
    "run_failed": ("failed", "failed", "run.failed"),
    "run_cancelled": ("cancelled", "cancelled", "run.cancelled"),
    "run_timeout": ("timeout", "failed", "run.failed"),
}


@asynccontextmanager
async def isolated_headless_session(
    user_id: int,
) -> AsyncIterator[tuple[AsyncSession, UserRead]]:
    """Yield a synthetic trusted user and a fresh in-memory SQL database."""
    if user_id < 1:
        raise ValueError("headless evaluation requires a positive user id")

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        poolclass=StaticPool,
    )
    try:
        # Importing the package registers the existing SQLModel tables. This
        # engine is explicit in-memory SQLite and never reads DATABASE_URL.
        import app.models  # noqa: F401

        async with engine.begin() as connection:
            await connection.run_sync(SQLModel.metadata.create_all)

        session_factory = async_sessionmaker(
            engine,
            class_=AsyncSession,
            expire_on_commit=False,
        )
        async with session_factory() as session:
            row = User(
                id=user_id,
                username=f"headless-evaluation-{user_id}",
            )
            session.add(row)
            await session.commit()
            await session.refresh(row)
            yield session, UserRead.model_validate(row)
    finally:
        await engine.dispose()


class _EntrypointEchoCapability(BaseCapability):
    def __init__(self) -> None:
        self.flaky_calls = 0
        self.writes: list[str] = []

    @property
    def name(self) -> str:
        return "entrypoint"

    @property
    def description(self) -> str:
        return "Deterministic read and approved-write eval capability."

    def actions(self) -> list[ActionDescriptor]:
        read_schema = {
            "type": "object",
            "properties": {"text": {"type": "string"}},
            "required": ["text"],
            "additionalProperties": False,
        }
        read_output = {
            "type": "object",
            "properties": {"value": {"type": "string"}},
            "required": ["value"],
            "additionalProperties": False,
        }
        return [
            ActionDescriptor(
                name="echo",
                public_name="entrypoint.echo",
                description="Return the fixed synthetic evaluation value.",
                input_schema=read_schema,
                output_schema=read_output,
                requires_auth=True,
                is_side_effect=False,
                retry_class="read_only",
            ),
            ActionDescriptor(
                name="flaky",
                public_name="entrypoint.flaky",
                description="Fail the first synthetic read, then succeed.",
                input_schema=read_schema,
                output_schema=read_output,
                requires_auth=True,
                is_side_effect=False,
                retry_class="read_only",
            ),
            ActionDescriptor(
                name="write",
                public_name="entrypoint.write",
                description="Record one approved synthetic side effect.",
                input_schema={
                    "type": "object",
                    "properties": {
                        "value": {"type": "string"},
                        "idempotency_key": {"type": "string"},
                    },
                    "required": ["value", "idempotency_key"],
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "properties": {"appended": {"type": "string"}},
                    "required": ["appended"],
                },
                requires_auth=True,
                is_side_effect=True,
                approval_required=True,
                idempotency_mode="required",
            ),
        ]

    async def execute(self, action: str, **kwargs: Any) -> dict[str, Any]:
        if action == "echo":
            return {"success": True, "value": "synthetic-result"}
        if action == "flaky":
            self.flaky_calls += 1
            if self.flaky_calls == 1:
                return CapabilityResult.fail(
                    "Synthetic read failure",
                    error_type="read_failure",
                ).to_dict()
            return {"success": True, "value": "recovered-result"}
        if action == "write":
            value = str(kwargs.get("value") or "")
            self.writes.append(value)
            return {"success": True, "appended": value}
        return {"success": False, "error_type": "invalid_action"}


async def run_headless_case(
    case: EvalCase,
    *,
    registry: CapabilityRegistry,
    model_gateway: ModelGateway,
    model: str,
    fail_on_run_failure: bool,
    fail_on_tool_failure: bool = False,
    observation_failure_source: Callable[[], Sequence[str]] | None = None,
    approvals: Sequence[ApprovalFixture] = (),
) -> tuple[ExecutionResult, list[dict[str, Any]]]:
    """Execute one case with durable Runtime stores backed by isolated SQL.

    Declared approvals are trusted server-side fixtures: the principal always
    comes from the isolated fixture user, never from model arguments.
    """
    run_id = f"eval-{case.id}"
    started = time.perf_counter()
    checkpoint_context = tempfile.TemporaryDirectory() if approvals else None
    checkpoint_store = (
        SqliteCheckpointStore(str(Path(checkpoint_context.name) / "checkpoint.db"))
        if checkpoint_context is not None
        else None
    )
    async with isolated_headless_session(case.user_fixture.user_id) as (
        session,
        user,
    ):
        trace_store = SqlTraceStore(session)
        memory_context = await FixtureMemory(case).retrieve_context(
            run_id,
            case.input_messages[-1].content,
        )
        runtime = build_runtime(
            session=session,
            user=user,
            registry=registry,
            model_gateway=model_gateway,
            trace_store=trace_store,
            durable=True,
            allow_side_effects=bool(approvals),
            checkpoint_store=checkpoint_store,
            memory_context=memory_context,
        )
        context = ExecutionContext(
            principal_id=user.id,
            run_id=run_id,
            trace_id=run_id,
            thread_id=run_id,
            capability_allowlist=frozenset(
                definition.public_name
                for definition in registry.allowed_public_definitions(
                    include_side_effects=bool(approvals)
                )
            ),
        )
        task = AgentTask(
            user_id=user.id,
            goal=case.input_messages[-1].content,
            task_metadata={
                "model": model,
                "messages": [message.model_dump() for message in case.input_messages],
                "thread_id": run_id,
                "run_id": run_id,
                "trace_id": run_id,
            },
        )
        try:
            approval_queue = list(approvals)
            pending_approval: Approval | None = None
            events: list[dict[str, Any]] = []
            while True:
                batch = [
                    event
                    async for event in runtime.stream_decision(
                        task,
                        context=context,
                        budget=RunBudget(),
                        cancellation=CancellationToken(),
                        approval=pending_approval,
                    )
                ]
                events.extend(batch)
                required = next(
                    (
                        event
                        for event in batch
                        if event.get("type") == "approval_required"
                    ),
                    None,
                )
                if required is None or not approval_queue:
                    break
                fixture = approval_queue.pop(0)
                pending_approval = Approval(
                    approval_id=str(required.get("approval_id") or ""),
                    principal_id=user.id,
                    action=fixture.action,
                )
        except Exception as exc:
            raise RuntimeError("headless Runtime execution failed") from exc

        observation_failures = (
            tuple(observation_failure_source())
            if observation_failure_source is not None
            else ()
        )
        if observation_failures:
            # Observation failures must surface before the canonical/trace
            # validators, which may otherwise mask a first-call failure with a
            # generic "trace incomplete" error.
            raise ScriptedObservationError("; ".join(observation_failures))

        result = normalize_events(
            events,
            response_schema=case.assertions.response_schema,
            run_id=run_id,
        )
        await _validate_runtime_result(
            events,
            result,
            run_id=run_id,
            user_id=user.id,
            runtime=runtime,
            trace_store=trace_store,
        )

        if fail_on_run_failure and result.run_status != "completed":
            raise RuntimeError("headless Runtime run failed")
        if fail_on_tool_failure and result.tool_failure_count:
            raise RuntimeError("headless Runtime invocation failed")

    if checkpoint_context is not None:
        checkpoint_context.cleanup()

    duration_ms = (time.perf_counter() - started) * 1000
    result = result.model_copy(
        update={
            "route": classify_route(events, result.capabilities, result.text),
            "latency_ms": duration_ms,
            "trace_id": run_id,
        }
    )
    return result, events


async def _validate_runtime_result(
    events: list[dict[str, Any]],
    result: ExecutionResult,
    *,
    run_id: str,
    user_id: int,
    runtime: Any,
    trace_store: SqlTraceStore,
) -> None:
    terminals = [event for event in events if event.get("type") in _TERMINAL_EVENTS]
    if (
        not events
        or len(terminals) != 1
        or terminals[0] is not events[-1]
        or any(event.get("run_id") != run_id for event in events)
    ):
        raise RuntimeError("headless Runtime canonical result mismatch")

    terminal = terminals[0]
    normalized_status, stored_status, stored_event_type = _TERMINAL_EVENTS[
        str(terminal["type"])
    ]
    if result.run_status != normalized_status:
        raise RuntimeError("headless Runtime canonical result mismatch")
    if (
        terminal.get("type") == "run_completed"
        and terminal.get("content") != result.text
    ):
        raise RuntimeError("headless Runtime canonical result mismatch")

    stored_run = await runtime.run_store.get(run_id, user_id=user_id)
    if stored_run is None or stored_run.status != stored_status:
        raise RuntimeError("headless Runtime canonical result mismatch")
    stored_events = await runtime.event_store.list_after(run_id)
    stored_terminals = [
        event
        for event in stored_events
        if event.event_type in {"run.succeeded", "run.failed", "run.cancelled"}
    ]
    if len(stored_terminals) != 1:
        raise RuntimeError("headless Runtime canonical result mismatch")
    stored_terminal = stored_terminals[0]
    if (
        stored_terminal.event_type != stored_event_type
        or stored_terminal.sequence != terminal.get("sequence")
    ):
        raise RuntimeError("headless Runtime canonical result mismatch")
    stored_payload = json.loads(stored_terminal.payload_json or "{}")
    for field in ("content", "error_code", "termination_reason"):
        if field in terminal and stored_payload.get(field) != terminal[field]:
            raise RuntimeError("headless Runtime canonical result mismatch")

    trace = await trace_store.query(run_id, user_id=user_id)
    if trace is None:
        raise RuntimeError("headless Runtime trace unavailable")
    trace_status = (
        "cancelled"
        if normalized_status == "cancelled"
        else ("completed" if normalized_status == "completed" else "failed")
    )
    trace_events = [event for step in trace.steps for event in step.events]
    if (
        trace.trace_id != run_id
        or trace.run_id != run_id
        or trace.user_id != user_id
        or trace.status != trace_status
        or any(event.run_id != run_id for event in trace_events)
    ):
        raise RuntimeError("headless Runtime trace correlation missing")
    trace_types = {event.event_type.value for event in trace_events}
    if "model_call" not in trace_types:
        raise RuntimeError("headless Runtime trace incomplete")
    if result.tool_call_count and not {
        "tool_call_start",
        "tool_call_end",
    }.issubset(trace_types):
        raise RuntimeError("headless Runtime trace incomplete")


class DecisionEntrypointTarget:
    """Offline target exercising the Runtime-owned Decision and Dispatcher path."""

    async def evaluate(self, case: EvalCase) -> ExecutionResult:
        registry = CapabilityRegistry()
        registry.register(_EntrypointEchoCapability())
        gateway = ScriptedLLM.from_script_events(case.fixtures.events)
        # A case that explicitly allows tool error codes is exercising recovery,
        # so the target must not turn the observed failure into a hard exception.
        allows_tool_errors = bool(
            case.deterministic is not None
            and case.deterministic.tool_errors.allowed_error_codes
        )
        result, _events = await run_headless_case(
            case,
            registry=registry,
            model_gateway=gateway,
            model="entrypoint-fixture-v1",
            fail_on_run_failure=True,
            fail_on_tool_failure=not allows_tool_errors,
            observation_failure_source=lambda: gateway.observation_failures,
            approvals=case.approvals,
        )
        return result


def create_entrypoint_target(_config=None) -> DecisionEntrypointTarget:
    return DecisionEntrypointTarget()
