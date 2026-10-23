"""Real Runtime/Dispatcher observations for the frozen System action."""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import replace
from datetime import datetime
from typing import Any

import pytest

from app.capabilities import system as system_capability
from app.harness.authority import RUNTIME_OWNED_FIELDS
from app.harness.budget import CancellationToken, RunBudget
from app.harness.contracts import InvocationResult
from app.harness.normalizer import _schema_error
from tests.capabilities.contracts.plugin import record
from tests.capabilities.contracts.system_support import (
    SYSTEM_PRIVATE,
    FixedSystemDateTime,
    assert_no_model_calls,
    capture_application_logs,
    make_system_execution,
    system_parameters,
)

_FIXED_PAYLOAD = {
    "current_time": "2026-01-02 03:04:05",
    "current_date": "2026-01-02",
    "current_year": 2026,
    "current_month": 1,
    "current_day": 2,
    "current_hour": 3,
    "current_minute": 4,
    "current_second": 5,
    "weekday": 4,
    "weekday_cn": "星期五",
    # The local timezone decides the epoch value; success asserts the type and
    # the other fixed fields instead of pinning a machine-specific offset.
    "timestamp": 0.0,
    "timezone": "本地时间",
}


class _RaisingDateTime(datetime):
    @classmethod
    def now(cls, tz: Any = None) -> "_RaisingDateTime":
        raise RuntimeError(SYSTEM_PRIVATE)


def _wire(result: Any) -> str:
    return json.dumps(result.model_dump(mode="json"), allow_nan=False)


def _assert_common_success(result: Any, descriptor_name: str) -> None:
    assert result.status == "succeeded"
    assert result.capability == descriptor_name
    assert result.capability_version == "v1"
    assert result.error_code is None
    assert result.output["success"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("key", system_parameters("system_error"))
async def test_system_error_observation(key, db_session, monkeypatch, caplog, request):
    execution = await make_system_execution(key, db_session)
    monkeypatch.setattr(system_capability, "datetime", _RaisingDateTime)

    with capture_application_logs(caplog):
        logging.getLogger("app.harness.runtime").error(
            "system-contract-log-capture-probe"
        )
        result = await execution.dispatch()
        assert "system-contract-log-capture-probe" in caplog.text

    assert result.status == "failed"
    assert result.error_code == "internal"
    assert result.retryable is False
    assert result.output["error_type"] == "internal"
    assert result.output["message"] == "Capability execution failed"
    assert SYSTEM_PRIVATE not in _wire(result)
    assert SYSTEM_PRIVATE not in caplog.text
    assert all(item.exc_info is None for item in caplog.records)
    unknown = await execution.capability.execute("unknown")
    assert unknown == {
        "success": False,
        "error": "Unknown action: unknown",
        "error_type": "invalid_action",
    }
    direct = await execution.capability.execute("current_time")
    assert direct == {
        "success": False,
        "error": "System time lookup failed",
        "error_type": "internal",
    }
    assert SYSTEM_PRIVATE not in json.dumps(direct, ensure_ascii=False)
    invocation_events = [
        event
        for event in execution.dispatcher.events
        if event.invocation_id == result.invocation_id
    ]
    assert [event.event_type for event in invocation_events] == [
        "invocation_start",
        "invocation_end",
    ]
    assert invocation_events[-1].payload == {
        "status": "failed",
        "error_code": "internal",
    }
    assert_no_model_calls(execution)
    record(request, key, "system_error")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", system_parameters("system_timeout"))
async def test_system_timeout_observation(key, db_session, monkeypatch, request):
    execution = await make_system_execution(key, db_session)
    entered = asyncio.Event()
    cleaned = asyncio.Event()

    async def blocking_execute(_action: str, **kwargs: Any) -> dict[str, Any]:
        assert kwargs == {}
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()
        raise AssertionError("Blocking System execution must be cancelled")

    monkeypatch.setattr(execution.capability, "execute", blocking_execute)
    descriptors = [
        replace(descriptor, timeout_seconds=0.02)
        if descriptor.name == execution.descriptor.name
        else descriptor
        for descriptor in execution.capability.actions()
    ]
    monkeypatch.setattr(execution.capability, "actions", lambda: descriptors)
    execution.registry.unregister("system")
    execution.registry.register(execution.capability)

    controls = execution.dispatcher._run_with_controls

    async def armed_controls(operation, timeout_seconds, cancellation):
        task = asyncio.ensure_future(operation)
        try:
            await asyncio.wait_for(entered.wait(), timeout=5)
            return await controls(task, timeout_seconds, cancellation)
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    monkeypatch.setattr(execution.dispatcher, "_run_with_controls", armed_controls)

    timed_out = await execution.dispatch()
    assert timed_out.status == "timeout"
    assert timed_out.error_code == "timeout"
    assert timed_out.retryable is False
    assert cleaned.is_set()
    timeout_events = [
        event
        for event in execution.dispatcher.events
        if event.invocation_id == timed_out.invocation_id
    ]
    assert [event.event_type for event in timeout_events] == [
        "invocation_start",
        "invocation_end",
    ]
    assert timeout_events[-1].payload == {
        "status": "timeout",
        "error_code": "timeout",
    }

    denied = await execution.dispatch(budget=RunBudget(max_tool_calls=0))
    assert denied.status == "denied"
    assert denied.error_code == "budget_exceeded"

    cancellation = CancellationToken()
    cancellation.cancel()
    cancelled = await execution.dispatch(cancellation=cancellation)
    assert cancelled.status == "cancelled"
    assert cancelled.error_code == "cancelled"

    assert_no_model_calls(execution)
    record(request, key, "system_timeout")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", system_parameters("system_isolation"))
async def test_system_isolation_observation(key, db_session, monkeypatch, request):
    execution = await make_system_execution(key, db_session)
    original_execute = execution.capability.execute

    async def failing_execute(_action: str, **kwargs: Any) -> dict[str, Any]:
        raise RuntimeError(SYSTEM_PRIVATE)

    monkeypatch.setattr(execution.capability, "execute", failing_execute)
    shared_context = execution.context_for(execution.user.id)
    failed = await execution.dispatch(context=shared_context)
    assert failed.status == "failed"
    assert failed.error_code == "internal"
    assert failed.retryable is False
    assert SYSTEM_PRIVATE not in _wire(failed)

    monkeypatch.setattr(execution.capability, "execute", original_execute)
    monkeypatch.setattr(system_capability, "datetime", FixedSystemDateTime)
    healthy = await execution.dispatch(context=shared_context)
    _assert_common_success(healthy, execution.descriptor.name)
    assert healthy.output["current_date"] == "2026-01-02"
    assert healthy.output["weekday"] == 4
    assert healthy.output["success"] is True
    assert failed.invocation_id != healthy.invocation_id
    assert failed.run_id == healthy.run_id
    assert failed.trace_id == healthy.trace_id
    assert SYSTEM_PRIVATE not in _wire(healthy)
    assert_no_model_calls(execution)
    record(request, key, "system_isolation")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", system_parameters("system_serialization"))
async def test_system_serialization_observation(key, db_session, monkeypatch, request):
    execution = await make_system_execution(key, db_session)
    monkeypatch.setattr(system_capability, "datetime", FixedSystemDateTime)

    assert execution.descriptor.output_schema["additionalProperties"] is False
    result = await execution.dispatch()
    _assert_common_success(result, execution.descriptor.name)
    safe_output = result.model_output["safe_output"]
    assert set(safe_output) == set(_FIXED_PAYLOAD)
    assert {key: value for key, value in safe_output.items() if key != "timestamp"} == {
        key: value for key, value in _FIXED_PAYLOAD.items() if key != "timestamp"
    }
    assert isinstance(safe_output["timestamp"], float)
    assert safe_output["timestamp"] > 0
    assert result.output["current_time"] == "2026-01-02 03:04:05"
    assert result.output["weekday_cn"] == "星期五"
    assert (
        _schema_error(safe_output, execution.descriptor.output_schema, "output") is None
    )
    encoded = json.dumps(result.model_dump(mode="json"), allow_nan=False)
    assert InvocationResult.model_validate(json.loads(encoded)) == result

    async def leaked_execute(_action: str, **kwargs: Any) -> dict[str, Any]:
        return {"success": True, **_FIXED_PAYLOAD, "leaked": SYSTEM_PRIVATE}

    monkeypatch.setattr(execution.capability, "execute", leaked_execute)
    leaked = await execution.dispatch()
    assert leaked.status == "failed"
    assert leaked.error_code == "invalid_output"
    assert leaked.output["error_type"] == "invalid_output"
    assert (
        leaked.output["message"]
        == "Capability output did not match its declared contract"
    )
    assert SYSTEM_PRIVATE not in _wire(leaked)

    async def wrong_type_execute(_action: str, **kwargs: Any) -> dict[str, Any]:
        return {"success": True, **_FIXED_PAYLOAD, "weekday": SYSTEM_PRIVATE}

    monkeypatch.setattr(execution.capability, "execute", wrong_type_execute)
    wrong_type = await execution.dispatch()
    assert wrong_type.status == "failed"
    assert wrong_type.error_code == "invalid_output"
    assert SYSTEM_PRIVATE not in _wire(wrong_type)

    assert_no_model_calls(execution)
    record(request, key, "system_serialization")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", system_parameters("system_authorization"))
async def test_system_authorization_observation(key, db_session, monkeypatch, request):
    execution = await make_system_execution(key, db_session)
    assert execution.descriptor.requires_auth is False
    assert execution.descriptor.is_side_effect is False
    assert execution.descriptor.approval_required is False
    assert execution.descriptor.idempotency_mode == "none"

    captured: list[dict[str, Any]] = []
    original_execute = execution.capability.execute

    async def capture_execute(_action: str, **kwargs: Any) -> dict[str, Any]:
        captured.append(dict(kwargs))
        return await original_execute(_action, **kwargs)

    monkeypatch.setattr(execution.capability, "execute", capture_execute)
    monkeypatch.setattr(system_capability, "datetime", FixedSystemDateTime)

    anonymous = await execution.dispatch(context=execution.context_for(None))
    _assert_common_success(anonymous, execution.descriptor.name)
    authenticated = await execution.dispatch(
        context=execution.context_for(execution.user.id)
    )
    _assert_common_success(authenticated, execution.descriptor.name)
    assert len(captured) == 2
    for kwargs in captured:
        assert "user_id" not in kwargs
        assert "db" not in kwargs
        assert "token" not in kwargs

    for principal_id in (0, -1, True, "system-private-principal"):
        hostile = await execution.dispatch(context=execution.context_for(principal_id))
        _assert_common_success(hostile, execution.descriptor.name)
    assert len(captured) == 6
    assert all(not kwargs for kwargs in captured)

    denied = await execution.dispatch(
        context=execution.context_for(execution.user.id, allowlist=frozenset({"media"}))
    )
    assert denied.status == "denied"
    assert denied.error_code == "policy_denied"
    assert len(captured) == 6
    assert_no_model_calls(execution)
    record(request, key, "system_authorization")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", system_parameters("system_dispatcher"))
async def test_system_dispatcher_observation(key, db_session, monkeypatch, request):
    execution = await make_system_execution(key, db_session)
    captured: list[dict[str, Any]] = []
    original_execute = execution.capability.execute

    async def capture_execute(_action: str, **kwargs: Any) -> dict[str, Any]:
        captured.append(dict(kwargs))
        return await original_execute(_action, **kwargs)

    monkeypatch.setattr(execution.capability, "execute", capture_execute)
    context = execution.context_for(execution.user.id)

    forged_values: dict[str, Any] = {
        "user_id": 999999,
        "principal_id": 999999,
        "tenant_id": "system-private-tenant",
        "role": "system-private-role",
        "scope": ["system-private-scope"],
        "db": "system-private-db-handle",
        "token": SYSTEM_PRIVATE,
        "approval_state": {"approved": True},
    }
    assert set(forged_values) == RUNTIME_OWNED_FIELDS
    for name, value in forged_values.items():
        denied = await execution.dispatch(
            arguments={name: value},
            context=context,
            forged_decision=True,
        )
        assert denied.status == "denied"
        assert denied.error_code == "identity_spoofing"
        assert SYSTEM_PRIVATE not in _wire(denied)
    nested = await execution.dispatch(
        arguments={"nested": [{"user_id": 999999}]},
        context=context,
        forged_decision=True,
    )
    assert nested.status == "denied"
    assert nested.error_code == "identity_spoofing"
    assert captured == []

    for name in ("host", "timezone", "client", "credential", "password"):
        denied = await execution.dispatch(
            arguments={name: SYSTEM_PRIVATE},
            context=context,
        )
        assert denied.status == "denied"
        assert denied.error_code == "invalid_request"
        assert SYSTEM_PRIVATE not in _wire(denied)
    assert captured == []

    wrong_version = await execution.dispatch(context=context, version="v999")
    assert wrong_version.status == "denied"
    assert wrong_version.error_code == "not_configured"

    unknown = await execution.dispatch(
        "system.delete_everything",
        context=execution.context_for(action="system.delete_everything"),
    )
    assert unknown.status == "denied"
    assert unknown.error_code == "not_configured"

    respond = await execution.dispatch(context=context, decision_action="respond")
    assert respond.status == "denied"
    assert respond.error_code == "invalid_request"

    mismatch = await execution.dispatch(context=context, run_id="other-system-run")
    assert mismatch.status == "denied"
    assert mismatch.error_code == "policy_denied"
    assert captured == []

    monkeypatch.setattr(system_capability, "datetime", FixedSystemDateTime)
    allowed = await execution.dispatch(context=context)
    _assert_common_success(allowed, execution.descriptor.name)
    assert captured == [{}]
    assert_no_model_calls(execution)
    record(request, key, "system_dispatcher")


@pytest.mark.asyncio
async def test_system_capability_direct_failures_use_safe_envelopes(
    db_session, monkeypatch
):
    execution = await make_system_execution(("get_current_time", "v1"), db_session)

    unknown = await execution.capability.execute("unknown")
    assert unknown == {
        "success": False,
        "error": "Unknown action: unknown",
        "error_type": "invalid_action",
    }

    monkeypatch.setattr(system_capability, "datetime", _RaisingDateTime)
    failed = await execution.capability.execute("current_time")
    assert failed == {
        "success": False,
        "error": "System time lookup failed",
        "error_type": "internal",
    }
    assert SYSTEM_PRIVATE not in json.dumps(failed, ensure_ascii=False)
