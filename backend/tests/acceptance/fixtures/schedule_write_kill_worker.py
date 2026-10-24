"""Real Schedule API/Runtime/SQL worker; only model and external I/O are fake."""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
from typing import Any


def emit(**values: Any) -> None:
    print(json.dumps(values, sort_keys=True), flush=True)


def frames(text: str) -> list[dict]:
    return [
        json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")
    ]


async def main(args: argparse.Namespace) -> int:
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
            "ENABLE_PROACTIVE_SCHEDULER": "false",
            "OPENAI_API_KEY": "synthetic-fixture-key",
            "JWT_SECRET_KEY": "schedule-kill-fixture-only-not-production",
        }
    )
    import httpx
    from datetime import time
    from fastapi import FastAPI
    from fastapi_cache import FastAPICache
    from fastapi_cache.backends.inmemory import InMemoryBackend
    from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
    from sqlmodel import SQLModel
    from sqlmodel.ext.asyncio.session import AsyncSession
    import app.models  # noqa: F401
    from app.api import api_router
    from app.api.v1 import agent as agent_api
    from app.core.security import create_access_token
    from app.db.database import get_session
    from app.harness import execution
    from app.harness.checkpoint import SqliteCheckpointStore
    from app.harness.model_types import ModelCallResult
    from app.harness.persistence.event_store import EventStore
    from app.harness.persistence.idempotency import SqlIdempotencyStore
    from app.models import Schedule, User
    from app.services.schedule_service import ScheduleService
    from app.services.bangumi_client import BangumiClient
    from app.services.bangumi_data_sync import BangumiDataSyncService
    from tests.capabilities.schedule_write_fixtures import (
        calendar_payload,
        metadata_payload,
    )

    FastAPICache.init(InMemoryBackend())
    engine = create_async_engine(f"sqlite+aiosqlite:///{args.app_db}")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    async with factory() as db:
        if await db.get(User, 7) is None:
            db.add_all(
                [
                    User(id=7, username="schedule-kill-owner"),
                    User(id=8, username="schedule-kill-other"),
                ]
            )
            await db.flush()
            for row_id, owner in ((71, 7), (81, 8)):
                db.add(
                    Schedule(
                        id=row_id,
                        user_id=owner,
                        source="bangumi",
                        source_id="701",
                        day_of_week=2,
                        start_time=time(19, 30),
                        watch_type=4,
                    )
                )
            await db.commit()

    with sqlite3.connect(args.audit_db) as audit:
        audit.execute("CREATE TABLE IF NOT EXISTS audit(kind TEXT, action TEXT)")

    def audit_call(kind: str) -> None:
        with sqlite3.connect(args.audit_db) as audit:
            audit.execute(
                "INSERT INTO audit(kind,action) VALUES (?,?)", (kind, args.action)
            )

    transport_calls = 0

    def external(request):
        nonlocal transport_calls
        transport_calls += 1
        audit_call("external")
        if str(request.url) == BangumiClient.CALENDAR_URL:
            return httpx.Response(200, json=calendar_payload(), request=request)
        if str(request.url) == BangumiDataSyncService.DATA_SOURCES[0]:
            return httpx.Response(200, json=metadata_payload(), request=request)
        raise AssertionError("Unplanned external request")

    original_init = httpx.AsyncClient.__init__

    def client_init(client, *values, **options):
        if not isinstance(options.get("transport"), httpx.ASGITransport):
            options["transport"] = httpx.MockTransport(external)
        original_init(client, *values, **options)

    setattr(httpx.AsyncClient, "__init__", client_init)

    armed = False
    current_run = args.run_id
    service_calls = 0

    async def boundary() -> None:
        emit(
            kind="boundary",
            boundary=args.boundary,
            action=args.action,
            run_id=current_run,
            thread_id=args.thread_id,
            service_calls=service_calls,
            external_calls=transport_calls,
        )
        await asyncio.Event().wait()

    method_name = {
        "create_schedule": "create_schedule",
        "update_schedule": "update_schedule",
        "delete_schedule": "delete_schedule",
        "upsert_schedule": "upsert_schedule",
        "bulk_upsert_schedules": "bulk_upsert_schedules",
        "sync_bangumi_schedule": "sync_bangumi_calendar",
    }[args.action]
    original_service = getattr(ScheduleService, method_name)

    async def track_service(*values, **options):
        nonlocal service_calls
        service_calls += 1
        audit_call("service")
        return await original_service(*values, **options)

    setattr(ScheduleService, method_name, track_service)

    class BoundaryEventStore(EventStore):
        async def append(self, event, **options):
            if (
                armed
                and args.boundary == "unknown"
                and event.event_type == "idempotency.result"
            ):
                await boundary()
            return await super().append(event, **options)

    class BoundaryIdempotencyStore(SqlIdempotencyStore):
        async def execute_once(self, scope, key, payload_hash, operation):
            result = await super().execute_once(scope, key, payload_hash, operation)
            if armed and args.boundary == "confirmed" and result.status == "executed":
                await boundary()
            return result

    # The actual SQL implementation remains in place; these subclasses only
    # pause at durable boundaries. No replacement Registry or Capability exists.
    setattr(execution, "SqlIdempotencyStore", BoundaryIdempotencyStore)
    import app.harness.persistence.idempotency as idem_module

    setattr(idem_module, "EventStore", BoundaryEventStore)

    value = {
        "source": "bangumi",
        "source_id": "702",
        "day_of_week": 3,
        "start_time": "20:00:00",
    }
    all_arguments: dict[str, dict[str, Any]] = {
        "create_schedule": value,
        "upsert_schedule": value,
        "update_schedule": {"schedule_id": 71, "day_of_week": 4},
        "delete_schedule": {"schedule_id": 71},
        "bulk_upsert_schedules": {"items": [value]},
        "sync_bangumi_schedule": {},
    }
    business_args = all_arguments[args.action]
    model_calls = 0

    class Gateway:
        def __init__(self, **options):
            self.model = options["model"]

        async def infer(self, **options):
            nonlocal model_calls
            model_calls += 1
            decision: dict[str, Any] = {
                "schema_version": "v1",
                "decision_id": f"schedule-{args.mode}-decision-{model_calls}",
            }
            if args.mode == "crash" and model_calls == 1:
                decision.update(
                    action="invoke",
                    capability=args.action,
                    capability_version="v1",
                    arguments={
                        **business_args,
                        "idempotency_key": "schedule-kill-" + args.action,
                    },
                )
            else:
                decision.update(
                    action="respond", content="Schedule operation completed"
                )
            return ModelCallResult(
                provider="fixture",
                model=self.model,
                operation="infer",
                status="completed",
                decision=decision,
                text=json.dumps(decision),
            )

        async def close(self):
            pass

    class NoMemory:
        last_model_call = None

        async def retrieve_context(self, *values, **options):
            return None

        async def extract_and_store_facts(self, *values, **options):
            return None

    setattr(agent_api, "OpenAIModelGateway", Gateway)
    setattr(agent_api, "MemoryServiceImpl", lambda **options: NoMemory())
    setattr(agent_api, "SqlMemoryRepository", lambda *values, **options: None)
    setattr(agent_api, "LLMFactExtractor", lambda *values, **options: None)
    setattr(
        agent_api, "_resolve_provider_base_url", lambda value: "http://127.0.0.1:9/v1"
    )
    setattr(agent_api, "_provider_endpoint_policy", lambda: None)

    web_app = FastAPI()
    web_app.include_router(api_router)

    async def session_dependency():
        async with factory() as db:
            yield db

    web_app.dependency_overrides[get_session] = session_dependency

    def headers(user_id=7):
        return {
            "X-Api-Key": "synthetic-fixture-key",
            "Authorization": "Bearer " + create_access_token({"sub": str(user_id)}),
        }

    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=web_app), base_url="http://fixture.test"
        ) as client:
            if args.mode == "crash":
                response = await client.post(
                    "/api/v1/chat",
                    headers=headers(),
                    json={
                        "model": "fixture-model",
                        "thread_id": args.thread_id,
                        "messages": [
                            {"role": "user", "content": "Perform the scheduled write"}
                        ],
                    },
                )
                approval = next(
                    (
                        f
                        for f in frames(response.text)
                        if f.get("type") == "approval_required"
                    ),
                    None,
                )
                if response.status_code != 200 or approval is None:
                    emit(
                        kind="startup_failure",
                        status=response.status_code,
                        frames=frames(response.text),
                    )
                    return 2
                current_run = approval["run_id"]
                armed = True
                await client.post(
                    "/api/v1/chat/resume",
                    headers=headers(),
                    params={
                        "thread_id": args.thread_id,
                        "run_id": current_run,
                        "decision": "approve",
                    },
                )
                emit(kind="unexpected_return")
                return 3

            probe = await client.post(
                "/api/v1/chat/resume",
                headers=headers(8),
                params={
                    "thread_id": args.thread_id,
                    "run_id": current_run,
                    "decision": "approve",
                },
            )
            response = await client.post(
                "/api/v1/chat/resume",
                headers=headers(),
                params={
                    "thread_id": args.thread_id,
                    "run_id": current_run,
                    "decision": "approve",
                },
            )
            run = await client.get(f"/api/v1/runs/{current_run}", headers=headers())
            events = await client.get(
                f"/api/v1/runs/{current_run}/events", headers=headers()
            )
            trace = await client.get(f"/api/v1/trace/{current_run}", headers=headers())
            foreign_trace = await client.get(
                f"/api/v1/trace/{current_run}", headers=headers(8)
            )
            repeat = await client.post(
                "/api/v1/chat/resume",
                headers=headers(),
                params={
                    "thread_id": args.thread_id,
                    "run_id": current_run,
                    "decision": "approve",
                },
            )
            checkpoint_store = SqliteCheckpointStore(args.checkpoint_db)
            state = await checkpoint_store.load(
                current_run, f"user:7:thread:{args.thread_id}"
            )
            await checkpoint_store.close()
            emit(
                kind="recovery_result",
                status_code=response.status_code,
                run_id=current_run,
                frames=frames(response.text),
                run_status=run.status_code,
                run=run.json(),
                events_status=events.status_code,
                events=events.json(),
                trace_status=trace.status_code,
                trace=trace.json(),
                foreign_trace_status=foreign_trace.status_code,
                foreign_resume_status=probe.status_code,
                repeat_status=repeat.status_code,
                checkpoint_status=state.status if state else None,
                service_calls=service_calls,
                external_calls=transport_calls,
                model_calls=model_calls,
            )
            return 0
    finally:
        web_app.dependency_overrides.clear()
        await engine.dispose()


def arguments():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=("crash", "recover"), required=True)
    parser.add_argument("--boundary", choices=("confirmed", "unknown"), required=True)
    parser.add_argument("--action", required=True)
    parser.add_argument("--app-db", required=True)
    parser.add_argument("--checkpoint-db", required=True)
    parser.add_argument("--audit-db", required=True)
    parser.add_argument("--thread-id", required=True)
    parser.add_argument("--run-id", default="")
    return parser.parse_args()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main(arguments())))
