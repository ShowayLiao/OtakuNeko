"""Real Schedule read handler error, timeout, isolation, and output contracts."""

from __future__ import annotations

import asyncio
from dataclasses import replace
import json
import logging

import pytest
from pydantic import ValidationError

from app.capabilities import schedule as schedule_module
from app.harness.authority import RUNTIME_OWNED_FIELDS
from app.harness.contracts import InvocationResult
from app.models.enums import WatchType
from tests.capabilities.contracts.plugin import record
from tests.capabilities.contracts.schedule_read_support import (
    DEPENDENCIES,
    FOREIGN_COMMENT,
    OWNER_COMMENT,
    assert_trusted_service_call,
    make_execution,
    schedule_parameters,
)

_ERROR_SENTINEL = "schedule-read-private-diagnostic-sentinel"
_OUTPUT_SENTINEL = "schedule-read-private-output-sentinel"


class _UnsafeValue:
    def __repr__(self) -> str:
        return _OUTPUT_SENTINEL


def _assert_owned_success(execution, result) -> None:
    assert result.status == "succeeded", result.model_dump()
    assert result.error_code is None
    assert result.output["success"] is True
    assert type(result.output["count"]) is int
    schedules = result.output["schedules"]
    assert result.output["count"] == len(schedules)
    if execution.key[0] == "list_unified_schedules":
        entries = [item["schedule"] for item in schedules]
        encoded = json.dumps(result.model_dump(mode="json"), allow_nan=False)
        assert OWNER_COMMENT in encoded
        assert FOREIGN_COMMENT not in encoded
        assert "schedule-foreign-private-tag" not in encoded
    else:
        entries = schedules
        encoded = json.dumps(result.model_dump(mode="json"), allow_nan=False)
    expected_ids = (
        execution.env.by_day_schedule_ids
        if execution.key[0] == "list_schedules_by_day"
        else execution.env.owner_schedule_ids
    )
    assert {item["id"] for item in entries} == expected_ids
    assert '"user_id"' not in encoded
    assert execution.env.foreign_user.username not in encoded


@pytest.mark.asyncio
@pytest.mark.parametrize("key", schedule_parameters("schedule_read_error"))
async def test_schedule_read_errors_are_safe(
    key, db_session, monkeypatch, caplog, request
):
    execution = await make_execution(key, db_session)
    dependency = DEPENDENCIES[key[0]]
    calls = []

    async def fail_value_error(*args, **kwargs):
        assert_trusted_service_call(execution, args, kwargs)
        calls.append((args, kwargs))
        raise ValueError(_ERROR_SENTINEL)

    monkeypatch.setattr(schedule_module.ScheduleService, dependency, fail_value_error)
    invalid = await execution.dispatch()

    assert len(calls) == 1
    assert invalid.status == "failed" and invalid.error_code == "invalid_args"
    invalid_json = json.dumps(invalid.model_dump(mode="json"), allow_nan=False)
    assert _ERROR_SENTINEL not in invalid_json

    calls.clear()

    async def fail_runtime_error(*args, **kwargs):
        assert_trusted_service_call(execution, args, kwargs)
        calls.append((args, kwargs))
        raise RuntimeError(_ERROR_SENTINEL)

    monkeypatch.setattr(schedule_module.ScheduleService, dependency, fail_runtime_error)
    logger = schedule_module.logger
    logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.ERROR, logger=logger.name):
            internal = await execution.dispatch()
    finally:
        logger.removeHandler(caplog.handler)

    assert len(calls) == 1
    assert internal.status == "failed" and internal.error_code == "internal"
    internal_json = json.dumps(internal.model_dump(mode="json"), allow_nan=False)
    assert _ERROR_SENTINEL not in internal_json
    records = [item for item in caplog.records if item.name == logger.name]
    assert len(records) == 1
    assert records[0].getMessage() == "schedule_capability_failed"
    assert records[0].action == execution.descriptor.name
    assert records[0].error_type == "RuntimeError"
    assert records[0].exc_info is None
    assert _ERROR_SENTINEL not in repr(records[0].__dict__)
    record(request, key, "schedule_read_error")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", schedule_parameters("schedule_read_timeout"))
async def test_schedule_read_timeout_cleans_up_and_allows_fresh_dispatch(
    key, db_session, monkeypatch, request
):
    execution = await make_execution(key, db_session)
    dependency = DEPENDENCIES[key[0]]
    read_dependency = getattr(schedule_module.ScheduleService, dependency)
    entered = asyncio.Event()
    cleaned = asyncio.Event()
    calls = 0

    async def block_once_then_read(*args, **kwargs):
        nonlocal calls
        assert_trusted_service_call(execution, args, kwargs)
        calls += 1
        if calls == 1:
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()
        return await read_dependency(*args, **kwargs)

    monkeypatch.setattr(
        schedule_module.ScheduleService, dependency, block_once_then_read
    )
    descriptors = [
        replace(descriptor, timeout_seconds=0.1)
        if descriptor.name == execution.descriptor.name
        else descriptor
        for descriptor in execution.capability.actions()
    ]
    monkeypatch.setattr(execution.capability, "actions", lambda: descriptors)
    execution.dispatcher.registry.unregister(execution.capability.name)
    execution.dispatcher.registry.register(execution.capability)

    dispatch_task = asyncio.create_task(execution.dispatch())
    try:
        await asyncio.wait_for(entered.wait(), timeout=5)
        timed_out = await dispatch_task
    finally:
        if not dispatch_task.done():
            dispatch_task.cancel()
        await asyncio.gather(dispatch_task, return_exceptions=True)

    assert entered.is_set() and cleaned.is_set()
    assert timed_out.status == "timeout" and timed_out.error_code == "timeout"
    events = execution.dispatcher.events
    assert [event.event_type for event in events] == [
        "invocation_start",
        "invocation_end",
    ]
    assert events[0].invocation_id == events[1].invocation_id == timed_out.invocation_id
    assert events[1].payload["status"] == "timeout"

    recovered = await execution.dispatch()
    assert calls == 2
    _assert_owned_success(execution, recovered)
    events = execution.dispatcher.events
    assert [event.event_type for event in events] == [
        "invocation_start",
        "invocation_end",
        "invocation_start",
        "invocation_end",
    ]
    assert events[2].invocation_id == events[3].invocation_id == recovered.invocation_id
    assert events[0].invocation_id != events[2].invocation_id
    assert events[3].payload["status"] == "succeeded"
    record(request, key, "schedule_read_timeout")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", schedule_parameters("schedule_read_isolation"))
async def test_schedule_read_recovers_and_keeps_user_scope(
    key, db_session, monkeypatch, request
):
    execution = await make_execution(key, db_session)
    dependency = DEPENDENCIES[key[0]]
    read_dependency = getattr(schedule_module.ScheduleService, dependency)
    calls = 0

    async def fail_once_then_read(*args, **kwargs):
        nonlocal calls
        assert_trusted_service_call(execution, args, kwargs)
        calls += 1
        if calls == 1:
            raise RuntimeError(_ERROR_SENTINEL)
        return await read_dependency(*args, **kwargs)

    monkeypatch.setattr(
        schedule_module.ScheduleService, dependency, fail_once_then_read
    )
    failed = await execution.dispatch()
    recovered = await execution.dispatch()

    assert calls == 2
    assert failed.status == "failed" and failed.error_code == "internal"
    assert _ERROR_SENTINEL not in json.dumps(
        failed.model_dump(mode="json"), allow_nan=False
    )
    _assert_owned_success(execution, recovered)
    record(request, key, "schedule_read_isolation")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", schedule_parameters("schedule_read_serialization"))
async def test_schedule_read_serializes_real_models_and_rejects_bad_output(
    key, db_session, monkeypatch, request
):
    execution = await make_execution(key, db_session)
    result = await execution.dispatch()
    _assert_owned_success(execution, result)
    encoded = json.dumps(result.model_dump(mode="json"), allow_nan=False)
    assert '"user_id"' not in encoded
    assert InvocationResult.model_validate(json.loads(encoded)) == result

    if key[0] == "list_unified_schedules":
        by_source = {
            item["schedule"]["source_id"]: item for item in result.output["schedules"]
        }
        shared = by_source[execution.env.shared_source_id]
        subject_only = by_source[execution.env.subject_only_source_id]
        collection_only = by_source[execution.env.collection_only_source_id]
        assert type(shared["schedule"]["watch_type"]) is int
        assert shared["schedule"]["watch_type"] == int(WatchType.NEW)
        assert shared["schedule"]["start_time"] == "19:30:00"
        assert shared["schedule"]["watch_time"] == "21:45:00"
        assert shared["subject"]["id"] > 0
        assert shared["collection"]["comment"] == OWNER_COMMENT
        assert subject_only["subject"]["id"] > 0
        assert subject_only["collection"] is None
        assert collection_only["subject"] is None
        assert collection_only["collection"]["comment"] == OWNER_COMMENT
    else:
        by_source = {item["source_id"]: item for item in result.output["schedules"]}
        shared = by_source[execution.env.shared_source_id]
        assert type(shared["watch_type"]) is int
        assert shared["watch_type"] == int(WatchType.NEW)
        assert shared["start_time"] == "19:30:00"
        assert shared["watch_time"] == "21:45:00"

    dependency = DEPENDENCIES[key[0]]
    schedule = {
        "id": 9001,
        "source": "bangumi",
        "source_id": "contract-schedule",
        "day_of_week": 2,
        "start_time": "19:30:00",
        "watch_day": None,
        "watch_time": None,
        "duration": None,
        "watch_type": int(WatchType.NEW),
    }
    for kind in ("object", "nan", "bad_shape"):
        malformed_schedule = dict(schedule)
        if kind == "object":
            malformed_schedule["source_id"] = _UnsafeValue()
        elif kind == "nan":
            malformed_schedule["duration"] = float("nan")
        elif key[0] != "list_unified_schedules":
            malformed_schedule.pop("start_time")

        if key[0] == "list_unified_schedules":
            item = {
                "schedule": malformed_schedule or schedule,
                "subject": None,
                "collection": None,
            }
            if kind == "bad_shape":
                item.pop("schedule")

            async def return_malformed(db, user_id, *args, malformed=item):
                return {"total": 1, "items": [malformed]}

        else:

            async def return_malformed(
                db, user_id, *args, malformed=malformed_schedule
            ):
                return [malformed]

        monkeypatch.setattr(
            schedule_module.ScheduleService, dependency, return_malformed
        )
        rejected = await execution.dispatch()
        assert rejected.status == "failed", rejected.model_dump()
        assert rejected.error_code == "invalid_output"
        rejected_json = json.dumps(rejected.model_dump(mode="json"), allow_nan=False)
        assert _OUTPUT_SENTINEL not in rejected_json
    record(request, key, "schedule_read_serialization")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", schedule_parameters("schedule_read_authorization"))
async def test_schedule_read_authorization_precedes_service(
    key, db_session, monkeypatch, request
):
    anonymous = await make_execution(key, db_session, authenticated=False)
    dependency = DEPENDENCIES[key[0]]
    calls = []

    async def unexpected_service(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("Unauthorized Schedule read reached ScheduleService")

    monkeypatch.setattr(schedule_module.ScheduleService, dependency, unexpected_service)
    anonymous_result = await anonymous.dispatch()
    assert anonymous_result.status == "denied"
    assert anonymous_result.error_code == "unauthorized"
    assert not calls

    execution = await make_execution(key, db_session)
    for field in sorted(RUNTIME_OWNED_FIELDS):
        for location in ("root", "nested"):
            arguments = execution.arguments()
            arguments.update(
                {field: "forged-identity"}
                if location == "root"
                else {"untrusted": [{field: "forged-identity"}]}
            )
            with pytest.raises(ValidationError):
                await execution.dispatch(arguments)
            denied = await execution.dispatch(arguments, forged=True)
            assert denied.status == "denied"
            assert denied.error_code == "identity_spoofing"
            assert not calls

    for principal in (None, 0, -1):
        denied = await execution.dispatch(
            context=execution.context.model_copy(update={"principal_id": principal})
        )
        assert denied.status == "denied" and denied.error_code == "unauthorized"
        assert not calls

    invalid_arguments = [
        {**execution.arguments(), "save": True},
        {**execution.arguments(), "idempotency_key": "forged-key"},
        {**execution.arguments(), "filter": "private"},
    ]
    if key[0] == "list_schedules_by_day":
        invalid_arguments.extend(
            [
                {},
                {"day_of_week": True},
                {"day_of_week": -1},
                {"day_of_week": 7},
            ]
        )
    else:
        invalid_arguments.append({"day_of_week": 2})
    for arguments in invalid_arguments:
        denied = await execution.dispatch(arguments)
        assert denied.status == "denied"
        assert denied.error_code == "invalid_request"
        assert not calls

    wrong_version = await execution.dispatch(version="v999")
    assert wrong_version.status == "denied"
    assert wrong_version.error_code == "not_configured"
    denied_allowlist = await execution.dispatch(
        context=execution.context.model_copy(
            update={"capability_allowlist": frozenset({"unrelated.action"})}
        )
    )
    assert denied_allowlist.status == "denied"
    assert denied_allowlist.error_code == "policy_denied"
    assert not calls
    record(request, key, "schedule_read_authorization")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", schedule_parameters("schedule_read_dispatcher"))
async def test_schedule_read_dispatcher_contract_and_event_correlation(
    key, db_session, monkeypatch, request
):
    execution = await make_execution(key, db_session)
    dependency = DEPENDENCIES[key[0]]
    read_dependency = getattr(schedule_module.ScheduleService, dependency)
    calls = []

    async def track_service(*args, **kwargs):
        assert_trusted_service_call(execution, args, kwargs)
        calls.append((args, kwargs))
        return await read_dependency(*args, **kwargs)

    monkeypatch.setattr(schedule_module.ScheduleService, dependency, track_service)

    assert execution.descriptor.version == "v1"
    assert execution.descriptor.requires_auth is True
    assert execution.descriptor.is_side_effect is False
    input_schema = execution.descriptor.input_schema
    assert input_schema["type"] == "object"
    assert input_schema["additionalProperties"] is False
    assert input_schema["properties"] == (
        {"day_of_week": {"type": "integer", "minimum": 0, "maximum": 6}}
        if key[0] == "list_schedules_by_day"
        else {}
    )
    assert set(input_schema["required"]) == (
        {"day_of_week"} if key[0] == "list_schedules_by_day" else set()
    )

    output_schema = execution.descriptor.output_schema
    assert output_schema != {"type": "object", "additionalProperties": True}
    assert output_schema["type"] == "object"
    assert set(output_schema["required"]) == {"schedules", "count"}
    properties = output_schema["properties"]
    assert set(properties) == {"schedules", "count"}
    assert properties["count"]["type"] == "integer"
    assert properties["count"]["minimum"] == 0
    assert properties["schedules"]["type"] == "array"
    item_schema = properties["schedules"]["items"]
    if key[0] == "list_unified_schedules":
        assert set(item_schema["required"]) == {"schedule", "subject", "collection"}
        assert set(item_schema["properties"]) == {
            "schedule",
            "subject",
            "collection",
        }
        schedule_schema = item_schema["properties"]["schedule"]
        assert item_schema["properties"]["subject"]["anyOf"][-1] == {"type": "null"}
        assert item_schema["properties"]["collection"]["anyOf"][-1] == {"type": "null"}
    else:
        schedule_schema = item_schema
    assert schedule_schema["type"] == "object"
    assert set(schedule_schema["required"]) == {
        "id",
        "source",
        "source_id",
        "day_of_week",
        "start_time",
    }
    schedule_properties = schedule_schema["properties"]
    assert schedule_properties["day_of_week"]["minimum"] == 0
    assert schedule_properties["day_of_week"]["maximum"] == 6
    assert schedule_properties["start_time"]["type"] == "string"
    assert schedule_properties["watch_time"]["type"] == ["string", "null"]
    assert schedule_properties["watch_type"]["enum"] == [1, 2, 3, 4, None]

    denied_allowlist = await execution.dispatch(
        context=execution.context.model_copy(
            update={"capability_allowlist": frozenset({"unrelated.action"})}
        )
    )
    assert denied_allowlist.status == "denied"
    assert denied_allowlist.error_code == "policy_denied"
    wrong_version = await execution.dispatch(version="v999")
    assert wrong_version.status == "denied"
    assert wrong_version.error_code == "not_configured"
    assert not calls and not execution.dispatcher.events

    for name, schema in input_schema["properties"].items():
        invalid_arguments = execution.arguments()
        invalid_arguments[name] = {"wrong": "type"}
        invalid = await execution.dispatch(invalid_arguments)
        assert invalid.status == "denied"
        assert invalid.error_code == "invalid_request"
        assert not calls and not execution.dispatcher.events

    result = await execution.dispatch()
    _assert_owned_success(execution, result)
    assert len(calls) == 1
    events = execution.dispatcher.events
    assert [event.event_type for event in events] == [
        "invocation_start",
        "invocation_end",
    ]
    assert events[0].invocation_id == events[1].invocation_id == result.invocation_id
    assert events[1].payload["status"] == "succeeded"
    assert result.run_id == execution.context.run_id
    assert result.trace_id == execution.context.trace_id
    assert result.capability == key[0] and result.capability_version == key[1]
    record(request, key, "schedule_read_dispatcher")
