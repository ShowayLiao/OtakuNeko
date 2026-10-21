"""Real SQL write outcomes and durable replay across Runtime construction."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import json
import logging
from uuid import uuid4
from unittest.mock import create_autospec
from copy import deepcopy

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.capabilities import collections as boundary
from app.capabilities.collections import CollectionCapability
from app.capabilities.factory import build_capability_registry
from app.harness.contracts import AgentDecision, ExecutionContext
from app.harness.execution import build_runtime
from app.harness.model_gateway import ModelGateway
from app.harness.normalizer import ResultNormalizer, SchemaContractError, validate_input
from app.harness.policy import Approval
from app.harness.capability_adapter import _payload_hash
from app.harness.persistence.event_store import EventStore
from app.models import Collection, Subject, User
from app.services import (
    collection_service,
    subject_service,
    bangumi_service,
    douban_service,
)
from app.repositories import collection_repo, subject_repo
from app.schemas.user import UserRead

WRITES = tuple(d.name for d in CollectionCapability().actions() if d.is_side_effect)


@pytest.fixture(autouse=True)
def _postgres_write_configuration(request, monkeypatch):
    # The opt-in session selects the database; repositories also select their
    # INSERT dialect from the deployment mode used by the real cloud path.
    if request.node.get_closest_marker("postgres"):
        from app.core.config import settings

        monkeypatch.setattr(settings, "DEPLOY_MODE", "cloud")


async def _seed(db):
    owners = [User(username="write-owner"), User(username="write-foreign")]
    db.add_all(owners)
    await db.flush()
    db.add(
        Subject(source="bangumi", source_id="701", name="Synthetic owned anime", type=2)
    )
    for owner in owners:
        db.add(
            Collection(
                user_id=owner.id,
                source="bangumi",
                source_id="701",
                type=3,
                rate=2,
                private=True,
                comment=f"private-{owner.id}",
            )
        )
    await db.commit()
    assert owners[0].id is not None
    return UserRead(
        id=owners[0].id,
        username=owners[0].username,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


def _runtime(db, user, action):
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


async def _dispatch(runtime, user, action, key, **arguments):
    run_id = uuid4().hex
    return await runtime.dispatcher.dispatch(
        AgentDecision(
            decision_id=uuid4().hex,
            run_id=run_id,
            action="invoke",
            capability=action,
            capability_version="v1",
            arguments={**arguments, "idempotency_key": key},
        ),
        ExecutionContext(
            principal_id=user.id,
            run_id=run_id,
            trace_id=run_id,
            capability_allowlist=frozenset({action}),
        ),
    )


async def _snapshot(db):
    return [
        row.model_dump(mode="json")
        for row in (
            await db.execute(
                select(Collection).execution_options(populate_existing=True)
            )
        ).scalars()
    ]


@pytest.mark.parametrize("action", WRITES)
def test_write_schema_rejects_unknown_parameters_and_missing_output(action):
    descriptor = next(d for d in CollectionCapability().actions() if d.name == action)
    assert descriptor.input_schema.get("additionalProperties") is False
    result = ResultNormalizer().normalize(
        {"success": True},
        descriptor=descriptor,
        run_id="schema",
        decision_id="decision",
        invocation_id="invocation",
        trace_id="schema",
    )
    assert result.status == "failed"


@pytest.mark.parametrize("action", WRITES)
@pytest.mark.asyncio
async def test_precommit_value_error_diagnostic_is_safe(action, monkeypatch):
    async def fail(**kwargs):
        raise ValueError("synthetic-private-write-diagnostic")

    method = {
        "create_collection": "_create",
        "update_collection": "_update",
        "delete_collection": "_delete",
        "upsert_collection": "_upsert",
        "batch_upsert_collections": "_batch_upsert",
        "import_json_collections": "_import_json",
        "sync_bangumi_collections": "_sync_bangumi",
        "sync_douban_collections": "_sync_douban",
    }[action]
    capability = CollectionCapability()
    monkeypatch.setattr(capability, method, fail)
    result = await capability.execute(action, db=object(), user_id=7)
    assert result["error_type"] == "invalid_args"
    assert "synthetic-private" not in json.dumps(result)


@pytest.mark.asyncio
async def test_real_create_has_server_timestamp_and_durable_replay(
    db_session, initialized_cache
):
    user = await _seed(db_session)
    arguments = {"source": "bangumi", "source_id": "702", "type": 3}
    first = await _dispatch(
        _runtime(db_session, user, "create_collection"),
        user,
        "create_collection",
        "create-real",
        **arguments,
    )
    assert first.status == "succeeded", first.model_dump()
    rows = await _snapshot(db_session)
    created = [row for row in rows if row["source_id"] == "702"]
    assert len(created) == 1 and created[0]["updated_at"] is not None
    factory = async_sessionmaker(
        db_session.bind, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as fresh:
        replay = await _dispatch(
            _runtime(fresh, user, "create_collection"),
            user,
            "create_collection",
            "create-real",
            **arguments,
        )
        assert replay.status == "succeeded"
        assert await _snapshot(fresh) == rows


async def _verify_commit_window(db, monkeypatch):
    user = await _seed(db)
    original = boundary.update_collection
    entered, cleaned = asyncio.Event(), asyncio.Event()
    calls = 0

    async def commit_then_block(*args, **kwargs):
        nonlocal calls
        calls += 1
        result = await original(*args, **kwargs)
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()
        return result

    actions = CollectionCapability.actions
    assert db.bind is not None
    timeout = 2.0 if db.bind.dialect.name == "postgresql" else 0.1
    monkeypatch.setattr(
        CollectionCapability,
        "actions",
        lambda self: [
            replace(d, timeout_seconds=timeout) if d.name == "update_collection" else d
            for d in actions(self)
        ],
    )
    monkeypatch.setattr(boundary, "update_collection", commit_then_block)
    arguments = {"source": "bangumi", "source_id": "701", "rate": 9}
    result = await _dispatch(
        _runtime(db, user, "update_collection"),
        user,
        "update_collection",
        "commit-window",
        **arguments,
    )
    assert result.status == "timeout" and not result.retryable
    assert entered.is_set() and cleaned.is_set() and calls == 1
    factory = async_sessionmaker(db.bind, class_=AsyncSession, expire_on_commit=False)
    async with factory() as fresh:
        before = await _snapshot(fresh)
        assert next(row for row in before if row["user_id"] == user.id)["rate"] == 9
        assert next(row for row in before if row["user_id"] != user.id)["rate"] == 2
        replay = await _dispatch(
            _runtime(fresh, user, "update_collection"),
            user,
            "update_collection",
            "commit-window",
            **arguments,
        )
        assert replay.error_code == "attention_required", replay.model_dump()
        assert not replay.retryable and calls == 1
        assert await _snapshot(fresh) == before


@pytest.mark.asyncio
async def test_commit_then_timeout_reopens_into_verification(
    db_session, initialized_cache, monkeypatch
):
    await _verify_commit_window(db_session, monkeypatch)


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_commit_then_timeout_reopens_into_verification_postgres(
    postgres_session, initialized_cache, monkeypatch
):
    await _verify_commit_window(postgres_session, monkeypatch)


@pytest.mark.asyncio
async def test_commit_then_exception_requires_verification_not_known_failure(
    db_session, initialized_cache, monkeypatch
):
    user = await _seed(db_session)
    original = boundary.update_collection
    calls = 0

    async def commit_then_fail(*args, **kwargs):
        nonlocal calls
        calls += 1
        await original(*args, **kwargs)
        raise RuntimeError("synthetic-private-after-commit")

    monkeypatch.setattr(boundary, "update_collection", commit_then_fail)
    arguments = {"source": "bangumi", "source_id": "701", "rate": 9}
    first = await _dispatch(
        _runtime(db_session, user, "update_collection"),
        user,
        "update_collection",
        "post-commit-failure",
        **arguments,
    )
    assert first.error_code == "attention_required", first.model_dump()
    factory = async_sessionmaker(
        db_session.bind, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as fresh:
        before = await _snapshot(fresh)
        assert next(row for row in before if row["user_id"] == user.id)["rate"] == 9
        replay = await _dispatch(
            _runtime(fresh, user, "update_collection"),
            user,
            "update_collection",
            "post-commit-failure",
            **arguments,
        )
        assert replay.error_code == "attention_required" and calls == 1
        assert await _snapshot(fresh) == before


def test_nested_batch_identity_and_unknown_write_parameters_are_rejected():
    descriptor = next(
        d
        for d in CollectionCapability().actions()
        if d.name == "batch_upsert_collections"
    )
    for extra in ({"save": True}, {"user_id": 999}):
        with pytest.raises(SchemaContractError):
            validate_input(
                {"items": [{"source": "bangumi", "source_id": "701", **extra}]},
                descriptor,
            )


@pytest.mark.asyncio
async def test_same_key_and_payload_cannot_replay_another_write_action(
    db_session, initialized_cache
):
    user = await _seed(db_session)
    arguments = {"source": "bangumi", "source_id": "701"}
    updated = await _dispatch(
        _runtime(db_session, user, "update_collection"),
        user,
        "update_collection",
        "cross-action",
        **arguments,
    )
    assert updated.status == "succeeded"
    deleted = await _dispatch(
        _runtime(db_session, user, "delete_collection"),
        user,
        "delete_collection",
        "cross-action",
        **arguments,
    )
    assert deleted.error_code == "idempotency_conflict", deleted.model_dump()
    assert len(await _snapshot(db_session)) == 2


@pytest.mark.asyncio
async def test_legacy_collection_result_without_action_binding_needs_verification(
    db_session, initialized_cache
):
    user = await _seed(db_session)
    runtime = _runtime(db_session, user, "delete_collection")
    arguments = {
        "source": "bangumi",
        "source_id": "701",
        "idempotency_key": "legacy-action",
    }

    async def legacy_operation():
        return {"status": "succeeded", "result": {"success": True, "deleted": True}}

    await runtime.dispatcher.idempotency_store.execute_once(
        f"{user.id}:collections:collection:bangumi:701",
        "legacy-action",
        _payload_hash(arguments),
        legacy_operation,
    )
    before = await _snapshot(db_session)
    result = await _dispatch(
        runtime,
        user,
        "delete_collection",
        "legacy-action",
        source="bangumi",
        source_id="701",
    )
    assert result.error_code == "attention_required", result.model_dump()
    assert await _snapshot(db_session) == before


@pytest.mark.asyncio
async def test_missing_durable_result_after_commit_never_reexecutes(
    db_session, initialized_cache, monkeypatch
):
    user = await _seed(db_session)
    original_append = EventStore.append
    original_update = boundary.update_collection
    calls = 0

    async def track(*args, **kwargs):
        nonlocal calls
        calls += 1
        return await original_update(*args, **kwargs)

    async def lose_result(self, event):
        if event.event_type == "idempotency.result":
            raise RuntimeError("synthetic-result-persistence-interruption")
        return await original_append(self, event)

    monkeypatch.setattr(boundary, "update_collection", track)
    monkeypatch.setattr(EventStore, "append", lose_result)
    arguments = {"source": "bangumi", "source_id": "701", "rate": 9}
    first = await _dispatch(
        _runtime(db_session, user, "update_collection"),
        user,
        "update_collection",
        "lost-result",
        **arguments,
    )
    assert first.status == "failed" and first.error_code == "attention_required"
    factory = async_sessionmaker(
        db_session.bind, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as fresh:
        before = await _snapshot(fresh)
        assert next(row for row in before if row["user_id"] == user.id)["rate"] == 9
        replay = await _dispatch(
            _runtime(fresh, user, "update_collection"),
            user,
            "update_collection",
            "lost-result",
            **arguments,
        )
        assert replay.error_code == "attention_required" and not replay.retryable
        assert calls == 1 and await _snapshot(fresh) == before


@pytest.mark.asyncio
async def test_partial_import_commit_is_classified_for_verification(
    db_session, initialized_cache, monkeypatch
):
    user = await _seed(db_session)

    async def fail_collection_phase(*args, **kwargs):
        raise RuntimeError("synthetic-private-import-second-phase")

    monkeypatch.setattr(
        collection_service, "batch_upsert_collections", fail_collection_phase
    )
    data = {
        "data": [
            {
                "subject_id": 703,
                "type": 3,
                "subject_type": 2,
                "subject": {
                    "id": 703,
                    "name": "Synthetic partially committed subject",
                    "type": 2,
                },
            }
        ]
    }
    first = await _dispatch(
        _runtime(db_session, user, "import_json_collections"),
        user,
        "import_json_collections",
        "partial-import",
        data=data,
    )
    assert first.error_code == "attention_required", first.model_dump()
    subject = (
        await db_session.execute(select(Subject).where(Subject.source_id == "703"))
    ).scalar_one()
    assert subject.name == "Synthetic partially committed subject"
    assert not any(row["source_id"] == "703" for row in await _snapshot(db_session))
    replay = await _dispatch(
        _runtime(db_session, user, "import_json_collections"),
        user,
        "import_json_collections",
        "partial-import",
        data=data,
    )
    assert replay.error_code == "attention_required"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "action",
    [
        "create_collection",
        "update_collection",
        "delete_collection",
        "upsert_collection",
        "batch_upsert_collections",
        "import_json_collections",
        "sync_bangumi_collections",
        "sync_douban_collections",
    ],
)
async def test_real_write_failure_logs_are_safe(
    action, db_session, initialized_cache, monkeypatch, caplog
):
    user = await _seed(db_session)

    async def fail(*args, **kwargs):
        raise SQLAlchemyError("synthetic-private-write-sql-diagnostic")

    if action == "create_collection":
        monkeypatch.setattr(db_session, "commit", fail)
    else:
        monkeypatch.setattr(db_session, "execute", fail)
    loggers = (
        boundary.logger,
        collection_service.logger,
        collection_repo.logger,
        subject_service.logger,
        subject_repo.logger,
        bangumi_service.logger,
        douban_service.logger,
    )
    for logger in loggers:
        logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.ERROR):
            arguments = {"source": "bangumi", "source_id": "701", "type": 3}
            if action == "batch_upsert_collections":
                arguments = {"items": [arguments]}
            elif action == "import_json_collections":
                arguments = {
                    "data": {
                        "data": [
                            {
                                "subject_id": 703,
                                "type": 3,
                                "subject": {
                                    "id": 703,
                                    "type": 2,
                                    "name": "Synthetic subject",
                                },
                            }
                        ]
                    }
                }
            elif action == "sync_douban_collections":
                arguments = {
                    "data": [
                        {
                            "interest": {
                                "status": "done",
                                "subject": {
                                    "id": "703",
                                    "type": "book",
                                    "title": "Synthetic book",
                                },
                            }
                        }
                    ]
                }
            result = await CollectionCapability().execute(
                action, db=db_session, user_id=user.id, user=user, **arguments
            )
    finally:
        for logger in loggers:
            logger.removeHandler(caplog.handler)
    assert result["success"] is False
    records = [
        record
        for record in caplog.records
        if record.name in {logger.name for logger in loggers}
    ]
    assert records
    assert all(
        "synthetic-private-write-sql" not in repr(record.__dict__)
        and record.exc_info is None
        for record in records
    )


@pytest.mark.postgres
@pytest.mark.asyncio
@pytest.mark.parametrize("action", WRITES)
async def test_all_real_write_services_persist_and_replay_postgres(
    action, postgres_session, initialized_cache, monkeypatch
):
    from tests.api import test_collections_write_certification as support

    owners = await support._seed(postgres_session)
    owner, foreign = owners
    assert owner.id is not None and foreign.id is not None
    user = UserRead(
        id=owner.id,
        username=owner.username,
        bangumi_name=owner.bangumi_name,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    calls, _, active_response = support._install_service_counters(action, monkeypatch)
    arguments = support._arguments(action, "approved")
    if action == "sync_bangumi_collections":
        active_response["value"] = arguments.pop("_synthetic_bangumi_response")
    before = await support._business_snapshot(postgres_session)
    result = await _dispatch(
        _runtime(postgres_session, user, action),
        user,
        action,
        "real-pg-replay",
        **arguments,
    )
    assert result.status == "succeeded", result.model_dump()
    after = await support._business_snapshot(postgres_session)
    support._assert_business_write(
        action, "approved", owner.id, foreign.id, before, after
    )
    factory = async_sessionmaker(
        postgres_session.bind, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as fresh:
        replay = await _dispatch(
            _runtime(fresh, user, action), user, action, "real-pg-replay", **arguments
        )
        assert replay.status == "succeeded", replay.model_dump()
        assert calls == [action]
        assert await support._business_snapshot(fresh) == after
        if action != "delete_collection":
            changed = deepcopy(arguments)
            if action in {
                "create_collection",
                "update_collection",
                "upsert_collection",
            }:
                changed["rate"] = 1
            elif action == "batch_upsert_collections":
                changed["items"][0]["rate"] = 1
            elif action == "import_json_collections":
                changed["data"]["data"][0]["rate"] = 1
            elif action == "sync_bangumi_collections":
                changed["limit"] = 1
            else:
                changed["data"][0]["interest"]["rating"]["value"] = 1
            conflict = await _dispatch(
                _runtime(fresh, user, action), user, action, "real-pg-replay", **changed
            )
            assert conflict.error_code == "idempotency_conflict", conflict.model_dump()
            assert (
                calls == [action] and await support._business_snapshot(fresh) == after
            )


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_post_commit_exception_is_unknown_postgres(
    postgres_session, initialized_cache, monkeypatch
):
    await test_commit_then_exception_requires_verification_not_known_failure(
        postgres_session, initialized_cache, monkeypatch
    )


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_missing_result_is_unknown_postgres(
    postgres_session, initialized_cache, monkeypatch
):
    await test_missing_durable_result_after_commit_never_reexecutes(
        postgres_session, initialized_cache, monkeypatch
    )


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_partial_import_requires_verification_postgres(
    postgres_session, initialized_cache, monkeypatch
):
    await test_partial_import_commit_is_classified_for_verification(
        postgres_session, initialized_cache, monkeypatch
    )
