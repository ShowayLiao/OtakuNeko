"""Real Media write handlers under dispatch, authority, and recovery probes."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, cast
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.capabilities.types import ActionDescriptor
from app.harness.authority import RUNTIME_OWNED_FIELDS
from app.harness.budget import CancellationToken
from app.harness.capability_adapter import CapabilityAdapter, _payload_hash
from app.harness.contracts import InvocationResult
from app.harness.normalizer import validate_input
from app.harness.persistence.idempotency import SqlIdempotencyStore
from app.harness.policy import Approval
from app.models.agent_run import AgentInvocation, AgentRunEvent
from tests.capabilities.contracts.media_write_support import (
    MEDIA_PRIVATE,
    MediaWriteExecution,
    arguments_for,
    assert_no_model_calls,
    make_write_execution,
    media_write_parameters,
    sdk_method,
)
from tests.capabilities.contracts.plugin import record

_ERROR_SENTINEL = "media-write-private-provider-diagnostic"
_RUNTIME_FIELDS = {
    "run_id",
    "decision_id",
    "invocation_id",
    "trace_id",
    "sequence",
    "latency_ms",
}


def _wire(result: InvocationResult) -> str:
    return json.dumps(
        result.model_dump(mode="json"), ensure_ascii=False, allow_nan=False
    )


def _assert_json_safe(result: InvocationResult) -> None:
    encoded = _wire(result)
    assert InvocationResult.model_validate(json.loads(encoded)) == result


def _business_output(result: InvocationResult) -> dict[str, Any]:
    return {
        key: value for key, value in result.output.items() if key not in _RUNTIME_FIELDS
    }


def _assert_success(execution: MediaWriteExecution, result: InvocationResult) -> None:
    assert result.status == "succeeded", result.model_dump()
    assert result.error_code is None
    assert result.retryable is False
    assert result.capability == execution.key[0]
    assert result.capability_version == execution.key[1]
    assert result.output["success"] is True
    assert result.output["operation"]["status"] == "succeeded"
    assert isinstance(result.output["operation"]["message"], str)
    assert result.output["idempotency_key"]
    assert MEDIA_PRIVATE not in _wire(result)
    _assert_json_safe(result)


def _assert_rejected(
    result: InvocationResult, expected_codes: set[str] | None = None
) -> None:
    assert result.status in {"denied", "failed", "cancelled", "timeout"}, (
        result.model_dump()
    )
    if expected_codes is not None:
        assert result.error_code in expected_codes, result.model_dump()
    _assert_json_safe(result)


def _assert_schema_has_no_runtime_identity(schema: Any) -> None:
    if isinstance(schema, dict):
        assert not (set(schema.get("properties", {})) & RUNTIME_OWNED_FIELDS)
        assert not (set(schema.get("required", [])) & RUNTIME_OWNED_FIELDS)
        for value in schema.values():
            _assert_schema_has_no_runtime_identity(value)
    elif isinstance(schema, list):
        for value in schema:
            _assert_schema_has_no_runtime_identity(value)


def _write_count(execution: MediaWriteExecution) -> int:
    return execution.client.write_calls


def _assert_no_sdk(execution: MediaWriteExecution) -> None:
    assert execution.client_factory.constructor_calls == 0
    assert execution.client.calls == []


def _changed_payload(action: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
    changed = json.loads(json.dumps(arguments))
    if action in {"add_rss_feed", "upsert_rss_feed"}:
        changed["url"] += "&revision=changed"
        return changed
    if action == "set_rss_rule":
        changed["rule"]["mustContain"] = "Changed synthetic title"
        return changed
    # For the remove actions, the only public data field identifies the resource
    # and therefore also changes the idempotency scope.
    return None


def _shared_resource_collision(
    action: str, suffix: str
) -> tuple[str, dict[str, Any], str, dict[str, Any]]:
    """Return two valid actions that name the same qB resource scope."""
    if action in {"add_rss_feed", "upsert_rss_feed"}:
        name = f"contract-action-bound-{suffix}"
        args = {
            "url": f"https://feeds.synthetic.invalid/action-{suffix}.xml",
            "name": name,
        }
        return "add_rss_feed", args, "upsert_rss_feed", args
    if action == "remove_rss_feed":
        name = f"contract-remove-collision-{suffix}"
        return (
            "add_rss_feed",
            {
                "url": f"https://feeds.synthetic.invalid/remove-{suffix}.xml",
                "name": name,
            },
            "remove_rss_feed",
            {"item_path": name},
        )
    rule_name = f"contract-rule-collision-{suffix}"
    return (
        "set_rss_rule",
        {"rule_name": rule_name, "rule": arguments_for("set_rss_rule")["rule"]},
        "remove_rss_rule",
        {"rule_name": rule_name},
    )


async def _replay_with_fresh_session(
    execution: MediaWriteExecution,
    *,
    arguments: dict[str, Any],
    idempotency_key: str,
    action: str | None = None,
):
    target = action or execution.key[0]
    factory = async_sessionmaker(
        execution.db.bind,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with factory() as recovered_session:
        dispatcher = execution.make_dispatcher(db=recovered_session, action=target)
        context = execution.context_for(action=target)
        return await execution.dispatch(
            arguments,
            action=target,
            dispatcher=dispatcher,
            context=context,
            idempotency_key=idempotency_key,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("key", media_write_parameters("media_write_error"))
async def test_media_write_errors_are_normalized_and_non_retryable(
    key, db_session, monkeypatch, caplog, request
):
    import qbittorrentapi

    execution = await make_write_execution(key, db_session, monkeypatch)
    method = sdk_method(key[0])
    execution.client.failures[method] = qbittorrentapi.APIConnectionError(
        _ERROR_SENTINEL
    )

    logger = logging.getLogger("app.services.qb_service")
    with caplog.at_level(logging.ERROR, logger=logger.name):
        unknown = await execution.dispatch(
            idempotency_key="media-write-unknown-" + uuid4().hex
        )

    assert unknown.status == "failed", unknown.model_dump()
    assert unknown.error_code == "attention_required"
    assert unknown.retryable is False
    assert _ERROR_SENTINEL not in _wire(unknown)
    assert unknown.output["message"]
    assert _ERROR_SENTINEL not in caplog.text
    assert all(item.exc_info is None for item in caplog.records)
    assert len(execution.client.calls_for(method)) == 1
    if key[0] == "upsert_rss_feed":
        # The old item may have been removed, but the unknown add response must
        # not trigger a second add as speculative compensation.
        assert len(execution.client.calls_for("rss_remove_item")) == 1
        assert len(execution.client.calls_for("rss_add_feed")) == 1

    execution.client.failures["auth_log_in"] = qbittorrentapi.LoginFailed(
        _ERROR_SENTINEL
    )
    auth_failure = await execution.dispatch(
        idempotency_key="media-write-auth-error-" + uuid4().hex
    )
    assert auth_failure.status == "failed"
    assert auth_failure.error_code == "qb_authentication_failed"
    assert auth_failure.retryable is False
    assert _ERROR_SENTINEL not in _wire(auth_failure)
    assert _ERROR_SENTINEL not in caplog.text
    assert_no_model_calls(execution)
    record(request, key, "media_write_error")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", media_write_parameters("media_write_timeout"))
async def test_media_write_timeout_and_cancel_freeze_unknown_side_effects(
    key, db_session, monkeypatch, request
):
    execution = await make_write_execution(key, db_session, monkeypatch)
    method = sdk_method(key[0])
    controls = execution.dispatcher._run_with_controls
    execution.client.block_write(method)
    request.addfinalizer(
        lambda: execution.client.release_and_join_writes(
            verify_upsert=key[0] == "upsert_rss_feed"
        )
    )

    async def arm_timeout(operation, _timeout_seconds, cancellation):
        task = asyncio.ensure_future(operation)
        try:
            entered = await asyncio.wait_for(
                asyncio.to_thread(execution.client.entered[method].wait, 5), timeout=6
            )
            assert entered, "Media write did not enter the blocking SDK method"
            # This timeout starts only once the synchronous SDK side effect has
            # already happened and its response is held by the transport double.
            return await controls(task, 0.05, cancellation)
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    monkeypatch.setattr(execution.dispatcher, "_run_with_controls", arm_timeout)
    timeout_key = "media-write-timeout-" + uuid4().hex
    timed_out = await execution.dispatch(idempotency_key=timeout_key)
    timeout_snapshot = _wire(timed_out)
    assert timed_out.status == "timeout" and timed_out.error_code == "timeout"
    assert timed_out.retryable is False
    assert execution.client.entered[method].is_set()
    assert not execution.client.finished[method].is_set()
    assert _write_count(execution) >= 1

    await asyncio.to_thread(
        execution.client.release_and_join_writes,
        verify_upsert=key[0] == "upsert_rss_feed",
    )
    assert _wire(timed_out) == timeout_snapshot
    timeout_end = [
        event
        for event in execution.dispatcher.events
        if event.event_type == "invocation_end"
        and event.invocation_id == timed_out.invocation_id
    ]
    assert len(timeout_end) == 1
    assert timeout_end[0].payload["status"] == "timeout"

    await execution.db.commit()
    writes_after_timeout = _write_count(execution)
    timeout_arguments = arguments_for(key[0])
    replay_timeout = await _replay_with_fresh_session(
        execution,
        arguments=timeout_arguments,
        idempotency_key=timeout_key,
    )
    _assert_rejected(replay_timeout, {"attention_required"})
    assert _write_count(execution) == writes_after_timeout

    monkeypatch.setattr(execution.dispatcher, "_run_with_controls", controls)
    execution.client.block_write(method)
    cancel_key = "media-write-cancel-" + uuid4().hex
    cancel_arguments = arguments_for(key[0])
    if key[0] == "upsert_rss_feed":
        cancel_arguments["name"] = "media-write-cancel-upsert-" + uuid4().hex
        cancel_arguments["url"] = (
            "https://feeds.synthetic.invalid/cancel-" + uuid4().hex + ".xml"
        )
    cancellation = CancellationToken()
    cancel_task = asyncio.create_task(
        execution.dispatch(
            cancel_arguments,
            idempotency_key=cancel_key,
            cancellation=cancellation,
        )
    )
    try:
        entered = await asyncio.wait_for(
            asyncio.to_thread(execution.client.entered[method].wait, 5), timeout=6
        )
        assert entered, "Media write did not enter the blocking SDK method"
        cancellation.cancel()
        cancelled = await asyncio.wait_for(cancel_task, timeout=5)
    finally:
        if not cancel_task.done():
            cancel_task.cancel()
        await asyncio.gather(cancel_task, return_exceptions=True)

    cancel_snapshot = _wire(cancelled)
    assert cancelled.status == "cancelled" and cancelled.error_code == "cancelled"
    assert cancelled.retryable is False
    assert execution.client.entered[method].is_set()
    assert not execution.client.finished[method].is_set()
    await asyncio.to_thread(
        execution.client.release_and_join_writes,
        verify_upsert=key[0] == "upsert_rss_feed",
    )
    assert _wire(cancelled) == cancel_snapshot
    cancel_end = [
        event
        for event in execution.dispatcher.events
        if event.event_type == "invocation_end"
        and event.invocation_id == cancelled.invocation_id
    ]
    assert len(cancel_end) == 1
    assert cancel_end[0].payload["status"] == "cancelled"

    await execution.db.commit()
    writes_after_cancel = _write_count(execution)
    replay_cancel = await _replay_with_fresh_session(
        execution,
        arguments=cancel_arguments,
        idempotency_key=cancel_key,
    )
    _assert_rejected(replay_cancel, {"attention_required"})
    assert _write_count(execution) == writes_after_cancel
    start_ids = [
        event.invocation_id
        for event in execution.dispatcher.events
        if event.event_type == "invocation_start"
    ]
    end_ids = [
        event.invocation_id
        for event in execution.dispatcher.events
        if event.event_type == "invocation_end"
    ]
    assert len(start_ids) == len(set(start_ids))
    assert set(start_ids) == set(end_ids)
    assert_no_model_calls(execution)
    record(request, key, "media_write_timeout")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", media_write_parameters("media_write_isolation"))
async def test_media_write_idempotency_scope_is_bound_to_trusted_principal(
    key, db_session, monkeypatch, request
):
    execution = await make_write_execution(key, db_session, monkeypatch)
    stable_key = "media-write-principal-scope-" + uuid4().hex
    public_arguments = arguments_for(key[0])

    owner_result = await execution.dispatch(
        public_arguments,
        idempotency_key=stable_key,
    )
    _assert_success(execution, owner_result)
    calls_after_owner = len(execution.client.calls)

    # qBittorrent's configured allowlist is shared; this verifies that the
    # durable key scope uses the trusted principal without claiming resource
    # ownership or per-user isolation inside qBittorrent.
    other_dispatcher = execution.make_dispatcher(
        action=key[0], user=execution.other_user
    )
    other_result = await execution.dispatch(
        public_arguments,
        context=execution.context_for(execution.other_user.id),
        dispatcher=other_dispatcher,
        idempotency_key=stable_key,
    )
    _assert_success(execution, other_result)
    assert len(execution.client.calls) > calls_after_owner

    calls_after_other = len(execution.client.calls)
    owner_replay = await execution.dispatch(
        public_arguments,
        idempotency_key=stable_key,
    )
    _assert_success(execution, owner_replay)
    assert len(execution.client.calls) == calls_after_other
    assert owner_replay.output["idempotency_key"] == stable_key
    assert other_result.output["idempotency_key"] == stable_key
    assert_no_model_calls(execution)
    record(request, key, "media_write_isolation")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", media_write_parameters("media_write_serialization"))
async def test_media_write_success_output_is_structured_and_secret_safe(
    key, db_session, monkeypatch, request
):
    execution = await make_write_execution(key, db_session, monkeypatch)
    definition = execution.registry.get_public_definition(*key)
    assert definition is not None
    descriptor: ActionDescriptor = execution.descriptor
    assert descriptor.input_schema["type"] == "object"
    assert descriptor.input_schema["additionalProperties"] is False
    assert descriptor.input_schema["properties"]["idempotency_key"]
    assert descriptor.output_schema["type"] == "object"
    assert {"operation", "idempotency_key"}.issubset(
        set(descriptor.output_schema.get("required", []))
    )
    operation_schema = descriptor.output_schema["properties"]["operation"]
    assert {"status", "message"}.issubset(set(operation_schema["required"]))
    _assert_schema_has_no_runtime_identity(descriptor.input_schema)
    _assert_schema_has_no_runtime_identity(definition.input_schema)

    public_arguments = arguments_for(key[0])
    validate_input(
        {**public_arguments, "idempotency_key": "schema-check-" + uuid4().hex},
        descriptor,
    )
    json.dumps(definition.to_dict(), ensure_ascii=False, allow_nan=False)

    result = await execution.dispatch(
        idempotency_key="media-write-serialization-" + uuid4().hex
    )
    _assert_success(execution, result)
    wire = _wire(result)
    assert MEDIA_PRIVATE not in wire
    assert "torrentParams" not in wire
    assert all(
        MEDIA_PRIVATE not in json.dumps(event.payload)
        for event in execution.dispatcher.events
    )
    assert execution.client_factory.constructor_calls == 1
    assert_no_model_calls(execution)
    record(request, key, "media_write_serialization")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", media_write_parameters("media_write_authorization"))
async def test_media_write_authorization_fails_closed_before_sdk(
    key, db_session, monkeypatch, request
):
    from app.core.config import settings

    execution = await make_write_execution(key, db_session, monkeypatch)
    public_arguments = arguments_for(key[0])
    stable_key = "media-write-authorization-" + uuid4().hex

    anonymous_dispatcher = execution.make_dispatcher(
        authenticated=False,
        durable=False,
    )
    anonymous = await execution.dispatch(
        public_arguments,
        context=execution.context_for(None),
        dispatcher=anonymous_dispatcher,
        idempotency_key=stable_key,
    )
    _assert_rejected(anonymous, {"unauthorized"})

    invalid_context = execution.context_for(0)
    invalid = await execution.dispatch(
        public_arguments,
        context=invalid_context,
        idempotency_key="media-write-invalid-principal-" + uuid4().hex,
    )
    _assert_rejected(invalid, {"unauthorized"})

    boolean_context = execution.context_for(True)
    boolean_principal = await execution.dispatch(
        public_arguments,
        context=boolean_context,
        idempotency_key="media-write-bool-principal-" + uuid4().hex,
    )
    _assert_rejected(boolean_principal, {"unauthorized", "forbidden"})

    with pytest.raises(ValidationError):
        await execution.dispatch(
            {**public_arguments, "user_id": execution.user.id + 100},
            idempotency_key="media-write-spoof-" + uuid4().hex,
        )

    no_store = execution.make_dispatcher(durable=False)
    no_store_result = await execution.dispatch(
        public_arguments,
        dispatcher=no_store,
        idempotency_key="media-write-no-store-" + uuid4().hex,
    )
    _assert_rejected(no_store_result, {"idempotency_required"})

    no_side_effects = execution.make_dispatcher(allow_side_effects=False)
    side_effect_denied = await execution.dispatch(
        public_arguments,
        dispatcher=no_side_effects,
        idempotency_key="media-write-side-effects-disabled-" + uuid4().hex,
    )
    _assert_rejected(side_effect_denied, {"policy_denied"})

    missing_key = await execution.dispatch(
        include_key=False,
    )
    _assert_rejected(missing_key, {"idempotency_required", "invalid_request"})

    monkeypatch.setattr(settings, "ENABLE_QB_PROXY", False)
    disabled = await execution.dispatch(
        public_arguments,
        idempotency_key="media-write-disabled-provider-" + uuid4().hex,
    )
    _assert_rejected(disabled, {"not_configured"})

    monkeypatch.setattr(settings, "ENABLE_QB_PROXY", True)
    monkeypatch.setattr(
        settings,
        "QB_ALLOWED_USER_IDS",
        f"{execution.user.id},not-a-number",
    )
    malformed_allowlist = await execution.dispatch(
        public_arguments,
        idempotency_key="media-write-malformed-allowlist-" + uuid4().hex,
    )
    _assert_rejected(malformed_allowlist, {"forbidden"})

    _assert_no_sdk(execution)
    assert_no_model_calls(execution)
    record(request, key, "media_write_authorization")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", media_write_parameters("media_write_dispatcher"))
async def test_media_write_executes_only_through_registered_dispatcher(
    key, db_session, monkeypatch, request
):
    execution = await make_write_execution(key, db_session, monkeypatch)
    invalid = await execution.dispatch(
        {**arguments_for(key[0]), "unregistered_field": "rejected"},
        idempotency_key="media-write-dispatch-invalid-" + uuid4().hex,
    )
    _assert_rejected(invalid, {"invalid_request", "invalid_args"})
    _assert_no_sdk(execution)

    result = await execution.dispatch(
        idempotency_key="media-write-dispatch-" + uuid4().hex
    )
    _assert_success(execution, result)
    events = execution.dispatcher.events
    assert [event.event_type for event in events] == [
        "invocation_start",
        "invocation_end",
    ]
    assert all(event.invocation_id == result.invocation_id for event in events)
    assert events[-1].payload["status"] == "succeeded"
    assert execution.client_factory.constructor_fields == [
        frozenset({"host", "username", "password"})
    ]
    assert_no_model_calls(execution)
    record(request, key, "media_write_dispatcher")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", media_write_parameters("media_write_approval"))
async def test_media_write_requires_approval_bound_to_principal_and_action(
    key, db_session, monkeypatch, request
):
    execution = await make_write_execution(key, db_session, monkeypatch)

    missing = execution.make_dispatcher(approval=None, use_default_approval=False)
    missing_result = await execution.dispatch(
        dispatcher=missing,
        idempotency_key="media-write-no-approval-" + uuid4().hex,
    )
    _assert_rejected(missing_result, {"policy_denied", "approval_required"})

    rejected = execution.make_dispatcher(
        approval=Approval(
            approval_id=uuid4().hex,
            approved=False,
            principal_id=execution.user.id,
            action=key[0],
        ),
        use_default_approval=False,
    )
    denied_rejected = await execution.dispatch(
        dispatcher=rejected,
        idempotency_key="media-write-rejected-approval-" + uuid4().hex,
    )
    _assert_rejected(denied_rejected, {"policy_denied"})

    wrong_principal = execution.make_dispatcher(
        approval=Approval(
            approval_id=uuid4().hex,
            principal_id=execution.other_user.id,
            action=key[0],
        ),
        use_default_approval=False,
    )
    denied_principal = await execution.dispatch(
        dispatcher=wrong_principal,
        idempotency_key="media-write-wrong-principal-" + uuid4().hex,
    )
    _assert_rejected(denied_principal, {"policy_denied"})

    wrong_action = execution.make_dispatcher(
        approval=Approval(
            approval_id=uuid4().hex,
            principal_id=execution.user.id,
            action="another_media_write_action",
        ),
        use_default_approval=False,
    )
    denied_action = await execution.dispatch(
        dispatcher=wrong_action,
        idempotency_key="media-write-wrong-action-" + uuid4().hex,
    )
    _assert_rejected(denied_action, {"policy_denied"})
    _assert_no_sdk(execution)

    approved = await execution.dispatch(
        idempotency_key="media-write-approved-" + uuid4().hex
    )
    _assert_success(execution, approved)
    assert execution.client_factory.constructor_calls == 1
    assert _write_count(execution) >= 1
    assert_no_model_calls(execution)
    record(request, key, "media_write_approval")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", media_write_parameters("media_write_idempotency"))
async def test_media_write_idempotency_replays_and_rejects_collisions(
    key, db_session, monkeypatch, request
):
    execution = await make_write_execution(key, db_session, monkeypatch)
    action = key[0]
    stable_key = "media-write-explicit-" + uuid4().hex
    public_arguments = arguments_for(action)

    first = await execution.dispatch(
        public_arguments,
        idempotency_key=stable_key,
    )
    _assert_success(execution, first)
    calls_after_first = len(execution.client.calls)

    replay = await execution.dispatch(
        public_arguments,
        idempotency_key=stable_key,
    )
    _assert_success(execution, replay)
    assert _business_output(replay) == _business_output(first)
    assert len(execution.client.calls) == calls_after_first

    changed_arguments = _changed_payload(action, public_arguments)
    if changed_arguments is not None:
        changed = await execution.dispatch(
            changed_arguments,
            idempotency_key=stable_key,
        )
        _assert_rejected(changed, {"idempotency_conflict"})
        assert len(execution.client.calls) == calls_after_first

    first_action, first_arguments, second_action, second_arguments = (
        _shared_resource_collision(action, uuid4().hex[:8])
    )
    collision_key = "media-write-cross-action-" + uuid4().hex
    first_dispatcher = execution.make_dispatcher(action=first_action)
    first_context = execution.context_for(action=first_action)
    first_action_result = await execution.dispatch(
        first_arguments,
        action=first_action,
        dispatcher=first_dispatcher,
        context=first_context,
        idempotency_key=collision_key,
    )
    assert first_action_result.status == "succeeded", first_action_result.model_dump()
    calls_before_collision = len(execution.client.calls)

    second_dispatcher = execution.make_dispatcher(action=second_action)
    second_context = execution.context_for(action=second_action)
    collision = await execution.dispatch(
        second_arguments,
        action=second_action,
        dispatcher=second_dispatcher,
        context=second_context,
        idempotency_key=collision_key,
    )
    _assert_rejected(collision, {"idempotency_conflict"})
    assert len(execution.client.calls) == calls_before_collision

    concurrent_arguments = arguments_for(action)
    if action in {"add_rss_feed", "upsert_rss_feed"}:
        concurrent_arguments["name"] = "media-write-concurrent-" + uuid4().hex
        concurrent_arguments["url"] = (
            "https://feeds.synthetic.invalid/concurrent-" + uuid4().hex + ".xml"
        )
    concurrent_key = "media-write-concurrent-" + uuid4().hex
    constructors_before = execution.client_factory.constructor_calls
    concurrent = await asyncio.gather(
        execution.dispatch(
            concurrent_arguments,
            idempotency_key=concurrent_key,
        ),
        execution.dispatch(
            concurrent_arguments,
            idempotency_key=concurrent_key,
        ),
    )
    assert all(result.status == "succeeded" for result in concurrent), [
        result.model_dump() for result in concurrent
    ]
    assert execution.client_factory.constructor_calls == constructors_before + 1
    assert_no_model_calls(execution)
    record(request, key, "media_write_idempotency")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", media_write_parameters("media_write_recovery"))
async def test_media_write_recovery_rebuilds_runtime_from_sql_state(
    key, db_session, monkeypatch, request
):
    execution = await make_write_execution(key, db_session, monkeypatch)
    confirmed_key = "media-write-recovered-result-" + uuid4().hex
    arguments = arguments_for(key[0])
    confirmed = await execution.dispatch(
        arguments,
        idempotency_key=confirmed_key,
    )
    _assert_success(execution, confirmed)
    writes_after_success = _write_count(execution)

    replay = await _replay_with_fresh_session(
        execution,
        arguments=arguments,
        idempotency_key=confirmed_key,
    )
    _assert_success(execution, replay)
    assert _business_output(replay) == _business_output(confirmed)
    assert _write_count(execution) == writes_after_success

    unknown_key = "media-write-reserved-unknown-" + uuid4().hex
    public_arguments = {
        **arguments,
        "idempotency_key": unknown_key,
    }
    scope = (
        f"{execution.user.id}:media:"
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

    writes_before_unknown_replay = _write_count(execution)
    factory = async_sessionmaker(
        execution.db.bind,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with factory() as recovered_session:
        rebuilt = execution.make_dispatcher(db=recovered_session, action=key[0])
        unknown = await execution.dispatch(
            arguments,
            dispatcher=rebuilt,
            context=execution.context_for(action=key[0]),
            idempotency_key=unknown_key,
        )
        _assert_rejected(unknown, {"attention_required"})
        assert _write_count(execution) == writes_before_unknown_replay

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

    assert_no_model_calls(execution)
    record(request, key, "media_write_recovery")
