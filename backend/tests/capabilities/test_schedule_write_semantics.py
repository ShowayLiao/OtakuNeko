"""Schedule write SQL, commit windows, durable results and action binding."""

from datetime import datetime, time, timezone
import logging
from typing import Any, cast
from unittest.mock import create_autospec
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlmodel import col

from app.capabilities.schedule import ScheduleCapability
from app.capabilities.factory import build_capability_registry
from app.harness.capability_adapter import _payload_hash
from app.harness.contracts import AgentDecision, ExecutionContext
from app.harness.execution import build_runtime
from app.harness.model_gateway import ModelGateway
from app.harness.normalizer import ResultNormalizer, SchemaContractError, validate_input
from app.harness.persistence.event_store import EventStore
from app.harness.policy import Approval
from app.models import Schedule, Subject, User
from app.models import AnimeBroadcastMetadata, Collection
from app.schemas.schedule import (
    ScheduleCreate,
    ScheduleUpdate,
    ScheduleUpsert,
    ScheduleUpsertList,
)
from app.schemas.user import UserRead
from app.services.schedule_service import ScheduleService
from tests.capabilities.schedule_write_fixtures import (
    calendar_payload,
    metadata_payload,
)

WRITES = tuple(d.name for d in ScheduleCapability().actions() if d.is_side_effect)
METHODS = dict(
    zip(
        WRITES,
        (
            "create_schedule",
            "update_schedule",
            "delete_schedule",
            "upsert_schedule",
            "bulk_upsert_schedules",
            "sync_bangumi_calendar",
        ),
    )
)


@pytest.fixture(autouse=True)
def write_dialect(request, monkeypatch):
    if request.node.get_closest_marker("postgres"):
        from app.core.config import settings

        monkeypatch.setattr(settings, "DEPLOY_MODE", "cloud")


async def seed(db):
    users = [
        User(username="schedule-write-owner"),
        User(username="schedule-write-other"),
    ]
    db.add_all(users)
    await db.flush()
    assert users[0].id is not None
    for user in users:
        db.add(
            Schedule(
                user_id=user.id,
                source="bangumi",
                source_id="701",
                day_of_week=2,
                start_time=time(19, 30),
                watch_type=4,
            )
        )
    await db.commit()
    rows = list((await db.execute(select(Schedule))).scalars())
    owner = UserRead(
        id=users[0].id,
        username=users[0].username,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    return (
        owner,
        next(r.id for r in rows if r.user_id == owner.id),
        next(r.id for r in rows if r.user_id != owner.id),
    )


def arguments(action, row_id) -> dict[str, Any]:
    value = {
        "source": "bangumi",
        "source_id": "702",
        "day_of_week": 3,
        "start_time": "20:00:00",
    }
    if action == "update_schedule":
        return {"schedule_id": row_id, "day_of_week": 4}
    if action == "delete_schedule":
        return {"schedule_id": row_id}
    if action == "bulk_upsert_schedules":
        return {"items": [value]}
    if action == "sync_bangumi_schedule":
        return {}
    return value


def runtime(db, user, action):
    return build_runtime(
        session=db,
        user=user,
        registry=build_capability_registry(),
        model_gateway=create_autospec(ModelGateway, instance=True),
        trace_store=None,
        durable=True,
        allow_side_effects=True,
        approval=Approval(approval_id="trusted", principal_id=user.id, action=action),
    )


async def dispatch(db, user, action, key, values):
    control = runtime(db, user, action)
    run_id = uuid4().hex
    return await control.dispatcher.dispatch(
        AgentDecision(
            decision_id=uuid4().hex,
            run_id=run_id,
            action="invoke",
            capability=action,
            capability_version="v1",
            arguments={**values, "idempotency_key": key},
        ),
        ExecutionContext(
            principal_id=user.id,
            run_id=run_id,
            trace_id=run_id,
            capability_allowlist=frozenset({action}),
        ),
    )


async def snapshot(db):
    return [
        r.model_dump(mode="json")
        for r in (
            await db.execute(
                select(Schedule)
                .order_by(col(Schedule.id))
                .execution_options(populate_existing=True)
            )
        ).scalars()
    ]


@pytest.mark.parametrize("action", WRITES)
def test_write_contract_is_closed_and_missing_success_fields_fail(action):
    descriptor = next(d for d in ScheduleCapability().actions() if d.name == action)
    with pytest.raises(SchemaContractError):
        validate_input({**arguments(action, 1), "save": True}, descriptor)
    result = ResultNormalizer().normalize(
        {"success": True},
        descriptor=descriptor,
        run_id="schema",
        decision_id="schema",
        invocation_id="schema",
        trace_id="schema",
    )
    assert result.error_code == "invalid_output"
    assert descriptor.risk_level == "medium"


@pytest.mark.asyncio
@pytest.mark.parametrize("action", WRITES)
async def test_value_error_before_commit_is_safe(action, monkeypatch):
    async def fail(*args):
        raise ValueError("synthetic-private-write-diagnostic")

    monkeypatch.setattr(ScheduleService, METHODS[action], fail)
    result = await ScheduleCapability().execute(
        action, db=object(), user_id=7, **arguments(action, 1)
    )
    assert result["error_type"] == "invalid_args"
    assert "synthetic-private" not in str(result)


@pytest.mark.asyncio
@pytest.mark.parametrize("action", WRITES)
async def test_exception_after_business_commit_requires_verification(
    action, db_session, monkeypatch
):
    user, row_id, _ = await seed(db_session)
    original = getattr(ScheduleService, METHODS[action])
    calls = 0

    async def fail_after_commit(*args):
        nonlocal calls
        calls += 1
        if action == "sync_bangumi_schedule":
            # A real SQL commit isolates handler commit tracking; full domain sync
            # and metadata fallback are exercised separately below.
            db_session.add(Subject(source_id="799", name="Commit sentinel", type=2))
            await db_session.commit()
        else:
            await original(*args)
        raise ValueError("synthetic-private-postcommit-diagnostic")

    monkeypatch.setattr(ScheduleService, METHODS[action], fail_after_commit)
    result = await dispatch(
        db_session, user, action, "postcommit", arguments(action, row_id)
    )
    assert result.error_code == "attention_required", result.model_dump()
    after = await snapshot(db_session)
    replay = await dispatch(
        db_session, user, action, "postcommit", arguments(action, row_id)
    )
    assert replay.error_code == "attention_required"
    assert calls == 1 and await snapshot(db_session) == after


@pytest.mark.asyncio
async def test_same_scope_key_cannot_replay_another_schedule_action(db_session):
    user, row_id, _ = await seed(db_session)
    values = arguments("create_schedule", row_id)
    first = await dispatch(db_session, user, "create_schedule", "cross-action", values)
    assert first.status == "succeeded"
    before = await snapshot(db_session)
    second = await dispatch(db_session, user, "upsert_schedule", "cross-action", values)
    assert second.error_code == "idempotency_conflict", second.model_dump()
    assert await snapshot(db_session) == before


@pytest.mark.asyncio
async def test_legacy_result_without_action_binding_is_reserved(db_session):
    user, row_id, _ = await seed(db_session)
    control = runtime(db_session, user, "delete_schedule")
    values = {"schedule_id": row_id, "idempotency_key": "legacy"}

    async def legacy():
        return {"status": "succeeded", "result": {"success": True, "deleted": True}}

    await control.dispatcher.idempotency_store.execute_once(
        f"{user.id}:schedule:schedule:{row_id}", "legacy", _payload_hash(values), legacy
    )
    before = await snapshot(db_session)
    result = await dispatch(
        db_session, user, "delete_schedule", "legacy", {"schedule_id": row_id}
    )
    assert result.error_code == "attention_required", result.model_dump()
    assert await snapshot(db_session) == before


@pytest.mark.asyncio
async def test_committed_write_without_durable_result_never_executes_again(
    db_session, monkeypatch
):
    user, row_id, _ = await seed(db_session)
    real_append = EventStore.append
    real_update = ScheduleService.update_schedule
    calls = 0

    async def track(*args):
        nonlocal calls
        calls += 1
        return await real_update(*args)

    async def lose(self, event, **kwargs):
        if event.event_type == "idempotency.result":
            raise RuntimeError("synthetic-result-store-fault")
        return await real_append(self, event, **kwargs)

    monkeypatch.setattr(ScheduleService, "update_schedule", track)
    monkeypatch.setattr(EventStore, "append", lose)
    values = arguments("update_schedule", row_id)
    first = await dispatch(db_session, user, "update_schedule", "lost-result", values)
    assert first.error_code == "attention_required", first.model_dump()
    before = await snapshot(db_session)
    monkeypatch.setattr(EventStore, "append", real_append)
    session_factory = async_sessionmaker(db_session.bind, expire_on_commit=False)
    async with session_factory() as recovered:
        result = await dispatch(
            recovered, user, "update_schedule", "lost-result", values
        )
        assert result.error_code == "attention_required"
        assert await snapshot(recovered) == before
    assert calls == 1


async def verify_sql_write(db, action, monkeypatch):
    user, row_id, foreign_id = await seed(db)
    method = getattr(ScheduleService, METHODS[action])
    calls = 0

    async def track(*args):
        nonlocal calls
        calls += 1
        return await method(*args)

    monkeypatch.setattr(ScheduleService, METHODS[action], track)
    before = await snapshot(db)
    foreign_before = next(r for r in before if r["id"] == foreign_id)
    values = arguments(action, row_id)
    first = await dispatch(db, user, action, "sql-replay", values)
    assert first.status == "succeeded", first.model_dump()
    after = await snapshot(db)
    assert next(r for r in after if r["id"] == foreign_id) == foreign_before
    if action == "delete_schedule":
        assert all(r["id"] != row_id for r in after)
    elif action == "update_schedule":
        assert next(r for r in after if r["id"] == row_id)["day_of_week"] == 4
    else:
        assert any(r["user_id"] == user.id and r["source_id"] == "702" for r in after)
    replay = await dispatch(db, user, action, "sql-replay", values)
    assert replay.status == "succeeded" and calls == 1
    assert await snapshot(db) == after
    if action in {"update_schedule", "delete_schedule"}:
        refused = await dispatch(
            db, user, action, "foreign-row", {**values, "schedule_id": foreign_id}
        )
        assert refused.error_code == "not_found"
        assert await snapshot(db) == after


@pytest.mark.asyncio
@pytest.mark.parametrize("action", WRITES[:-1])
async def test_real_sqlite_writes_replay_and_owner_isolation(
    db_session, monkeypatch, action
):
    await verify_sql_write(db_session, action, monkeypatch)


@pytest.mark.asyncio
@pytest.mark.postgres
@pytest.mark.parametrize("action", WRITES[:-1])
async def test_real_postgres_writes_replay_and_owner_isolation(
    postgres_session, monkeypatch, action
):
    await verify_sql_write(postgres_session, action, monkeypatch)


async def verify_calendar(db, external_http, *, fallback):
    from app.services.bangumi_client import BangumiClient
    from app.services.bangumi_data_sync import BangumiDataSyncService

    user, _, _ = await seed(db)
    if not fallback:
        db.add(
            AnimeBroadcastMetadata(
                bangumi_id=799,
                title="Synthetic cached title",
                broadcast_begin=datetime(2026, 10, 20, 12),
                year=2026,
                season=10,
            )
        )
        await db.commit()
    external_http.respond("GET", BangumiClient.CALENDAR_URL, json=calendar_payload())
    if fallback:
        external_http.respond(
            "GET", BangumiDataSyncService.DATA_SOURCES[0], json=metadata_payload()
        )
    before = await snapshot(db)
    first = await dispatch(db, user, "sync_bangumi_schedule", "calendar-replay", {})
    assert first.status == "succeeded", first.model_dump()
    assert first.output["count"] == 1
    assert first.output["schedules"][0]["subject"]["id"] == 0
    assert first.output["schedules"][0]["collection"] is None
    stored = (
        await db.execute(select(Subject).where(col(Subject.source_id) == "799"))
    ).scalar_one()
    assert stored.name == "Synthetic calendar anime" and stored.air_time is not None
    assert await db.get(AnimeBroadcastMetadata, 799) is not None
    assert await snapshot(db) == before
    calls = len(external_http.requests)
    replay = await dispatch(db, user, "sync_bangumi_schedule", "calendar-replay", {})
    assert replay.status == "succeeded"
    assert len(external_http.requests) == calls
    assert await snapshot(db) == before
    assert (await db.execute(select(Collection))).scalars().all() == []


@pytest.mark.asyncio
@pytest.mark.parametrize("fallback", [False, True])
async def test_real_sqlite_calendar_and_metadata_pipeline(
    db_session, external_http, initialized_cache, fallback
):
    await verify_calendar(db_session, external_http, fallback=fallback)


@pytest.mark.asyncio
@pytest.mark.postgres
@pytest.mark.parametrize("fallback", [False, True])
async def test_real_postgres_calendar_and_metadata_pipeline(
    postgres_session, external_http, initialized_cache, fallback
):
    await verify_calendar(postgres_session, external_http, fallback=fallback)


async def verify_metadata_update_timestamps(db: Any, external_http: Any) -> None:
    from app.services.bangumi_data_sync import BangumiDataSyncService

    db.add(
        AnimeBroadcastMetadata(
            bangumi_id=799,
            title="Synthetic cached title",
            broadcast_begin=datetime(2026, 1, 1),
            year=2026,
            season=1,
        )
    )
    await db.commit()
    payload = metadata_payload()
    expected = (
        datetime.fromisoformat(payload["items"][0]["begin"])
        .astimezone(timezone.utc)
        .replace(tzinfo=None)
    )
    external_http.respond("GET", BangumiDataSyncService.DATA_SOURCES[0], json=payload)
    assert await BangumiDataSyncService.fetch_and_sync_recent_data(db) == 1
    db.expire_all()
    stored = await db.get(AnimeBroadcastMetadata, 799)
    assert stored is not None and stored.broadcast_begin == expected
    assert stored.broadcast_begin.tzinfo is stored.updated_at.tzinfo is None
    assert stored.updated_at > datetime(2026, 1, 1)


@pytest.mark.asyncio
async def test_sqlite_existing_metadata_updates_use_utc_naive_timestamps(
    db_session, external_http
):
    await verify_metadata_update_timestamps(db_session, external_http)


@pytest.mark.asyncio
@pytest.mark.postgres
async def test_postgres_existing_metadata_updates_use_utc_naive_timestamps(
    postgres_session, external_http
):
    await verify_metadata_update_timestamps(postgres_session, external_http)


@pytest.mark.asyncio
@pytest.mark.parametrize("action", WRITES[:-1])
async def test_service_repository_write_logs_do_not_include_sql_diagnostics(
    action, monkeypatch, caplog
):
    from app.repositories import schedule_repo
    from app.services import schedule_service

    class BrokenSession:
        def add(self, value: Any) -> None:
            raise SQLAlchemyError("synthetic-private-sql-write")

        async def execute(self, *args: Any, **kwargs: Any) -> None:
            raise SQLAlchemyError("synthetic-private-sql-write")

        async def rollback(self) -> None:
            pass

    value: dict[str, Any] = dict(
        source="bangumi",
        source_id="701",
        day_of_week=2,
        start_time=time(19, 30),
        user_id=7,
    )
    update_value: dict[str, Any] = {"day_of_week": 3}
    inputs = {
        "create_schedule": (ScheduleCreate(**value),),
        "update_schedule": (1, ScheduleUpdate(**update_value)),
        "delete_schedule": (1,),
        "upsert_schedule": (ScheduleUpsert(**value),),
        "bulk_upsert_schedules": (ScheduleUpsertList(items=[ScheduleUpsert(**value)]),),
    }
    broken_session = cast(AsyncSession, BrokenSession())
    loggers = (schedule_repo.logger, schedule_service.logger)
    for logger in loggers:
        logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.ERROR):
            if action in {"update_schedule", "delete_schedule"}:
                await getattr(ScheduleService, METHODS[action])(
                    broken_session, 1, 7, *inputs[action][1:]
                )
            else:
                await getattr(ScheduleService, METHODS[action])(
                    broken_session, 7, *inputs[action]
                )
    except SQLAlchemyError:
        pass
    finally:
        for logger in loggers:
            logger.removeHandler(caplog.handler)
    assert len(caplog.records) >= 2
    assert all(
        "synthetic-private" not in repr(r.__dict__) and r.exc_info is None
        for r in caplog.records
    )


@pytest.mark.asyncio
async def test_calendar_http_failure_does_not_log_response_or_exception(
    db_session, external_http, initialized_cache, caplog
):
    from app.services import bangumi_client, bangumi_service, schedule_service

    user, _, _ = await seed(db_session)
    external_http.respond(
        "GET",
        bangumi_client.BangumiClient.CALENDAR_URL,
        json={"private": "synthetic-private-calendar-response"},
        status=503,
    )
    loggers = (bangumi_client.logger, bangumi_service.logger, schedule_service.logger)
    for logger in loggers:
        logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.ERROR):
            result = await dispatch(
                db_session, user, "sync_bangumi_schedule", "calendar-error", {}
            )
    finally:
        for logger in loggers:
            logger.removeHandler(caplog.handler)
    assert result.status == "failed"
    assert len(caplog.records) >= 3
    assert all(
        "synthetic-private" not in repr(r.__dict__) and r.exc_info is None
        for r in caplog.records
    )
