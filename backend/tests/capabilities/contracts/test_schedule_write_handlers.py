"""Real Schedule write handlers under dispatch, authority, and recovery probes."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import time
import json
import logging
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.capabilities import schedule as schedule_module
from app.harness.authority import RUNTIME_OWNED_FIELDS
from app.harness.budget import CancellationToken
from app.harness.capability_adapter import CapabilityAdapter, _payload_hash
from app.harness.contracts import InvocationResult
from app.harness.normalizer import validate_input
from app.harness.persistence.idempotency import SqlIdempotencyStore
from app.harness.policy import Approval
from app.models import Schedule
from app.models.agent_run import AgentInvocation, AgentRunEvent
from app.models.enums import SubjectType, WatchType
from app.schemas.adaptersV2 import UnifiedCollectionSubject, UnifiedList
from app.schemas.subject import SubjectRead
from tests.capabilities.contracts.plugin import record
from tests.capabilities.contracts.schedule_write_support import (
    ScheduleWriteExecution,
    assert_trusted_service_call,
    install_schedule_service_boundary,
    make_write_execution,
    schedule_write_parameters,
)

_ERROR_SENTINEL = "schedule-write-private-diagnostic-sentinel"
_OUTPUT_SENTINEL = "schedule-write-private-output-sentinel"


class _UnsafeValue:
    def __repr__(self) -> str:
        return _OUTPUT_SENTINEL


def _assert_schema_has_no_runtime_identity(schema: Any) -> None:
    if isinstance(schema, dict):
        assert not (set(schema.get("properties", {})) & RUNTIME_OWNED_FIELDS)
        assert not (set(schema.get("required", [])) & RUNTIME_OWNED_FIELDS)
        for value in schema.values():
            _assert_schema_has_no_runtime_identity(value)
    elif isinstance(schema, list):
        for value in schema:
            _assert_schema_has_no_runtime_identity(value)


def _assert_json_safe(result: InvocationResult) -> None:
    encoded = json.dumps(result.model_dump(mode="json"), allow_nan=False)
    assert InvocationResult.model_validate(json.loads(encoded)) == result


def _business_output(result: InvocationResult) -> dict[str, Any]:
    runtime_fields = {
        "run_id",
        "decision_id",
        "invocation_id",
        "trace_id",
        "sequence",
        "latency_ms",
    }
    return {
        key: value for key, value in result.output.items() if key not in runtime_fields
    }


def _assert_success(
    execution: ScheduleWriteExecution, result: InvocationResult
) -> None:
    assert result.status == "succeeded", result.model_dump()
    assert result.error_code is None
    assert result.retryable is False
    assert result.output["success"] is True
    _assert_json_safe(result)

    action = execution.key[0]
    if action in {"create_schedule", "update_schedule", "upsert_schedule"}:
        schedule = result.output["schedule"]
        assert type(schedule["id"]) is int
        assert schedule["source"] == "bangumi"
        assert type(schedule["watch_type"]) is int
        assert time.fromisoformat(schedule["start_time"])
        assert WatchType(schedule["watch_type"])
    elif action == "delete_schedule":
        assert result.output["deleted"] is True
        assert type(result.output["deleted"]) is bool
    elif action == "bulk_upsert_schedules":
        schedules = result.output["schedules"]
        assert type(result.output["count"]) is int
        assert result.output["count"] == len(schedules)
        assert schedules
        assert type(schedules[0]["watch_type"]) is int
        assert time.fromisoformat(schedules[0]["start_time"])
        assert WatchType(schedules[0]["watch_type"])
    elif action == "sync_bangumi_schedule":
        schedules = result.output["schedules"]
        assert type(result.output["count"]) is int
        assert result.output["count"] == len(schedules)
        if schedules:
            assert set(schedules[0]) == {"subject", "collection"}
            assert schedules[0]["subject"]["id"] == 0
            assert schedules[0]["collection"] is None
            assert "schedule" not in schedules[0]


def _assert_rejected(
    result: InvocationResult, expected_codes: set[str] | None = None
) -> None:
    assert result.status in {"denied", "failed", "cancelled", "timeout"}, (
        result.model_dump()
    )
    if expected_codes is not None:
        assert result.error_code in expected_codes, result.model_dump()
    _assert_json_safe(result)


def _sync_success(execution: ScheduleWriteExecution) -> UnifiedList:
    """Mirror ScheduleService.sync_bangumi_calendar's actual result shape."""
    item = UnifiedCollectionSubject(
        subject=SubjectRead(
            id=0,
            name="Synthetic calendar subject",
            name_cn="合成日历条目",
            type=SubjectType.ANIME,
            source="bangumi",
            source_id=execution.source_id,
            summary="Synthetic subject for schedule write contracts",
        ),
        collection=None,
    )
    return UnifiedList(items=[item], total=1)


def _valid_service_result(execution: ScheduleWriteExecution) -> Any:
    """Return a model-shaped result without replacing the registered handler."""
    action = execution.key[0]
    if action == "delete_schedule":
        return True
    if action == "sync_bangumi_schedule":
        return _sync_success(execution)
    row = Schedule(
        id=execution.env.schedule_id,
        source="bangumi",
        source_id=execution.source_id,
        day_of_week=2,
        start_time=time(19, 30),
        watch_day=3,
        watch_time=time(21, 0),
        duration=7,
        user_id=execution.user.id,
        watch_type=WatchType.NEW,
    )
    if action == "bulk_upsert_schedules":
        return [row]
    return row


def _output_variant(execution: ScheduleWriteExecution, variant: str) -> Any:
    action = execution.key[0]
    if action == "delete_schedule":
        return True
    if variant == "unsafe_object":
        unsafe = _UnsafeValue()
        if action == "bulk_upsert_schedules":
            return [unsafe]
        if action == "sync_bangumi_schedule":
            return {"items": [unsafe], "total": 1}
        return unsafe

    if action == "sync_bangumi_schedule":
        if variant == "nan":
            return {
                "items": [
                    {
                        "subject": {
                            "id": 0,
                            "name": "Synthetic subject",
                            "source": "bangumi",
                            "source_id": execution.source_id,
                            "rating": float("nan"),
                        },
                        "collection": None,
                    }
                ],
                "total": 1,
            }
        return {"items": [{"subject": {"id": 0}, "collection": None}], "total": 1}

    if action == "bulk_upsert_schedules":
        if variant == "nan":
            return [
                {
                    "id": execution.env.schedule_id,
                    "source": "bangumi",
                    "source_id": execution.source_id,
                    "day_of_week": 2,
                    "start_time": "19:30:00",
                    "watch_type": int(WatchType.NEW),
                    "untrusted_number": float("nan"),
                }
            ]
        return [
            {
                "id": None,
                "source": "bangumi",
                "source_id": execution.source_id,
                "day_of_week": 2,
                "start_time": "19:30:00",
                "watch_type": int(WatchType.NEW),
            }
        ]

    if variant == "nan":
        return {
            "id": execution.env.schedule_id,
            "source": "bangumi",
            "source_id": execution.source_id,
            "day_of_week": 2,
            "start_time": "19:30:00",
            "watch_type": int(WatchType.NEW),
            "untrusted_number": float("nan"),
        }
    return Schedule(
        id=None,
        source="bangumi",
        source_id=execution.source_id,
        day_of_week=2,
        start_time=time(19, 30),
        user_id=execution.user.id,
        watch_type=WatchType.NEW,
    )


async def _row_by_id(execution: ScheduleWriteExecution, schedule_id: int):
    result = await execution.db.execute(
        select(Schedule)
        .where(cast(Any, Schedule.id) == schedule_id)
        .execution_options(populate_existing=True)
    )
    return result.scalars().first()


def _dispatcher_for_action(
    execution: ScheduleWriteExecution, action: str, *, user=None
):
    return execution.make_dispatcher(
        user=user,
        approval=Approval(
            approval_id=uuid4().hex,
            principal_id=(user or execution.user).id,
            action=action,
        ),
        use_default_approval=False,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("key", schedule_write_parameters("schedule_write_error"))
async def test_schedule_write_errors_are_safe(
    key, db_session, monkeypatch, caplog, request
):
    execution = await make_write_execution(key, db_session)
    behavior: dict[str, Any] = {"current": None}

    async def route(*args, **kwargs):
        return await behavior["current"](*args, **kwargs)

    boundary = install_schedule_service_boundary(execution, monkeypatch, handler=route)

    async def fail_value_error(*args, **kwargs):
        raise ValueError(_ERROR_SENTINEL)

    behavior["current"] = fail_value_error
    invalid = await execution.dispatch(idempotency_key=uuid4().hex)
    assert invalid.status == "failed" and invalid.error_code == "invalid_args"
    assert invalid.retryable is False
    assert _ERROR_SENTINEL not in json.dumps(
        invalid.model_dump(mode="json"), allow_nan=False
    )
    assert len(boundary.calls) == 1 and boundary.unexpected_calls == []

    async def fail_runtime_error(*args, **kwargs):
        raise RuntimeError(_ERROR_SENTINEL)

    behavior["current"] = fail_runtime_error
    logger = schedule_module.logger
    logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.ERROR, logger=logger.name):
            internal = await execution.dispatch(idempotency_key=uuid4().hex)
    finally:
        logger.removeHandler(caplog.handler)

    assert internal.status == "failed" and internal.error_code == "internal"
    assert internal.retryable is False
    assert _ERROR_SENTINEL not in json.dumps(
        internal.model_dump(mode="json"), allow_nan=False
    )
    assert len(boundary.calls) == 2 and boundary.unexpected_calls == []
    records = [item for item in caplog.records if item.name == logger.name]
    assert len(records) == 1
    assert records[0].getMessage() == "schedule_capability_failed"
    assert records[0].action == execution.descriptor.name
    assert records[0].error_type == "RuntimeError"
    assert records[0].exc_info is None
    assert _ERROR_SENTINEL not in repr(records[0].__dict__)
    record(request, key, "schedule_write_error")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", schedule_write_parameters("schedule_write_timeout"))
async def test_schedule_write_timeout_and_cancel_reserve_unknown_keys(
    key, db_session, monkeypatch, request
):
    execution = await make_write_execution(key, db_session)
    entered = [asyncio.Event(), asyncio.Event()]
    cleaned = [asyncio.Event(), asyncio.Event()]
    calls = 0

    async def block_timeout_and_cancel(*args, **kwargs):
        nonlocal calls
        assert_trusted_service_call(execution, args, kwargs)
        calls += 1
        if calls <= 2:
            index = calls - 1
            entered[index].set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaned[index].set()
        return _valid_service_result(execution)

    boundary = install_schedule_service_boundary(
        execution, monkeypatch, handler=block_timeout_and_cancel
    )
    original_descriptors = execution.capability.actions()
    descriptors = [
        replace(descriptor, timeout_seconds=0.1)
        if descriptor.name == execution.descriptor.name
        else descriptor
        for descriptor in original_descriptors
    ]
    monkeypatch.setattr(execution.capability, "actions", lambda: descriptors)
    execution.dispatcher.registry.unregister(execution.capability.name)
    execution.dispatcher.registry.register(execution.capability)

    controls = execution.dispatcher._run_with_controls

    async def arm_timeout(operation, timeout_seconds, cancellation):
        task = asyncio.create_task(operation)
        try:
            await asyncio.wait_for(entered[0].wait(), timeout=5)
            return await controls(task, timeout_seconds, cancellation)
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    monkeypatch.setattr(execution.dispatcher, "_run_with_controls", arm_timeout)

    timeout_key = "schedule-timeout-" + uuid4().hex
    timed_out = await execution.dispatch(idempotency_key=timeout_key)
    assert entered[0].is_set() and cleaned[0].is_set()
    assert timed_out.status == "timeout" and timed_out.error_code == "timeout"
    assert timed_out.retryable is False
    assert len(boundary.calls) == calls == 1

    # The short deadline belongs to the blocked-operation probe. Recovery and
    # cancellation use the actual action deadline, including SQL persistence.
    monkeypatch.setattr(execution.dispatcher, "_run_with_controls", controls)
    monkeypatch.setattr(execution.capability, "actions", lambda: original_descriptors)
    execution.dispatcher.registry.unregister(execution.capability.name)
    execution.dispatcher.registry.register(execution.capability)

    old_timeout_key = await execution.dispatch(idempotency_key=timeout_key)
    _assert_rejected(old_timeout_key, {"attention_required"})
    assert calls == 1

    cancellation = CancellationToken()
    cancel_key = "schedule-cancel-" + uuid4().hex
    cancel_task = asyncio.create_task(
        execution.dispatch(
            idempotency_key=cancel_key,
            cancellation=cancellation,
        )
    )
    try:
        await asyncio.wait_for(entered[1].wait(), timeout=5)
        cancellation.cancel()
        cancelled = await asyncio.wait_for(cancel_task, timeout=5)
    finally:
        if not cancel_task.done():
            cancel_task.cancel()
        await asyncio.gather(cancel_task, return_exceptions=True)

    assert entered[1].is_set() and cleaned[1].is_set()
    assert cancelled.status == "cancelled" and cancelled.error_code == "cancelled"
    assert cancelled.retryable is False
    assert calls == 2 and len(boundary.calls) == 2

    old_cancel_key = await execution.dispatch(idempotency_key=cancel_key)
    _assert_rejected(old_cancel_key, {"attention_required"})
    assert calls == 2

    fresh = await execution.dispatch(idempotency_key="schedule-fresh-" + uuid4().hex)
    _assert_success(execution, fresh)
    assert calls == 3 and len(boundary.calls) == 3
    assert [event.event_type for event in execution.dispatcher.events].count(
        "invocation_start"
    ) == 5
    assert [event.event_type for event in execution.dispatcher.events].count(
        "invocation_end"
    ) == 5
    assert all(event.invocation_id for event in execution.dispatcher.events)
    record(request, key, "schedule_write_timeout")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", schedule_write_parameters("schedule_write_isolation"))
async def test_schedule_write_isolation_keeps_principal_and_resource_scope(
    key, db_session, monkeypatch, request
):
    execution = await make_write_execution(key, db_session)
    action = key[0]

    async def sync_result(*args, **kwargs):
        return _sync_success(execution)

    boundary = install_schedule_service_boundary(
        execution,
        monkeypatch,
        handler=sync_result if action == "sync_bangumi_schedule" else None,
    )
    stable_key = "schedule-isolation-" + uuid4().hex
    owner_args = execution.arguments()
    owner = await execution.dispatch(arguments=owner_args, idempotency_key=stable_key)
    _assert_success(execution, owner)

    foreign_context = execution.context_for(execution.foreign_user)
    foreign_dispatcher = _dispatcher_for_action(
        execution, action, user=execution.foreign_user
    )
    if action in {"update_schedule", "delete_schedule"}:
        foreign_args = {
            "schedule_id": execution.env.second_schedule_id,
            **({"day_of_week": 4} if action == "update_schedule" else {}),
        }
        foreign = await execution.dispatch(
            arguments=foreign_args,
            context=foreign_context,
            dispatcher=foreign_dispatcher,
            idempotency_key=stable_key,
        )
        assert foreign.status in {"failed", "denied"}
        assert foreign.error_code == "not_found"
        row = await _row_by_id(execution, execution.env.second_schedule_id)
        assert row is not None
        if action == "update_schedule":
            assert row.day_of_week == 5

        owner_second = await execution.dispatch(
            arguments=foreign_args,
            idempotency_key=stable_key,
        )
        _assert_success(execution, owner_second)
        if action == "delete_schedule":
            assert await _row_by_id(execution, execution.env.second_schedule_id) is None
        else:
            row = await _row_by_id(execution, execution.env.second_schedule_id)
            assert row is not None and row.day_of_week == 4
        assert len(boundary.calls) == 3
    else:
        foreign = await execution.dispatch(
            arguments=owner_args,
            context=foreign_context,
            dispatcher=foreign_dispatcher,
            idempotency_key=stable_key,
        )
        _assert_success(execution, foreign)
        assert len(boundary.calls) == 2
        if action in {"create_schedule", "upsert_schedule", "bulk_upsert_schedules"}:
            source_id = (
                owner_args["items"][0]["source_id"]
                if action == "bulk_upsert_schedules"
                else owner_args["source_id"]
            )
            rows = (
                (
                    await execution.db.execute(
                        select(Schedule).where(
                            cast(Any, Schedule.source_id) == source_id
                        )
                    )
                )
                .scalars()
                .all()
            )
            assert {row.user_id for row in rows} == {
                execution.user.id,
                execution.foreign_user.id,
            }

    assert boundary.unexpected_calls == []
    service_user_index = 2 if action in {"update_schedule", "delete_schedule"} else 1
    assert all(
        call[0][0] is execution.db
        and call[0][service_user_index]
        in {execution.user.id, execution.foreign_user.id}
        for call in boundary.calls
    )
    record(request, key, "schedule_write_isolation")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "key", schedule_write_parameters("schedule_write_serialization")
)
async def test_schedule_write_serialization_is_finite_json_before_success_record(
    key, db_session, monkeypatch, request
):
    execution = await make_write_execution(key, db_session)
    behavior: dict[str, Any] = {"value": _valid_service_result(execution)}

    async def route(*args, **kwargs):
        return behavior["value"]

    boundary = install_schedule_service_boundary(execution, monkeypatch, handler=route)
    valid = await execution.dispatch(
        idempotency_key="serialization-valid-" + uuid4().hex
    )
    _assert_success(execution, valid)
    assert len(boundary.calls) == 1

    action = key[0]
    variants = ("unsafe_object", "nan", "bad_shape")
    for variant in variants:
        if action == "delete_schedule":
            break
        behavior["value"] = _output_variant(execution, variant)
        calls_before = len(boundary.calls)
        idempotency_key = f"serialization-{variant}-" + uuid4().hex
        invalid = await execution.dispatch(idempotency_key=idempotency_key)
        assert invalid.status == "failed" and invalid.error_code == "invalid_output", (
            invalid.model_dump()
        )
        assert invalid.retryable is False
        invalid_json = json.dumps(invalid.model_dump(mode="json"), allow_nan=False)
        assert _OUTPUT_SENTINEL not in invalid_json
        assert len(boundary.calls) == calls_before + 1

        replay = await execution.dispatch(idempotency_key=idempotency_key)
        assert replay.status == "failed" and replay.error_code == "invalid_output"
        assert len(boundary.calls) == calls_before + 1

    assert boundary.unexpected_calls == []
    record(request, key, "schedule_write_serialization")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "key", schedule_write_parameters("schedule_write_authorization")
)
async def test_schedule_write_authority_schema_and_allowlist_fail_closed(
    key, db_session, monkeypatch, request
):
    execution = await make_write_execution(key, db_session)
    boundary = install_schedule_service_boundary(execution, monkeypatch)
    public = execution.arguments()
    definition = execution.registry.get_public_definition(*key)
    assert definition is not None
    descriptor = execution.descriptor
    assert descriptor.requires_auth and descriptor.is_side_effect
    assert descriptor.approval_required is True
    assert descriptor.idempotency_mode == "required"
    assert descriptor.risk_level == "medium"
    assert descriptor.input_schema["type"] == "object"
    assert descriptor.input_schema["additionalProperties"] is False
    assert descriptor.output_schema["type"] == "object"
    assert descriptor.output_schema.get("required")
    assert "idempotency_key" in descriptor.input_schema["properties"]
    _assert_schema_has_no_runtime_identity(descriptor.input_schema)
    _assert_schema_has_no_runtime_identity(definition.input_schema)
    validate_input({**public, "idempotency_key": uuid4().hex}, descriptor)
    json.dumps(definition.to_dict(), ensure_ascii=False, allow_nan=False)

    anonymous_dispatcher = execution.make_dispatcher(authenticated=False, durable=False)
    anonymous_context = execution.context.model_copy(
        update={
            "principal_id": None,
            "run_id": uuid4().hex,
            "trace_id": uuid4().hex,
        }
    )
    anonymous = await execution.dispatch(
        context=anonymous_context,
        dispatcher=anonymous_dispatcher,
        idempotency_key=uuid4().hex,
    )
    _assert_rejected(anonymous, {"unauthorized"})

    invalid_principal = execution.context.model_copy(
        update={"principal_id": 0, "run_id": uuid4().hex, "trace_id": uuid4().hex}
    )
    zero = await execution.dispatch(context=invalid_principal)
    _assert_rejected(zero, {"unauthorized"})

    with pytest.raises(ValidationError):
        await execution.dispatch(
            arguments={**public, "user_id": execution.user.id + 100}
        )

    nested_spoof = dict(public)
    if key[0] == "bulk_upsert_schedules":
        nested_spoof["items"][0]["user_id"] = execution.user.id + 100
    else:
        nested_spoof["metadata"] = {"principal_id": execution.user.id + 100}
    with pytest.raises(ValidationError):
        await execution.dispatch(arguments=nested_spoof)

    denied_allowlist = await execution.dispatch(
        context=execution.context_for(
            execution.user, allowlist=frozenset({"other-capability"})
        )
    )
    _assert_rejected(denied_allowlist, {"policy_denied"})

    denied_version = await execution.dispatch(version="v999")
    _assert_rejected(denied_version, {"not_configured", "unsupported_version"})

    denied_missing_key = await execution.dispatch(include_key=False)
    _assert_rejected(denied_missing_key, {"idempotency_required"})

    no_side_effects = execution.make_dispatcher(allow_side_effects=False)
    denied_policy = await execution.dispatch(dispatcher=no_side_effects)
    _assert_rejected(denied_policy, {"policy_denied"})

    no_store = execution.make_dispatcher(durable=False)
    denied_no_store = await execution.dispatch(dispatcher=no_store)
    _assert_rejected(denied_no_store, {"idempotency_required"})

    assert boundary.calls == [] and boundary.unexpected_calls == []
    record(request, key, "schedule_write_authorization")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", schedule_write_parameters("schedule_write_dispatcher"))
async def test_schedule_write_runs_through_registered_dispatcher(
    key, db_session, monkeypatch, request
):
    execution = await make_write_execution(key, db_session)

    async def sync_result(*args, **kwargs):
        return _sync_success(execution)

    boundary = install_schedule_service_boundary(
        execution,
        monkeypatch,
        handler=sync_result if key[0] == "sync_bangumi_schedule" else None,
    )
    invalid = await execution.dispatch(
        arguments={**execution.arguments(), "unregistered_field": "rejected"}
    )
    _assert_rejected(invalid, {"invalid_request", "invalid_args"})
    assert boundary.calls == [] and boundary.unexpected_calls == []

    result = await execution.dispatch(idempotency_key="dispatcher-" + uuid4().hex)
    _assert_success(execution, result)
    assert len(boundary.calls) == 1 and boundary.unexpected_calls == []
    assert result.invocation_id
    assert [event.event_type for event in execution.dispatcher.events] == [
        "invocation_start",
        "invocation_end",
    ]
    assert all(
        event.invocation_id == result.invocation_id
        for event in execution.dispatcher.events
    )
    record(request, key, "schedule_write_dispatcher")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", schedule_write_parameters("schedule_write_approval"))
async def test_schedule_write_requires_owner_action_bound_approval(
    key, db_session, monkeypatch, request
):
    execution = await make_write_execution(key, db_session)
    boundary = install_schedule_service_boundary(
        execution,
        monkeypatch,
        handler=lambda *args, **kwargs: _valid_service_result(execution),
    )

    missing = execution.make_dispatcher(approval=None, use_default_approval=False)
    pending = await execution.dispatch(dispatcher=missing)
    _assert_rejected(pending, {"approval_required", "policy_denied"})

    rejected = execution.make_dispatcher(
        approval=Approval(
            approval_id=uuid4().hex,
            approved=False,
            principal_id=execution.user.id,
            action=key[0],
        ),
        use_default_approval=False,
    )
    denied_rejected = await execution.dispatch(dispatcher=rejected)
    _assert_rejected(denied_rejected, {"policy_denied"})

    wrong_principal = execution.make_dispatcher(
        approval=Approval(
            approval_id=uuid4().hex,
            principal_id=execution.foreign_user.id,
            action=key[0],
        ),
        use_default_approval=False,
    )
    denied_principal = await execution.dispatch(dispatcher=wrong_principal)
    _assert_rejected(denied_principal, {"policy_denied"})

    wrong_action = execution.make_dispatcher(
        approval=Approval(
            approval_id=uuid4().hex,
            principal_id=execution.user.id,
            action="different_schedule_action",
        ),
        use_default_approval=False,
    )
    denied_action = await execution.dispatch(dispatcher=wrong_action)
    _assert_rejected(denied_action, {"policy_denied"})
    assert boundary.calls == [] and boundary.unexpected_calls == []

    approved = await execution.dispatch(idempotency_key="approved-" + uuid4().hex)
    _assert_success(execution, approved)
    assert len(boundary.calls) == 1 and boundary.unexpected_calls == []
    record(request, key, "schedule_write_approval")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", schedule_write_parameters("schedule_write_idempotency"))
async def test_schedule_write_idempotency_replay_conflict_and_action_binding(
    key, db_session, monkeypatch, request
):
    execution = await make_write_execution(key, db_session)
    boundary = install_schedule_service_boundary(
        execution,
        monkeypatch,
        handler=lambda *args, **kwargs: _valid_service_result(execution),
    )
    stable_key = "schedule-explicit-" + uuid4().hex
    first = await execution.dispatch(idempotency_key=stable_key)
    _assert_success(execution, first)
    assert len(boundary.calls) == 1

    factory = async_sessionmaker(
        db_session.bind, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as fresh_session:
        rebuilt_dispatcher = execution.make_dispatcher(db=fresh_session)
        replay = await execution.dispatch(
            idempotency_key=stable_key,
            dispatcher=rebuilt_dispatcher,
            context=execution.context_for(execution.user),
        )
        _assert_success(execution, replay)
        assert _business_output(replay) == _business_output(first)
        assert len(boundary.calls) == 1

        changed = execution.arguments()
        if key[0] in {"create_schedule", "upsert_schedule", "update_schedule"}:
            changed["day_of_week"] = 1
        elif key[0] == "bulk_upsert_schedules":
            changed["items"][0]["day_of_week"] = 1
        if key[0] != "delete_schedule" and key[0] != "sync_bangumi_schedule":
            conflict = await execution.dispatch(
                arguments=changed,
                idempotency_key=stable_key,
                dispatcher=rebuilt_dispatcher,
                context=execution.context_for(execution.user),
            )
            _assert_rejected(conflict, {"idempotency_conflict"})
            assert len(boundary.calls) == 1

    concurrent_key = "schedule-concurrent-" + uuid4().hex
    concurrent = await asyncio.gather(
        execution.dispatch(idempotency_key=concurrent_key),
        execution.dispatch(idempotency_key=concurrent_key),
    )
    assert all(result.status == "succeeded" for result in concurrent), [
        result.model_dump() for result in concurrent
    ]
    assert len(boundary.calls) == 2

    if key[0] in {
        "create_schedule",
        "upsert_schedule",
        "bulk_upsert_schedules",
        "sync_bangumi_schedule",
    }:
        first_action, second_action = "create_schedule", "upsert_schedule"
        collision_arguments = {
            "source": "bangumi",
            "source_id": f"c{execution.source_id[1:]}",
            "day_of_week": 2,
            "start_time": "19:30:00",
        }
    else:
        first_action, second_action = "update_schedule", "delete_schedule"
        collision_arguments = {"schedule_id": execution.env.second_schedule_id}

    collision_key = "schedule-action-bound-" + uuid4().hex
    first_dispatcher = _dispatcher_for_action(execution, first_action)
    second_dispatcher = _dispatcher_for_action(execution, second_action)
    first_context = execution.context_for(
        execution.user, allowlist=frozenset({first_action})
    )
    second_context = execution.context_for(
        execution.user, allowlist=frozenset({second_action})
    )
    first_action_result = await execution.dispatch(
        arguments=collision_arguments,
        action=first_action,
        dispatcher=first_dispatcher,
        context=first_context,
        idempotency_key=collision_key,
    )
    assert first_action_result.status == "succeeded", first_action_result.model_dump()
    _assert_json_safe(first_action_result)
    collision = await execution.dispatch(
        arguments=collision_arguments,
        action=second_action,
        dispatcher=second_dispatcher,
        context=second_context,
        idempotency_key=collision_key,
    )
    _assert_rejected(collision, {"idempotency_conflict"})

    assert boundary.unexpected_calls == []
    record(request, key, "schedule_write_idempotency")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", schedule_write_parameters("schedule_write_recovery"))
async def test_schedule_write_recovery_rebuilds_runtime_from_sql_state(
    key, db_session, monkeypatch, request
):
    execution = await make_write_execution(key, db_session)
    boundary = install_schedule_service_boundary(
        execution,
        monkeypatch,
        handler=lambda *args, **kwargs: _valid_service_result(execution),
    )
    confirmed_key = "schedule-recovered-result-" + uuid4().hex
    confirmed = await execution.dispatch(idempotency_key=confirmed_key)
    _assert_success(execution, confirmed)
    assert len(boundary.calls) == 1

    factory = async_sessionmaker(
        db_session.bind, class_=AsyncSession, expire_on_commit=False
    )
    async with factory() as recovered_session:
        recovered_dispatcher = execution.make_dispatcher(db=recovered_session)
        replay = await execution.dispatch(
            idempotency_key=confirmed_key,
            dispatcher=recovered_dispatcher,
            context=execution.context_for(execution.user),
        )
        _assert_success(execution, replay)
        assert _business_output(replay) == _business_output(confirmed)
        assert len(boundary.calls) == 1

    unknown_key = "schedule-reserved-unknown-" + uuid4().hex
    public_arguments = {
        **execution.arguments(),
        "idempotency_key": unknown_key,
    }
    scope = (
        f"{execution.user.id}:schedule:"
        f"{CapabilityAdapter._resource_key(key[0], public_arguments)}"
    )
    payload_hash = _payload_hash(public_arguments)

    async def interrupted_operation():
        raise asyncio.CancelledError()

    store = SqlIdempotencyStore(db_session)
    with pytest.raises(asyncio.CancelledError):
        await store.execute_once(
            scope,
            unknown_key,
            payload_hash,
            interrupted_operation,
        )
    await db_session.commit()

    async with factory() as recovered_session:
        rebuilt = execution.make_dispatcher(db=recovered_session)
        unknown = await execution.dispatch(
            idempotency_key=unknown_key,
            dispatcher=rebuilt,
            context=execution.context_for(execution.user),
        )
        _assert_rejected(unknown, {"attention_required"})
        assert len(boundary.calls) == 1
        claim = (
            (
                await recovered_session.execute(
                    select(AgentInvocation).where(
                        cast(Any, AgentInvocation.idempotency_key) == unknown_key
                    )
                )
            )
            .scalars()
            .first()
        )
        assert claim is not None
        unknown_events = (
            (
                await recovered_session.execute(
                    select(AgentRunEvent).where(
                        cast(Any, AgentRunEvent.event_type) == "idempotency.result",
                        cast(Any, AgentRunEvent.run_id) == claim.run_id,
                    )
                )
            )
            .scalars()
            .all()
        )
        assert all(
            event.payload.get("result", {}).get("status") != "succeeded"
            for event in unknown_events
        )

    assert boundary.unexpected_calls == []
    record(request, key, "schedule_write_recovery")
