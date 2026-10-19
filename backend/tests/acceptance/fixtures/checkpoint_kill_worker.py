"""Subprocess worker for real API/checkpoint crash-recovery acceptance tests.

The parent test starts this module with file-backed application and checkpoint
databases.  A JSON line is emitted only after a selected durable boundary has
been reached; the parent then kills this process to model abrupt termination.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_armed = False
_boundary: str | None = None
_run_id: str | None = None
_thread_id: str | None = None
_sink_path: str | None = None
_feedback_seen = False
_boundary_reached = False
_model_call_count = 0
_capability_call_count = 0
_terminal_outcome = "completed"


def _emit(**payload: Any) -> None:
    print(json.dumps(payload, sort_keys=True), flush=True)


async def _block_at_boundary(name: str, **details: Any) -> None:
    global _boundary_reached
    if not _armed or _boundary != name or _boundary_reached:
        return
    _boundary_reached = True
    _emit(
        kind="boundary",
        boundary=name,
        run_id=_run_id,
        thread_id=_thread_id,
        observed_at=datetime.now(timezone.utc).isoformat(),
        **details,
    )
    await asyncio.Event().wait()


def _parse_sse(text: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for block in text.split("\n\n"):
        event_name = None
        data_lines: list[str] = []
        for line in block.splitlines():
            if line.startswith("event: "):
                event_name = line[7:].strip()
            elif line.startswith("data: "):
                data_lines.append(line[6:])
        if event_name is None or not data_lines:
            continue
        try:
            payload = json.loads("\n".join(data_lines))
        except json.JSONDecodeError:
            payload = {}
        events.append({"type": event_name, **payload})
    return events


async def _main(args: argparse.Namespace) -> int:
    global _armed, _boundary, _run_id, _thread_id, _sink_path
    global _feedback_seen, _model_call_count, _capability_call_count
    global _terminal_outcome

    os.environ.update(
        {
            "DEBUG": "false",
            "DEPLOY_MODE": "local",
            "SQLITE_FILE": args.app_db,
            "CHECKPOINT_DB_PATH": args.checkpoint_db,
            "CHECKPOINT_LEASE_SECONDS": "2",
            "HARNESS_CHECKPOINT_ADAPTER": "sqlite",
            "HARNESS_CHECKPOINT_SINGLE_WORKER": "true",
            "HARNESS_WORKER_COUNT": "1",
            "INTERACTIVE_RUN_STORE_ENABLED": "true",
            "ENABLE_MULTI_AGENT_ROUTING": "false",
            "PROVIDER_RESOLVE_DNS": "false",
            "OPENAI_API_KEY": "acceptance-fixture-key",
            "ENABLE_PROACTIVE_SCHEDULER": "false",
        }
    )

    import httpx
    from fastapi import FastAPI
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlmodel import SQLModel
    from sqlmodel.ext.asyncio.session import AsyncSession

    import app.models  # noqa: F401
    from app.api import api_router
    from app.api.deps import get_current_user, get_optional_user
    from app.api.v1 import agent as agent_api
    from app.capabilities.base import BaseCapability
    from app.capabilities.registry import CapabilityRegistry
    from app.capabilities.types import ActionDescriptor, CapabilityResult
    from app.harness.model_types import ModelCallResult
    from app.harness.contracts import RunEvent
    from app.harness.persistence.event_store import EventStore
    from app.harness.persistence.idempotency import SqlIdempotencyStore
    from app.db.database import get_session
    from app.harness.budget import RunBudget
    from app.harness.checkpoint import SqliteCheckpointStore
    from app.models import User
    from app.models.agent_run import AgentRunEvent
    from app.schemas.user import UserRead

    _boundary = args.boundary
    _thread_id = args.thread_id
    _sink_path = args.sink_db
    _terminal_outcome = args.terminal_outcome

    async_engine = create_async_engine(f"sqlite+aiosqlite:///{args.app_db}")
    session_factory = async_sessionmaker(
        async_engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with async_engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    async with session_factory() as session:
        for user_id in (7, 8):
            if await session.get(User, user_id) is None:
                session.add(
                    User(id=user_id, username=f"checkpoint-kill-user-{user_id}")
                )
        await session.commit()

    sink_path = Path(args.sink_db)
    sink_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(sink_path) as sink_connection:
        sink_connection.execute(
            "CREATE TABLE IF NOT EXISTS synthetic_writes "
            "(write_id INTEGER PRIMARY KEY AUTOINCREMENT, run_id TEXT, value TEXT)"
        )

    def fixture_user(user_id: int) -> UserRead:
        return UserRead(
            id=user_id,
            username=f"checkpoint-kill-user-{user_id}",
            created_at=datetime.now(timezone.utc),
        )

    active_user_id = 7

    async def override_session():
        async with session_factory() as session:
            yield session

    async def override_current_user():
        return fixture_user(active_user_id)

    async def override_optional_user():
        return fixture_user(active_user_id)

    class _WorkerGateway:
        def __init__(self, **kwargs: Any) -> None:
            self.model = str(kwargs.get("model", "checkpoint-kill-fixture"))
            self.call_number = 0

        async def infer(self, **kwargs: Any) -> ModelCallResult:
            global _feedback_seen, _model_call_count
            _model_call_count += 1
            messages = kwargs.get("messages") or []
            saw_result = any(
                "synthetic-side-effect-committed" in str(message.get("content", ""))
                for message in messages
                if isinstance(message, dict)
            )
            if saw_result:
                _feedback_seen = True
            current_run_id = str(kwargs.get("run_id") or _run_id or "")
            if not saw_result:
                decision = {
                    "schema_version": "v1",
                    "decision_id": f"decision-{current_run_id}",
                    "run_id": current_run_id,
                    "action": "invoke",
                    "capability": "checkpoint_kill.write",
                    "capability_version": "v1",
                    "arguments": {
                        "value": f"value-{current_run_id}",
                        "idempotency_key": f"key-{current_run_id}",
                    },
                }
            else:
                if _terminal_outcome == "cancelled":
                    return ModelCallResult(
                        provider="fixture",
                        model=self.model,
                        operation="infer",
                        status="cancelled",
                        error_code="cancelled",
                        trace_id=kwargs.get("trace_id"),
                    )
                if _terminal_outcome == "timeout":
                    return ModelCallResult(
                        provider="fixture",
                        model=self.model,
                        operation="infer",
                        status="failed",
                        error_code="timeout",
                        trace_id=kwargs.get("trace_id"),
                    )
                decision = {
                    "schema_version": "v1",
                    "decision_id": f"answer-{current_run_id}",
                    "run_id": current_run_id,
                    "action": "respond",
                    "content": "The synthetic write completed.",
                }
            return ModelCallResult(
                provider="fixture",
                model=self.model,
                operation="infer",
                status="completed",
                decision=decision,
                text=json.dumps(decision, sort_keys=True),
                trace_id=kwargs.get("trace_id"),
            )

        async def close(self) -> None:
            return None

    class _WorkerMemory:
        last_model_call = None

        async def retrieve_context(self, *values: Any, **kwargs: Any) -> None:
            return None

        async def extract_and_store_facts(self, *values: Any, **kwargs: Any) -> None:
            return None

    class _SyntheticWriteCapability(BaseCapability):
        @property
        def name(self) -> str:
            return "checkpoint_kill"

        @property
        def description(self) -> str:
            return "Synthetic durable write for process-kill acceptance tests"

        def actions(self) -> list[ActionDescriptor]:
            return [
                ActionDescriptor(
                    name="write",
                    public_name="checkpoint_kill.write",
                    description="Commit one synthetic write",
                    input_schema={
                        "type": "object",
                        "properties": {
                            "value": {"type": "string"},
                            "idempotency_key": {"type": "string"},
                        },
                        "required": ["value", "idempotency_key"],
                        "additionalProperties": False,
                    },
                    requires_auth=True,
                    is_side_effect=True,
                    idempotency_mode="required",
                    retry_class="transient",
                    timeout_seconds=5.0,
                )
            ]

        async def execute(self, action: str, **kwargs: Any) -> dict[str, Any]:
            global _capability_call_count
            _capability_call_count += 1
            if action != "write":
                raise AssertionError(f"Unexpected synthetic action: {action}")
            if _sink_path is None:
                raise AssertionError("Synthetic sink path was not configured")
            with sqlite3.connect(_sink_path) as connection:
                cursor = connection.execute(
                    "INSERT INTO synthetic_writes (run_id, value) VALUES (?, ?)",
                    (_run_id, str(kwargs["value"])),
                )
                if cursor.lastrowid is None:
                    raise AssertionError("Synthetic sink did not return a row id")
                write_id = cursor.lastrowid
                row_count = int(
                    connection.execute(
                        "SELECT COUNT(*) FROM synthetic_writes WHERE run_id = ?",
                        (_run_id,),
                    ).fetchone()[0]
                )
            if _boundary == "unknown" and _armed:
                await _block_at_boundary("unknown")
            return CapabilityResult.ok(
                marker="synthetic-side-effect-committed",
                write_id=write_id,
                sink_count=row_count,
            ).to_dict()

    class _WorkerCheckpointStore(SqliteCheckpointStore):
        async def save(self, run_id: str, thread_id: str, state, **kwargs: Any) -> None:
            await super().save(run_id, thread_id, state, **kwargs)
            if not _armed:
                return
            context = state.context
            if (
                _boundary == "before_dispatch"
                and state.status == "running"
                and state.current_step == "dispatch"
                and isinstance(context.get("pending_decision"), dict)
                and context.get("pending_invocation_started") is True
            ):
                await _block_at_boundary("before_dispatch")
            if (
                _boundary == "after_step"
                and state.status == "running"
                and state.current_step == "model"
                and context.get("pending_decision") is None
                and context.get("pending_invocation_started") is False
            ):
                await _block_at_boundary("after_step")
            if (
                _boundary == "terminal_checkpoint"
                and state.status in {"completed", "failed", "cancelled", "timeout"}
                and state.terminal_result is not None
            ):
                await _block_at_boundary(
                    "terminal_checkpoint",
                    terminal_status=state.status,
                    terminal_result=state.context.get("recovery_terminal_result"),
                )

    class _WorkerEventStore(EventStore):
        async def append(
            self,
            event: RunEvent | AgentRunEvent,
            *,
            event_id: str | None = None,
        ) -> AgentRunEvent:
            stored = await super().append(event, event_id=event_id)
            if (
                _armed
                and _boundary == "terminal_event_committed"
                and event.event_type in {"run.succeeded", "run.failed", "run.cancelled"}
            ):
                await _block_at_boundary(
                    "terminal_event_committed",
                    terminal_event_type=event.event_type,
                    terminal_event_id=stored.event_id,
                    terminal_sequence=stored.sequence,
                    terminal_payload=stored.payload,
                )
            return stored

    class _WorkerIdempotencyStore(SqlIdempotencyStore):
        async def execute_once(self, scope, key, payload_hash, operation):
            result = await super().execute_once(scope, key, payload_hash, operation)
            if _armed and _boundary == "confirmed" and result.status == "executed":
                await _block_at_boundary("confirmed")
            return result

    registry = CapabilityRegistry()
    registry.register(_SyntheticWriteCapability())
    setattr(agent_api, "build_capability_registry", lambda: registry)
    setattr(agent_api, "OpenAIModelGateway", _WorkerGateway)
    setattr(agent_api, "MemoryServiceImpl", lambda **kwargs: _WorkerMemory())
    setattr(agent_api, "SqlMemoryRepository", lambda *args, **kwargs: None)
    setattr(agent_api, "LLMFactExtractor", lambda *args, **kwargs: None)
    setattr(agent_api, "SqlTraceStore", lambda *args, **kwargs: None)
    setattr(agent_api, "SqliteCheckpointStore", _WorkerCheckpointStore)
    setattr(agent_api, "SqlIdempotencyStore", _WorkerIdempotencyStore)
    setattr(agent_api, "EventStore", _WorkerEventStore)

    class _OneToolRunBudget(RunBudget):
        def __init__(self, *values: Any, **kwargs: Any) -> None:
            kwargs.setdefault("max_tool_calls", 1)
            super().__init__(*values, **kwargs)

    setattr(agent_api, "RunBudget", _OneToolRunBudget)
    setattr(
        agent_api,
        "_resolve_provider_base_url",
        lambda value: "http://127.0.0.1:9/v1",
    )
    setattr(agent_api, "_provider_endpoint_policy", lambda: None)

    fastapi_app = FastAPI()
    fastapi_app.include_router(api_router)
    fastapi_app.dependency_overrides[get_session] = override_session
    fastapi_app.dependency_overrides[get_current_user] = override_current_user
    fastapi_app.dependency_overrides[get_optional_user] = override_optional_user

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=fastapi_app),
        base_url="http://fixture.test",
    ) as client:
        if args.mode == "crash":
            response = await client.post(
                "/api/v1/chat",
                json={
                    "model": "checkpoint-kill-fixture",
                    "thread_id": args.thread_id,
                    "messages": [{"role": "user", "content": "commit a test write"}],
                },
                headers={"X-Api-Key": "acceptance-fixture-key"},
            )
            events = _parse_sse(response.text)
            approval = next(
                (event for event in events if event.get("type") == "approval_required"),
                None,
            )
            if response.status_code != 200 or approval is None:
                _emit(
                    kind="startup_failure",
                    status_code=response.status_code,
                    event_types=[event.get("type") for event in events],
                )
                return 2
            _run_id = str(approval["run_id"])
            if not _run_id:
                _emit(kind="startup_failure", reason="approval omitted run id")
                return 2
            _armed = True
            resume = await client.post(
                "/api/v1/chat/resume",
                params={
                    "thread_id": args.thread_id,
                    "run_id": _run_id,
                    "decision": "approve",
                },
                headers={"X-Api-Key": "acceptance-fixture-key"},
            )
            _emit(
                kind="unexpected_return",
                status_code=resume.status_code,
                event_types=[event.get("type") for event in _parse_sse(resume.text)],
                run_id=_run_id,
                thread_id=args.thread_id,
            )
            return 3

        if args.mode == "terminalize":
            _run_id = args.run_id
            _armed = True
            response = await client.post(
                "/api/v1/chat/resume",
                params={
                    "thread_id": args.thread_id,
                    "run_id": args.run_id,
                    "decision": "approve",
                },
                headers={"X-Api-Key": "acceptance-fixture-key"},
            )
            _emit(
                kind="unexpected_terminalize_return",
                status_code=response.status_code,
                event_types=[event.get("type") for event in _parse_sse(response.text)],
                run_id=args.run_id,
                thread_id=args.thread_id,
            )
            return 3

        if args.mode == "reconcile":
            _run_id = args.run_id
            terminal_probes: dict[str, int] = {}
            for probe_user, probe_thread, key in (
                (8, args.thread_id, "cross_owner"),
                (7, f"{args.thread_id}-other", "cross_thread"),
            ):
                active_user_id = probe_user
                probe = await client.get(
                    f"/api/v1/runs/{args.run_id}",
                    params={"thread_id": probe_thread},
                    headers={"X-Api-Key": "acceptance-fixture-key"},
                )
                terminal_probes[key] = probe.status_code
            active_user_id = 7
            with sqlite3.connect(args.app_db) as terminal_db_connection:
                row = terminal_db_connection.execute(
                    "SELECT status FROM agent_run WHERE run_id = ?",
                    (args.run_id,),
                ).fetchone()
            pre_reconcile_status = str(row[0]) if row else None

            first_run = await client.get(
                f"/api/v1/runs/{args.run_id}",
                params={"thread_id": args.thread_id},
                headers={"X-Api-Key": "acceptance-fixture-key"},
            )
            second_run = await client.get(
                f"/api/v1/runs/{args.run_id}",
                params={"thread_id": args.thread_id},
                headers={"X-Api-Key": "acceptance-fixture-key"},
            )
            first_events = await client.get(
                f"/api/v1/runs/{args.run_id}/events",
                params={"thread_id": args.thread_id},
                headers={"X-Api-Key": "acceptance-fixture-key"},
            )
            second_events = await client.get(
                f"/api/v1/runs/{args.run_id}/events",
                params={"thread_id": args.thread_id},
                headers={"X-Api-Key": "acceptance-fixture-key"},
            )
            terminal_resume = await client.post(
                "/api/v1/chat/resume",
                params={
                    "thread_id": args.thread_id,
                    "run_id": args.run_id,
                    "decision": "approve",
                },
                headers={"X-Api-Key": "acceptance-fixture-key"},
            )
            checkpoint_store = _WorkerCheckpointStore(args.checkpoint_db)
            checkpoint = await checkpoint_store.load(
                args.run_id, f"user:7:thread:{args.thread_id}"
            )
            await checkpoint_store.close()
            with sqlite3.connect(args.sink_db) as sink_connection:
                sink_row = sink_connection.execute(
                    "SELECT COUNT(*) FROM synthetic_writes WHERE run_id = ?",
                    (args.run_id,),
                ).fetchone()
            _emit(
                kind="terminal_reconcile_result",
                run_id=args.run_id,
                thread_id=args.thread_id,
                probes=terminal_probes,
                pre_reconcile_status=pre_reconcile_status,
                run_statuses=[first_run.status_code, second_run.status_code],
                runs=[first_run.json(), second_run.json()],
                event_statuses=[first_events.status_code, second_events.status_code],
                event_projections=[first_events.json(), second_events.json()],
                terminal_resume_status=terminal_resume.status_code,
                checkpoint_status=checkpoint.status if checkpoint is not None else None,
                checkpoint_terminal_result=(
                    checkpoint.context.get("recovery_terminal_result")
                    if checkpoint is not None
                    else None
                ),
                model_call_count=_model_call_count,
                capability_call_count=_capability_call_count,
                sink_count=int(sink_row[0]),
            )
            return 0

        _run_id = args.run_id
        recovery_decision = args.decision
        probes: dict[str, int] = {}
        if recovery_decision == "approve":
            for probe_user, probe_thread, key in (
                (8, args.thread_id, "cross_owner"),
                (7, f"{args.thread_id}-other", "cross_thread"),
            ):
                active_user_id = probe_user
                response = await client.post(
                    "/api/v1/chat/resume",
                    params={
                        "thread_id": probe_thread,
                        "run_id": args.run_id,
                        "decision": "approve",
                    },
                    headers={"X-Api-Key": "acceptance-fixture-key"},
                )
                probes[key] = response.status_code
            active_user_id = 7
            continue_response = await client.post(
                "/api/v1/chat/resume",
                params={
                    "thread_id": args.thread_id,
                    "run_id": args.run_id,
                    "decision": "continue",
                },
                headers={"X-Api-Key": "acceptance-fixture-key"},
            )
            probes["continue_pending_write"] = continue_response.status_code

        active_user_id = 7
        response = await client.post(
            "/api/v1/chat/resume",
            params={
                "thread_id": args.thread_id,
                "run_id": args.run_id,
                "decision": recovery_decision,
            },
            headers={"X-Api-Key": "acceptance-fixture-key"},
        )
        events = _parse_sse(response.text)
        replays: list[dict[str, Any]] = []
        replay_statuses: list[int] = []
        for _ in range(2):
            replay = await client.get(
                f"/api/v1/runs/{args.run_id}/events",
                params={"thread_id": args.thread_id},
            )
            replays.append(replay.json())
            replay_statuses.append(replay.status_code)
        replay_sequences = [
            int(event["sequence"]) for event in replays[0].get("events", [])
        ]
        replay_sequences_second = [
            int(event["sequence"]) for event in replays[1].get("events", [])
        ]
        terminal_resume = await client.post(
            "/api/v1/chat/resume",
            params={
                "thread_id": args.thread_id,
                "run_id": args.run_id,
                "decision": recovery_decision,
            },
            headers={"X-Api-Key": "acceptance-fixture-key"},
        )
        sink_count = 0
        with sqlite3.connect(args.sink_db) as sink_read_connection:
            row = sink_read_connection.execute(
                "SELECT COUNT(*) FROM synthetic_writes WHERE run_id = ?",
                (args.run_id,),
            ).fetchone()
            sink_count = int(row[0])
        event_sequences = [
            int(event["sequence"]) for event in events if "sequence" in event
        ]
        _emit(
            kind="recovery_result",
            status_code=response.status_code,
            run_id=args.run_id,
            thread_id=args.thread_id,
            decision=recovery_decision,
            event_types=[event.get("type") for event in events],
            events=events,
            model_saw_tool_result=_feedback_seen,
            probes=probes,
            replay_statuses=replay_statuses,
            replay_sequences=replay_sequences,
            replay_sequences_second=replay_sequences_second,
            event_sequences=event_sequences,
            terminal_resume_status=terminal_resume.status_code,
            sink_count_after_replay=sink_count,
        )
        return 0


def _arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        choices=("crash", "recover", "terminalize", "reconcile"),
        required=True,
    )
    parser.add_argument("--boundary", default="")
    parser.add_argument(
        "--decision", choices=("approve", "continue"), default="approve"
    )
    parser.add_argument("--run-id", default="")
    parser.add_argument("--thread-id", required=True)
    parser.add_argument("--app-db", required=True)
    parser.add_argument("--checkpoint-db", required=True)
    parser.add_argument("--sink-db", required=True)
    parser.add_argument(
        "--terminal-outcome",
        choices=("completed", "cancelled", "timeout", "attention_required"),
        default="completed",
    )
    return parser.parse_args()


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(_main(_arguments()))
    except BaseException:
        raise
    else:
        sys.exit(exit_code)
