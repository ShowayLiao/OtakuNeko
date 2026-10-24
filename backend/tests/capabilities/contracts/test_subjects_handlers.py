"""Real Subjects handler error, timeout, isolation, and serialization contracts."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import json
import logging
from typing import Any

import pytest
from pydantic import ValidationError

from app.capabilities import subjects as subjects_module
from app.harness.authority import RUNTIME_OWNED_FIELDS
from app.harness.contracts import InvocationResult
from app.models.enums import SubjectType
from app.schemas.adaptersV2 import UnifiedCollectionSubject, UnifiedList
from app.schemas.subject import SubjectRead
from tests.capabilities.contracts.plugin import record
from tests.capabilities.contracts.subjects_support import (
    DEPENDENCIES,
    make_execution,
    subjects_parameters,
)
from tests.capabilities.contracts.test_contracts import assert_subset

_ERROR_SENTINEL = "subjects-private-diagnostic-sentinel"
_OUTPUT_SENTINEL = "subjects-private-output-sentinel"


class _UnsafeValue:
    def __repr__(self) -> str:
        return _OUTPUT_SENTINEL


def _assert_stub_options(action: str, kwargs: dict[str, Any]) -> None:
    dependency = DEPENDENCIES[action]
    expected = (
        {"strict": True}
        if dependency in {"search_subject_cloud", "search_mixed"}
        else {}
    )
    assert kwargs == expected


def _unsafe_subject() -> dict[str, Any]:
    return {
        "id": 101,
        "name": _UnsafeValue(),
        "name_cn": "合成动画",
        "type": 2,
        "source": "bangumi",
        "source_id": "subject-101",
        "air_time": _UnsafeValue(),
        "air_weekday": 2,
    }


def _pydantic_subject() -> UnifiedCollectionSubject:
    return UnifiedCollectionSubject(
        subject=SubjectRead(
            id=101,
            name="Synthetic Anime",
            name_cn="合成动画",
            type=SubjectType.ANIME,
            source="bangumi",
            source_id="subject-101",
            air_time=datetime(2026, 10, 20, 12, tzinfo=timezone.utc),
            air_weekday=2,
            summary=None,
        ),
        collection=None,
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("key", subjects_parameters("subjects_error"))
async def test_subjects_error(key, db_session, monkeypatch, caplog, request):
    execution = await make_execution(key, db_session, monkeypatch)
    dependency = DEPENDENCIES[key[0]]
    calls = []

    async def fail_value_error(*args, **kwargs):
        _assert_stub_options(key[0], kwargs)
        calls.append((args, kwargs))
        raise ValueError(_ERROR_SENTINEL)

    monkeypatch.setattr(subjects_module, dependency, fail_value_error)
    invalid = await execution.dispatch()

    assert len(calls) == 1
    assert invalid.status == "failed" and invalid.error_code == "invalid_args"
    assert invalid.output["success"] is False
    invalid_json = json.dumps(invalid.model_dump(mode="json"), allow_nan=False)
    assert _ERROR_SENTINEL not in invalid_json

    calls.clear()

    async def fail_internal(*args, **kwargs):
        _assert_stub_options(key[0], kwargs)
        calls.append((args, kwargs))
        raise RuntimeError(_ERROR_SENTINEL)

    monkeypatch.setattr(subjects_module, dependency, fail_internal)
    logger = subjects_module.logger
    logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.ERROR, logger=logger.name):
            internal = await execution.dispatch()
    finally:
        logger.removeHandler(caplog.handler)

    assert len(calls) == 1
    assert internal.status == "failed" and internal.error_code == "internal"
    assert internal.output["success"] is False
    internal_json = json.dumps(internal.model_dump(mode="json"), allow_nan=False)
    assert _ERROR_SENTINEL not in internal_json
    records = [item for item in caplog.records if item.name == logger.name]
    assert len(records) == 1
    assert records[0].getMessage() == "subject_capability_failed"
    assert records[0].action == execution.descriptor.name
    assert records[0].error_type == "RuntimeError"
    assert records[0].exc_info is None
    assert _ERROR_SENTINEL not in repr(records[0].__dict__)
    record(request, key, "subjects_error")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", subjects_parameters("subjects_timeout"))
async def test_subjects_timeout(key, db_session, monkeypatch, request):
    execution = await make_execution(key, db_session, monkeypatch)
    dependency = DEPENDENCIES[key[0]]
    started = asyncio.Event()
    cleaned = asyncio.Event()

    async def block_dependency(*args, **kwargs):
        _assert_stub_options(key[0], kwargs)
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    monkeypatch.setattr(subjects_module, dependency, block_dependency)
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
        await asyncio.wait_for(started.wait(), timeout=5)
        result = await dispatch_task
    finally:
        if not dispatch_task.done():
            dispatch_task.cancel()
        await asyncio.gather(dispatch_task, return_exceptions=True)

    assert started.is_set() and cleaned.is_set()
    assert result.status == "timeout" and result.error_code == "timeout"
    record(request, key, "subjects_timeout")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", subjects_parameters("subjects_isolation"))
async def test_subjects_isolation(key, db_session, monkeypatch, request):
    execution = await make_execution(key, db_session, monkeypatch)
    dependency = DEPENDENCIES[key[0]]
    positive_dependency = getattr(subjects_module, dependency)
    calls = 0

    async def fail_once_then_return_positive(*args, **kwargs):
        nonlocal calls
        _assert_stub_options(key[0], kwargs)
        calls += 1
        if calls == 1:
            raise RuntimeError(_ERROR_SENTINEL)
        return await positive_dependency(*args, **kwargs)

    monkeypatch.setattr(subjects_module, dependency, fail_once_then_return_positive)

    failed = await execution.dispatch()
    recovered = await execution.dispatch()

    assert calls == 2
    assert failed.status == "failed" and failed.error_code == "internal"
    assert _ERROR_SENTINEL not in json.dumps(
        failed.model_dump(mode="json"), allow_nan=False
    )
    assert recovered.status == "succeeded", recovered.model_dump()
    assert recovered.error_code is None and recovered.output["success"] is True
    assert execution.env.calls
    assert_subset(execution.example.expected, recovered.output)
    record(request, key, "subjects_isolation")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", subjects_parameters("subjects_serialization"))
async def test_subjects_serialization(key, db_session, monkeypatch, request):
    execution = await make_execution(key, db_session, monkeypatch)
    dependency = DEPENDENCIES[key[0]]
    unified_subject = _pydantic_subject()

    async def return_pydantic_unified_data(db, search, **kwargs):
        _assert_stub_options(key[0], kwargs)
        if key[0] == "search_remote_subjects":
            assert db is None and search.user_id is None
        else:
            assert db is execution.env.db
            assert search.user_id == execution.env.user.id
        execution.env.calls.append("subjects.serialization")
        if key[0] in {"get_subject", "get_subject_air_time"}:
            return unified_subject
        return UnifiedList(total=1, items=[unified_subject])

    monkeypatch.setattr(subjects_module, dependency, return_pydantic_unified_data)
    result = await execution.dispatch()

    assert result.status == "succeeded", result.model_dump()
    assert result.error_code is None and result.output["success"] is True
    assert execution.env.calls == ["subjects.serialization"]
    assert_subset(execution.example.expected, result.output)
    encoded = json.dumps(result.model_dump(mode="json"), allow_nan=False)
    assert "2026-10-20T12:00:00" in encoded
    assert "user_id" not in encoded
    assert InvocationResult.model_validate(json.loads(encoded)) == result

    async def return_unsafe_result(*args, **kwargs):
        _assert_stub_options(key[0], kwargs)
        subject = _unsafe_subject()
        if key[0] in {"get_subject", "get_subject_air_time"}:
            return {"subject": subject, "collection": None}
        return {"total": 1, "items": [{"subject": subject, "collection": None}]}

    monkeypatch.setattr(subjects_module, dependency, return_unsafe_result)
    unsafe = await execution.dispatch()

    assert unsafe.status == "failed" and unsafe.error_code == "invalid_output"
    unsafe_json = json.dumps(unsafe.model_dump(mode="json"), allow_nan=False)
    assert _OUTPUT_SENTINEL not in unsafe_json
    record(request, key, "subjects_serialization")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", subjects_parameters("subjects_authorization"))
async def test_subjects_authorization(key, db_session, monkeypatch, request):
    anonymous = await make_execution(key, db_session, monkeypatch, authenticated=False)
    anonymous_result = await anonymous.dispatch()
    if anonymous.descriptor.requires_auth:
        assert (
            anonymous_result.status == "denied"
            and anonymous_result.error_code == "unauthorized"
        )
        assert not anonymous.env.calls
    else:
        assert anonymous_result.status == "succeeded", anonymous_result.model_dump()
        assert_subset(anonymous.example.expected, anonymous_result.output)
        assert anonymous.env.calls

    execution = await make_execution(key, db_session, monkeypatch)
    for field in sorted(RUNTIME_OWNED_FIELDS):
        for location in ("root", "nested"):
            arguments = execution.example.arguments.copy()
            arguments.update(
                {field: "forged-authority"}
                if location == "root"
                else {"untrusted": [{field: "forged-authority"}]}
            )
            with pytest.raises(ValidationError):
                await execution.dispatch(arguments)
            denied = await execution.dispatch(arguments, forged=True)
            assert (
                denied.status == "denied" and denied.error_code == "identity_spoofing"
            )
            assert not execution.env.calls

    if execution.descriptor.requires_auth:
        for principal in (None, 0, -1):
            denied = await execution.dispatch(
                context=execution.context.model_copy(update={"principal_id": principal})
            )
            assert denied.status == "denied" and denied.error_code == "unauthorized"
            assert not execution.env.calls
    record(request, key, "subjects_authorization")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", subjects_parameters("subjects_dispatcher"))
async def test_subjects_dispatcher(key, db_session, monkeypatch, request):
    execution = await make_execution(key, db_session, monkeypatch)
    denied = await execution.dispatch(
        context=execution.context.model_copy(
            update={"capability_allowlist": frozenset({"unrelated.action"})}
        )
    )
    assert denied.status == "denied" and denied.error_code == "policy_denied"
    wrong_version = await execution.dispatch(version="v999")
    assert (
        wrong_version.status == "denied"
        and wrong_version.error_code == "not_configured"
    )
    assert not execution.env.calls and not execution.dispatcher.events

    for name, schema in execution.descriptor.input_schema.get("properties", {}).items():
        if schema.get("type") not in {"array", "integer", "string"}:
            continue
        invalid = execution.example.arguments.copy()
        invalid[name] = {"wrong": "type"}
        result = await execution.dispatch(invalid)
        assert result.status == "denied" and result.error_code == "invalid_request"
        assert not execution.env.calls and not execution.dispatcher.events

    result = await execution.dispatch()
    assert result.status == "succeeded" and result.error_code is None
    assert_subset(execution.example.expected, result.output)
    assert execution.env.calls
    events = execution.dispatcher.events
    assert [event.event_type for event in events] == [
        "invocation_start",
        "invocation_end",
    ]
    assert events[0].invocation_id == events[1].invocation_id == result.invocation_id
    assert events[1].payload["status"] == "succeeded"
    assert (
        result.run_id == execution.context.run_id
        and result.trace_id == execution.context.trace_id
    )
    record(request, key, "subjects_dispatcher")
