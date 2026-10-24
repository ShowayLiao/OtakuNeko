"""Real Recommendation and Stats handler failure and serialization contracts."""

from __future__ import annotations

import asyncio
from dataclasses import replace
import json
import logging
from typing import Any

import pytest
from pydantic import ValidationError

from app.capabilities import recommendation as recommendation_module
from app.capabilities import stats as stats_module
from app.harness.authority import RUNTIME_OWNED_FIELDS
from app.harness.contracts import InvocationResult
from tests.capabilities.contracts.plugin import record
from tests.capabilities.contracts.profile_stats_support import (
    DEPENDENCIES,
    make_execution,
    profile_stats_parameters,
)
from tests.capabilities.contracts.test_contracts import assert_subset

_ERROR_SENTINEL = "profile-stats-private-diagnostic-sentinel"
_OUTPUT_SENTINEL = "profile-stats-private-output-sentinel"


class _UnsafeValue:
    def __repr__(self) -> str:
        return _OUTPUT_SENTINEL


def _module(action: str):
    if action in {"generate_user_profile_tool", "analyse_taste"}:
        return recommendation_module
    return stats_module


@pytest.mark.asyncio
@pytest.mark.parametrize("key", profile_stats_parameters("recommendation_error"))
async def test_recommendation_error_is_safe(
    key, db_session, monkeypatch, caplog, request
):
    execution = await make_execution(key, db_session, monkeypatch)
    dependency = DEPENDENCIES[key[0]]
    calls = []

    async def fail_dependency(*args, **kwargs):
        calls.append((args, kwargs))
        raise RuntimeError(_ERROR_SENTINEL)

    monkeypatch.setattr(recommendation_module, dependency, fail_dependency)
    logger = recommendation_module.logger
    logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.ERROR, logger=logger.name):
            result = await execution.dispatch()
    finally:
        logger.removeHandler(caplog.handler)

    assert len(calls) == 1
    assert result.status == "failed" and result.error_code == "internal"
    assert result.output["success"] is False
    encoded = json.dumps(result.model_dump(mode="json"), allow_nan=False)
    assert _ERROR_SENTINEL not in encoded
    records = [item for item in caplog.records if item.name == logger.name]
    assert len(records) == 1
    assert records[0].getMessage() == "recommendation_capability_failed"
    assert records[0].action == execution.descriptor.name
    assert records[0].error_type == "RuntimeError"
    assert records[0].exc_info is None
    assert _ERROR_SENTINEL not in repr(records[0].__dict__)
    record(request, key, "recommendation_error")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", profile_stats_parameters("stats_error"))
async def test_stats_value_error_is_invalid_args_and_safe(
    key, db_session, monkeypatch, request
):
    execution = await make_execution(key, db_session, monkeypatch)
    dependency = DEPENDENCIES[key[0]]
    calls = []

    async def fail_with_value_error(*args, **kwargs):
        calls.append((args, kwargs))
        raise ValueError(_ERROR_SENTINEL)

    monkeypatch.setattr(stats_module, dependency, fail_with_value_error)
    result = await execution.dispatch()

    assert len(calls) == 1
    assert result.status == "failed" and result.error_code == "invalid_args"
    assert result.output["success"] is False
    assert result.output["error_type"] == "invalid_args"
    encoded = json.dumps(result.model_dump(mode="json"), allow_nan=False)
    assert _ERROR_SENTINEL not in encoded
    record(request, key, "stats_error")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", profile_stats_parameters("recommendation_timeout"))
async def test_recommendation_io_timeout_cancels_dependency(
    key, db_session, monkeypatch, request
):
    execution = await make_execution(key, db_session, monkeypatch)
    dependency = DEPENDENCIES[key[0]]
    started = asyncio.Event()
    cleaned = asyncio.Event()

    async def block_dependency(*args, **kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    monkeypatch.setattr(recommendation_module, dependency, block_dependency)
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
    assert [event.event_type for event in execution.dispatcher.events] == [
        "invocation_start",
        "invocation_end",
    ]
    assert execution.dispatcher.events[-1].payload["status"] == "timeout"
    record(request, key, "recommendation_timeout")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", profile_stats_parameters("stats_timeout"))
async def test_stats_io_timeout_cancels_dependency(
    key, db_session, monkeypatch, request
):
    execution = await make_execution(key, db_session, monkeypatch)
    dependency = DEPENDENCIES[key[0]]
    started = asyncio.Event()
    cleaned = asyncio.Event()

    async def block_dependency(*args, **kwargs):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    monkeypatch.setattr(stats_module, dependency, block_dependency)
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
    assert [event.event_type for event in execution.dispatcher.events] == [
        "invocation_start",
        "invocation_end",
    ]
    assert execution.dispatcher.events[-1].payload["status"] == "timeout"
    record(request, key, "stats_timeout")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", profile_stats_parameters("recommendation_isolation"))
async def test_recommendation_error_does_not_poison_next_call(
    key, db_session, monkeypatch, request
):
    execution = await make_execution(key, db_session, monkeypatch)
    dependency = DEPENDENCIES[key[0]]
    positive_dependency = getattr(recommendation_module, dependency)
    calls = 0

    async def fail_once_then_return_positive(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError(_ERROR_SENTINEL)
        return await positive_dependency(*args, **kwargs)

    monkeypatch.setattr(
        recommendation_module, dependency, fail_once_then_return_positive
    )
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
    record(request, key, "recommendation_isolation")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", profile_stats_parameters("stats_isolation"))
async def test_stats_error_does_not_poison_next_call(
    key, db_session, monkeypatch, request
):
    execution = await make_execution(key, db_session, monkeypatch)
    dependency = DEPENDENCIES[key[0]]
    positive_dependency = getattr(stats_module, dependency)
    calls = 0

    async def fail_once_then_return_positive(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise ValueError(_ERROR_SENTINEL)
        return await positive_dependency(*args, **kwargs)

    monkeypatch.setattr(stats_module, dependency, fail_once_then_return_positive)
    failed = await execution.dispatch()
    recovered = await execution.dispatch()

    assert calls == 2
    assert failed.status == "failed" and failed.error_code == "invalid_args"
    assert _ERROR_SENTINEL not in json.dumps(
        failed.model_dump(mode="json"), allow_nan=False
    )
    assert recovered.status == "succeeded", recovered.model_dump()
    assert recovered.error_code is None and recovered.output["success"] is True
    assert execution.env.calls
    assert_subset(execution.example.expected, recovered.output)
    record(request, key, "stats_isolation")


def _profile(kind: str) -> dict[str, Any]:
    profile: dict[str, Any] = {
        "llm_summary": {
            "total_rated": 2,
            "taste_dictionary": {"Synthetic": [2, 8]},
        },
        "chart_data": {"radar": [], "bar_count": [], "bar_score": []},
        "watched_ids": [101],
    }
    if kind == "object":
        profile["chart_data"]["unsafe"] = _UnsafeValue()
    elif kind == "nan":
        profile["chart_data"]["radar"] = [float("nan")]
    elif kind == "bad_shape":
        profile["chart_data"] = "invalid-chart-shape"
    else:
        raise AssertionError(f"Unknown malformed profile kind: {kind}")
    return profile


def _stats_result(action: str, kind: str) -> Any:
    if action == "get_user_stats":
        result: Any = {
            "anime": 1,
            "books": 0,
            "music": 0,
            "games": 0,
            "real": 0,
            "total": 1,
        }
        if kind == "object":
            result["anime"] = _UnsafeValue()
        elif kind == "nan":
            result["anime"] = float("nan")
        elif kind == "bad_shape":
            result["anime"] = "invalid-count"
        else:
            raise AssertionError(f"Unknown malformed stats kind: {kind}")
        return result

    result = {
        "subject_type": 2,
        "total": 1,
        "status_counts": {
            "wish": 0,
            "watched": 1,
            "watching": 0,
            "on_hold": 0,
            "dropped": 0,
        },
        "top_genres": [{"name": "fantasy", "count": 1}],
        "complete": True,
        "genre_subject_count": 1,
        "genre_complete": True,
    }
    if kind == "object":
        result["status_counts"]["watched"] = _UnsafeValue()
    elif kind == "nan":
        result["top_genres"][0]["count"] = float("nan")
    elif kind == "bad_shape":
        result["status_counts"] = "invalid-status-counts"
    else:
        raise AssertionError(f"Unknown malformed stats kind: {kind}")
    return result


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "key", profile_stats_parameters("recommendation_serialization")
)
async def test_recommendation_serialization_rejects_unsafe_results(
    key, db_session, monkeypatch, request
):
    execution = await make_execution(key, db_session, monkeypatch)
    positive = await execution.dispatch()
    assert positive.status == "succeeded", positive.model_dump()
    assert positive.error_code is None and positive.output["success"] is True
    assert execution.env.calls
    assert_subset(execution.example.expected, positive.output)
    encoded = json.dumps(positive.model_dump(mode="json"), allow_nan=False)
    assert InvocationResult.model_validate(json.loads(encoded)) == positive

    calls: list[Any] = []

    for kind in ("object", "nan", "bad_shape"):
        calls.clear()

        def malformed_profile(collections, *, _kind=kind):
            calls.append(collections)
            return _profile(_kind)

        monkeypatch.setattr(
            recommendation_module, "generate_user_profile", malformed_profile
        )
        result = await execution.dispatch()

        assert len(calls) == 1
        assert result.status == "failed" and result.error_code == "invalid_output", (
            f"{key[0]} {kind}: {result.model_dump()}"
        )
        serialized = json.dumps(result.model_dump(mode="json"), allow_nan=False)
        assert _OUTPUT_SENTINEL not in serialized
        assert "invalid-chart-shape" not in serialized

    record(request, key, "recommendation_serialization")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", profile_stats_parameters("stats_serialization"))
async def test_stats_serialization_rejects_unsafe_results(
    key, db_session, monkeypatch, request
):
    execution = await make_execution(key, db_session, monkeypatch)
    positive = await execution.dispatch()
    assert positive.status == "succeeded", positive.model_dump()
    assert positive.error_code is None and positive.output["success"] is True
    assert execution.env.calls
    assert_subset(execution.example.expected, positive.output)
    encoded = json.dumps(positive.model_dump(mode="json"), allow_nan=False)
    assert InvocationResult.model_validate(json.loads(encoded)) == positive

    dependency = DEPENDENCIES[key[0]]
    for kind in ("object", "nan", "bad_shape"):
        calls = []

        async def malformed_dependency(*args, _kind=kind, **kwargs):
            calls.append((args, kwargs))
            return _stats_result(key[0], _kind)

        monkeypatch.setattr(stats_module, dependency, malformed_dependency)
        result = await execution.dispatch()

        assert len(calls) == 1
        assert result.status == "failed" and result.error_code == "invalid_output"
        serialized = json.dumps(result.model_dump(mode="json"), allow_nan=False)
        assert _OUTPUT_SENTINEL not in serialized
        assert "invalid-count" not in serialized
        assert "invalid-status-counts" not in serialized

    record(request, key, "stats_serialization")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "key", profile_stats_parameters("recommendation_authorization")
)
async def test_recommendation_authorization_rejects_anonymous_and_spoofed_identity(
    key, db_session, monkeypatch, request
):
    anonymous = await make_execution(key, db_session, monkeypatch, authenticated=False)
    assert anonymous.descriptor.requires_auth is True
    assert anonymous.descriptor.is_side_effect is False
    assert anonymous.descriptor.approval_required is False
    denied = await anonymous.dispatch()
    assert denied.status == "denied" and denied.error_code == "unauthorized"
    assert not anonymous.env.calls and not anonymous.dispatcher.events

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
            assert not execution.env.calls and not execution.dispatcher.events

    record(request, key, "recommendation_authorization")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", profile_stats_parameters("stats_authorization"))
async def test_stats_authorization_rejects_anonymous_and_spoofed_identity(
    key, db_session, monkeypatch, request
):
    anonymous = await make_execution(key, db_session, monkeypatch, authenticated=False)
    assert anonymous.descriptor.requires_auth is True
    assert anonymous.descriptor.is_side_effect is False
    assert anonymous.descriptor.approval_required is False
    denied = await anonymous.dispatch()
    assert denied.status == "denied" and denied.error_code == "unauthorized"
    assert not anonymous.env.calls and not anonymous.dispatcher.events

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
            assert not execution.env.calls and not execution.dispatcher.events

    record(request, key, "stats_authorization")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", profile_stats_parameters("recommendation_dispatcher"))
async def test_recommendation_dispatcher_enforces_read_contract_and_version(
    key, db_session, monkeypatch, request
):
    execution = await make_execution(key, db_session, monkeypatch)
    assert execution.descriptor.is_side_effect is False
    assert execution.descriptor.approval_required is False

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

    for parameter in (
        {"save": True},
        {"refresh": True},
        {"sql": "synthetic query"},
    ):
        invalid = execution.example.arguments.copy()
        invalid.update(parameter)
        result = await execution.dispatch(invalid)
        assert result.status == "denied" and result.error_code == "invalid_request"
        assert not execution.env.calls and not execution.dispatcher.events

    # The public compatibility argument remains accepted, while the runtime's
    # trusted collection read supplies the actual data for this invocation.
    arguments = execution.example.arguments.copy()
    arguments["collections"] = [
        {"rate": 1, "subject": {"id": 999, "name": "untrusted example"}}
    ]
    result = await execution.dispatch(arguments)
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
    assert result.run_id == execution.context.run_id
    assert result.trace_id == execution.context.trace_id
    record(request, key, "recommendation_dispatcher")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", profile_stats_parameters("stats_dispatcher"))
async def test_stats_dispatcher_enforces_read_contract_and_version(
    key, db_session, monkeypatch, request
):
    execution = await make_execution(key, db_session, monkeypatch)
    assert execution.descriptor.is_side_effect is False
    assert execution.descriptor.approval_required is False

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

    for parameter in (
        {"save": True},
        {"refresh": True},
        {"sql": "synthetic query"},
    ):
        invalid = execution.example.arguments.copy()
        invalid.update(parameter)
        result = await execution.dispatch(invalid)
        assert result.status == "denied" and result.error_code == "invalid_request"
        assert not execution.env.calls and not execution.dispatcher.events

    if key[0] == "get_collection_statistics":
        invalid_type = execution.example.arguments.copy()
        invalid_type["subject_type"] = 999
        result = await execution.dispatch(invalid_type)
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
    assert result.run_id == execution.context.run_id
    assert result.trace_id == execution.context.trace_id
    record(request, key, "stats_dispatcher")
