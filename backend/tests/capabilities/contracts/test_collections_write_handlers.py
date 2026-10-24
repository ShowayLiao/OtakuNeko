"""Real Collections write handlers under error, authority, and serialization probes."""

from __future__ import annotations

import asyncio
from dataclasses import replace
import json
import logging
from typing import Any
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from app.capabilities import collections as collections_module
from app.harness.authority import RUNTIME_OWNED_FIELDS
from app.harness.normalizer import validate_input
from app.harness.policy import Approval
from tests.capabilities.contracts.collections_write_support import (
    SCENARIOS,
    assert_no_public_user_id,
    collections_write_parameters,
    install_collections_service_boundary,
    make_collections_write_execution,
    successful_service_result,
)
from tests.capabilities.contracts.plugin import record


_ERROR_SENTINEL = "collections-write-private-diagnostic-sentinel"


def _assert_schema_has_no_runtime_identity(schema) -> None:
    if isinstance(schema, dict):
        assert not (set(schema.get("properties", {})) & RUNTIME_OWNED_FIELDS)
        assert not (set(schema.get("required", [])) & RUNTIME_OWNED_FIELDS)
        for value in schema.values():
            _assert_schema_has_no_runtime_identity(value)
    elif isinstance(schema, list):
        for value in schema:
            _assert_schema_has_no_runtime_identity(value)


def _assert_result_json_safe(result) -> None:
    encoded = json.dumps(result.model_dump(mode="json"), allow_nan=False)
    assert "user_id" not in encoded
    assert "principal_id" not in encoded


def _assert_success(execution, result) -> None:
    action = execution.key[0]
    assert result.status == "succeeded", result.model_dump()
    assert result.error_code is None
    assert result.retryable is False
    assert result.output["success"] is True

    if action in {"create_collection", "update_collection"}:
        collection = result.output["collection"]
        assert collection["source"] == "bangumi"
        assert collection["source_id"] == execution.source_id
        assert type(collection["type"]) is int
        assert "user_id" not in collection
    elif action == "upsert_collection":
        unified = result.output["collection"]
        assert unified["collection"]["source"] == "bangumi"
        assert unified["collection"]["source_id"] == execution.source_id
        assert unified["subject"]["source_id"] == execution.source_id
        assert "user_id" not in unified["collection"]
    elif action == "delete_collection":
        assert result.output["deleted"] is True
    elif action == "batch_upsert_collections":
        assert result.output["processed_count"] == 2
        assert result.output["requested_count"] == 2
    else:
        assert result.output["processed_count"] == 2

    assert_no_public_user_id(result.output)
    _assert_result_json_safe(result)


def _assert_no_service_calls(boundary) -> None:
    assert boundary.calls == []
    assert boundary.unexpected_calls == []


def _assert_rejected(result, error_codes: set[str] | None = None) -> None:
    assert result.status in {"denied", "failed", "approval_required", "paused"}, (
        result.model_dump()
    )
    if error_codes is not None:
        assert result.error_code in error_codes, result.model_dump()
    _assert_result_json_safe(result)


@pytest.mark.asyncio
@pytest.mark.parametrize("key,scenario", collections_write_parameters())
async def test_collections_write_contract(
    key, scenario, db_session, monkeypatch, caplog, request
):
    """Record one required write observation for each action and dimension."""
    assert scenario in SCENARIOS
    execution = await make_collections_write_execution(key, db_session)

    if scenario == "collections_write_error":
        behavior: dict[str, Any] = {"current": None}

        async def route(*args, **kwargs):
            return await behavior["current"](*args, **kwargs)

        boundary = install_collections_service_boundary(
            execution, monkeypatch, handler=route
        )

        async def fail_value_error(*args, **kwargs):
            raise ValueError(_ERROR_SENTINEL)

        behavior["current"] = fail_value_error
        invalid = await execution.dispatch()
        assert invalid.status == "failed" and invalid.error_code == "invalid_args"
        assert invalid.retryable is False
        invalid_json = json.dumps(invalid.model_dump(mode="json"), allow_nan=False)
        assert "Capability execution failed" in invalid_json
        assert _ERROR_SENTINEL not in invalid_json
        assert len(boundary.calls) == 1 and boundary.unexpected_calls == []

        boundary.calls.clear()

        async def fail_runtime_error(*args, **kwargs):
            raise RuntimeError(_ERROR_SENTINEL)

        behavior["current"] = fail_runtime_error
        logger = collections_module.logger
        logger.addHandler(caplog.handler)
        try:
            with caplog.at_level(logging.ERROR, logger=logger.name):
                internal = await execution.dispatch()
        finally:
            logger.removeHandler(caplog.handler)

        assert internal.status == "failed" and internal.error_code == "internal"
        assert internal.retryable is False
        internal_json = json.dumps(internal.model_dump(mode="json"), allow_nan=False)
        assert "Capability execution failed" in internal_json
        assert _ERROR_SENTINEL not in internal_json
        assert len(boundary.calls) == 1 and boundary.unexpected_calls == []
        records = [item for item in caplog.records if item.name == logger.name]
        assert len(records) == 1
        assert records[0].getMessage() == "collection_capability_failed"
        assert records[0].action == execution.descriptor.name
        assert records[0].error_type == "RuntimeError"
        assert records[0].exc_info is None
        assert _ERROR_SENTINEL not in repr(records[0].__dict__)

    elif scenario == "collections_write_timeout":
        entered = asyncio.Event()
        cleaned = asyncio.Event()
        call_count = 0

        async def block_once_then_succeed(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                entered.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cleaned.set()
            return successful_service_result(execution)

        boundary = install_collections_service_boundary(
            execution, monkeypatch, handler=block_once_then_succeed
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

        dispatcher = execution.dispatcher
        run_controls = dispatcher._run_with_controls

        async def arm_timeout(operation, timeout_seconds, cancellation):
            task = asyncio.create_task(operation)
            try:
                await asyncio.wait_for(entered.wait(), timeout=5)
                return await run_controls(task, timeout_seconds, cancellation)
            finally:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)

        monkeypatch.setattr(dispatcher, "_run_with_controls", arm_timeout)
        timed_out = await execution.dispatch()
        assert entered.is_set() and cleaned.is_set()
        assert timed_out.status == "timeout" and timed_out.error_code == "timeout"
        assert timed_out.retryable is False
        assert len(boundary.calls) == 1 and boundary.unexpected_calls == []

        monkeypatch.setattr(
            execution.capability, "actions", lambda: original_descriptors
        )
        execution.dispatcher.registry.unregister(execution.capability.name)
        execution.dispatcher.registry.register(execution.capability)
        monkeypatch.setattr(dispatcher, "_run_with_controls", run_controls)

        recovered = await execution.dispatch()
        _assert_success(execution, recovered)
        assert call_count == 2 and len(boundary.calls) == 2

    elif scenario == "collections_write_isolation":
        call_count = 0

        async def fail_once_then_succeed(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError(_ERROR_SENTINEL)
            return successful_service_result(execution)

        boundary = install_collections_service_boundary(
            execution, monkeypatch, handler=fail_once_then_succeed
        )
        failed = await execution.dispatch()
        assert failed.status == "failed" and failed.error_code == "internal"
        assert failed.retryable is False
        assert _ERROR_SENTINEL not in json.dumps(
            failed.model_dump(mode="json"), allow_nan=False
        )

        recovered = await execution.dispatch()
        _assert_success(execution, recovered)
        assert call_count == 2 and len(boundary.calls) == 2
        assert boundary.unexpected_calls == []

    elif scenario == "collections_write_serialization":
        serialization_behavior: dict[str, Any] = {
            "value": successful_service_result(execution)
        }

        async def return_current_value(*args, **kwargs):
            return serialization_behavior["value"]

        boundary = install_collections_service_boundary(
            execution, monkeypatch, handler=return_current_value
        )
        successful = await execution.dispatch()
        _assert_success(execution, successful)
        assert len(boundary.calls) == 1 and boundary.unexpected_calls == []

        if key[0] != "delete_collection":
            for unsafe in (object(), float("nan")):
                serialization_behavior["value"] = unsafe
                boundary.calls.clear()
                invalid = await execution.dispatch()
                assert (
                    invalid.status == "failed"
                    and invalid.error_code == "invalid_output"
                )
                assert invalid.retryable is False
                _assert_result_json_safe(invalid)
                assert _ERROR_SENTINEL not in json.dumps(
                    invalid.model_dump(mode="json"), allow_nan=False
                )
                assert len(boundary.calls) == 1
        else:
            assert successful.output["deleted"] is True
            assert type(successful.output["deleted"]) is bool

    elif scenario == "collections_write_authorization":
        boundary = install_collections_service_boundary(execution, monkeypatch)
        public = execution.arguments()
        definition = execution.registry.get_public_definition(*key)
        assert definition is not None
        assert execution.descriptor.requires_auth
        assert execution.descriptor.is_side_effect
        assert execution.descriptor.approval_required
        assert execution.descriptor.idempotency_mode == "required"
        assert execution.descriptor.input_schema["type"] == "object"
        assert execution.descriptor.input_schema["additionalProperties"] is False
        assert "idempotency_key" in execution.descriptor.input_schema["properties"]
        if key[0] == "batch_upsert_collections":
            item_schema = execution.descriptor.input_schema["properties"]["items"][
                "items"
            ]
            assert item_schema["additionalProperties"] is False
        _assert_schema_has_no_runtime_identity(execution.descriptor.input_schema)
        _assert_schema_has_no_runtime_identity(definition.input_schema)
        validate_input({**public, "idempotency_key": uuid4().hex}, execution.descriptor)
        json.dumps(definition.to_dict(), ensure_ascii=False, allow_nan=False)

        anonymous_dispatcher = execution.make_dispatcher(
            authenticated=False, durable=False
        )
        anonymous_context = execution.context.model_copy(
            update={
                "principal_id": None,
                "run_id": uuid4().hex,
                "trace_id": uuid4().hex,
            }
        )
        anonymous = await execution.dispatch(
            dispatcher=anonymous_dispatcher, context=anonymous_context
        )
        _assert_rejected(anonymous, {"unauthorized"})

        root_spoof = {**public, "user_id": execution.user.id + 100}
        with pytest.raises(ValidationError):
            await execution.dispatch(arguments=root_spoof)

        nested_spoof = execution.arguments()
        if key[0] == "batch_upsert_collections":
            nested_spoof["items"][0]["user_id"] = execution.user.id + 100
        elif key[0] == "import_json_collections":
            nested_spoof["data"]["user_id"] = execution.user.id + 100
        elif key[0] == "sync_douban_collections":
            nested_spoof["data"][0]["interest"]["user_id"] = execution.user.id + 100
        else:
            nested_spoof["untrusted_metadata"] = {
                "principal_id": execution.user.id + 100
            }
        with pytest.raises(ValidationError):
            await execution.dispatch(arguments=nested_spoof)

        denied_allowlist = await execution.dispatch(
            context=execution.context.model_copy(
                update={
                    "capability_allowlist": frozenset({"not-collections"}),
                    "run_id": uuid4().hex,
                    "trace_id": uuid4().hex,
                }
            )
        )
        _assert_rejected(denied_allowlist, {"policy_denied"})

        denied_version = await execution.dispatch(version="v999")
        _assert_rejected(
            denied_version,
            {
                "invalid_request",
                "unsupported_version",
                "capability_not_found",
                "not_configured",
            },
        )

        denied_missing_key = await execution.dispatch(include_key=False)
        _assert_rejected(denied_missing_key, {"idempotency_required"})

        disabled_policy = execution.make_dispatcher(allow_side_effects=False)
        denied_disabled = await execution.dispatch(dispatcher=disabled_policy)
        _assert_rejected(denied_disabled, {"policy_denied"})

        no_store = execution.make_dispatcher(durable=False)
        denied_no_store = await execution.dispatch(dispatcher=no_store)
        _assert_rejected(denied_no_store, {"idempotency_required"})
        _assert_no_service_calls(boundary)

    elif scenario == "collections_write_dispatcher":
        boundary = install_collections_service_boundary(execution, monkeypatch)
        valid = execution.arguments()
        invalid = {**valid, "unknown_argument": "rejected"}
        rejected = await execution.dispatch(arguments=invalid)
        _assert_rejected(rejected, {"invalid_request", "invalid_args"})
        assert boundary.calls == [] and boundary.unexpected_calls == []

        succeeded = await execution.dispatch()
        _assert_success(execution, succeeded)
        assert len(boundary.calls) == 1 and boundary.unexpected_calls == []
        assert succeeded.invocation_id
        assert [event.event_type for event in execution.dispatcher.events] == [
            "invocation_start",
            "invocation_end",
        ]
        assert all(
            event.invocation_id == succeeded.invocation_id
            for event in execution.dispatcher.events
        )

    elif scenario == "collections_write_approval":
        boundary = install_collections_service_boundary(execution, monkeypatch)
        missing_approval = execution.make_dispatcher(
            approval=None, use_default_approval=False
        )
        pending = await execution.dispatch(dispatcher=missing_approval)
        _assert_rejected(pending, {"approval_required", "policy_denied"})

        rejected_approval = execution.make_dispatcher(
            approval=Approval(
                approval_id=uuid4().hex,
                approved=False,
                principal_id=execution.user.id,
                action=key[0],
            ),
            use_default_approval=False,
        )
        rejected = await execution.dispatch(dispatcher=rejected_approval)
        _assert_rejected(rejected, {"policy_denied"})

        wrong_principal = execution.make_dispatcher(
            approval=Approval(
                approval_id=uuid4().hex,
                principal_id=execution.user.id + 100,
                action=key[0],
            ),
            use_default_approval=False,
        )
        principal_denied = await execution.dispatch(dispatcher=wrong_principal)
        _assert_rejected(principal_denied, {"policy_denied"})

        wrong_action = execution.make_dispatcher(
            approval=Approval(
                approval_id=uuid4().hex,
                principal_id=execution.user.id,
                action="different_collection_action",
            ),
            use_default_approval=False,
        )
        action_denied = await execution.dispatch(dispatcher=wrong_action)
        _assert_rejected(action_denied, {"policy_denied"})
        _assert_no_service_calls(boundary)

    elif scenario == "collections_write_idempotency":
        boundary = install_collections_service_boundary(execution, monkeypatch)
        stable_key = uuid4().hex
        first = await execution.dispatch(idempotency_key=stable_key)
        _assert_success(execution, first)
        assert len(boundary.calls) == 1

        factory = async_sessionmaker(
            db_session.bind, class_=AsyncSession, expire_on_commit=False
        )
        async with factory() as fresh_session:
            execution.db = fresh_session
            rebuilt_dispatcher = execution.make_dispatcher(db=fresh_session)
            replay = await execution.dispatch(
                idempotency_key=stable_key, dispatcher=rebuilt_dispatcher
            )
            _assert_success(execution, replay)
            assert len(boundary.calls) == 1

            if key[0] != "delete_collection":
                changed_payload = execution.arguments()
                if "rate" in changed_payload:
                    changed_payload["rate"] = 9
                elif "items" in changed_payload:
                    changed_payload["items"][0]["rate"] = 9
                elif "data" in changed_payload and isinstance(
                    changed_payload["data"], dict
                ):
                    changed_payload["data"]["data"][0]["rate"] = 9
                elif "data" in changed_payload and isinstance(
                    changed_payload["data"], list
                ):
                    changed_payload["data"][0]["interest"]["rating"]["value"] = 3.5
                elif "limit" in changed_payload:
                    changed_payload["limit"] = 3
                conflict = await execution.dispatch(
                    arguments=changed_payload,
                    idempotency_key=stable_key,
                    dispatcher=rebuilt_dispatcher,
                )
                assert conflict.status == "denied", conflict.model_dump()
                assert conflict.error_code == "idempotency_conflict"
                assert conflict.retryable is False
                assert len(boundary.calls) == 1
                _assert_result_json_safe(conflict)
        assert boundary.unexpected_calls == []

    else:
        raise AssertionError(f"Unknown scenario: {scenario}")

    record(request, key, scenario)
