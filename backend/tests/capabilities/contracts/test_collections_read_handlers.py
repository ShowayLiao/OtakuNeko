"""Real Collections read handler error, timeout, isolation, and output contracts."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime, timezone
import json
import logging

import pytest
from pydantic import ValidationError

from app.capabilities import collections as collections_module
from app.harness.authority import RUNTIME_OWNED_FIELDS
from app.harness.contracts import InvocationResult
from app.models import CollectionStatus, SubjectType
from app.schemas.adaptersV2 import UnifiedCollectionSubject, UnifiedList
from app.schemas.collection import CollectionRead
from app.schemas.subject import SubjectRead
from tests.capabilities.contracts.collections_read_support import (
    DEPENDENCIES,
    FOREIGN_COMMENT,
    OWNER_COMMENT,
    assert_trusted_dependency_call,
    collections_parameters,
    make_execution,
)
from tests.capabilities.contracts.plugin import record

_ERROR_SENTINEL = "collections-read-private-diagnostic-sentinel"
_OUTPUT_SENTINEL = "collections-read-private-output-sentinel"
_MODEL_TIME = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)


class _UnsafeValue:
    def __repr__(self) -> str:
        return _OUTPUT_SENTINEL


def _unified_collection(execution) -> UnifiedCollectionSubject:
    return UnifiedCollectionSubject(
        collection=CollectionRead(
            type=CollectionStatus.DO,
            source="bangumi",
            source_id=execution.env.shared_source_id,
            user_id=execution.env.user.id,
            rate=8,
            comment=OWNER_COMMENT,
            tags=[],
            private=True,
            updated_at=_MODEL_TIME,
        ),
        subject=SubjectRead(
            id=901,
            name="Shared Synthetic Anime",
            name_cn="合成动画",
            type=SubjectType.ANIME,
            source="bangumi",
            source_id=execution.env.shared_source_id,
            summary="Synthetic contract subject",
            air_time=_MODEL_TIME,
            air_weekday=2,
        ),
    )


def _read_result(action: str, item: UnifiedCollectionSubject):
    if action == "get_collection":
        return item
    return UnifiedList(total=1, items=[item])


def _assert_owned_success(execution, result) -> None:
    assert result.status == "succeeded", result.model_dump()
    assert result.error_code is None
    assert result.output["success"] is True
    if execution.key[0] == "get_collection":
        entries = [result.output["collection"]]
    else:
        assert type(result.output["total"]) is int
        entries = result.output["collections"]
    source_ids = {entry["collection"]["source_id"] for entry in entries}
    if execution.key[0] == "get_collection":
        assert source_ids == {execution.env.shared_source_id}
    else:
        assert source_ids == {
            execution.env.shared_source_id,
            execution.env.owner_only_source_id,
        }
    encoded = json.dumps(result.model_dump(mode="json"), allow_nan=False)
    assert OWNER_COMMENT in encoded
    assert FOREIGN_COMMENT not in encoded
    assert execution.env.foreign_only_source_id not in encoded
    assert '"user_id"' not in encoded


@pytest.mark.asyncio
@pytest.mark.parametrize("key", collections_parameters("collections_read_error"))
async def test_collections_read_errors_are_safe(
    key, db_session, monkeypatch, caplog, request
):
    execution = await make_execution(key, db_session, monkeypatch)
    dependency = DEPENDENCIES[key[0]]
    calls = []

    async def fail_value_error(*args, **kwargs):
        assert_trusted_dependency_call(execution, args, kwargs)
        calls.append((args, kwargs))
        raise ValueError(_ERROR_SENTINEL)

    monkeypatch.setattr(collections_module, dependency, fail_value_error)
    invalid = await execution.dispatch()

    assert len(calls) == 1
    assert invalid.status == "failed" and invalid.error_code == "invalid_args"
    invalid_json = json.dumps(invalid.model_dump(mode="json"), allow_nan=False)
    assert "Capability execution failed" in invalid_json
    assert _ERROR_SENTINEL not in invalid_json

    calls.clear()

    async def fail_runtime_error(*args, **kwargs):
        assert_trusted_dependency_call(execution, args, kwargs)
        calls.append((args, kwargs))
        raise RuntimeError(_ERROR_SENTINEL)

    monkeypatch.setattr(collections_module, dependency, fail_runtime_error)
    logger = collections_module.logger
    logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.ERROR, logger=logger.name):
            internal = await execution.dispatch()
    finally:
        logger.removeHandler(caplog.handler)

    assert len(calls) == 1
    assert internal.status == "failed" and internal.error_code == "internal"
    internal_json = json.dumps(internal.model_dump(mode="json"), allow_nan=False)
    assert "Capability execution failed" in internal_json
    assert _ERROR_SENTINEL not in internal_json
    records = [item for item in caplog.records if item.name == logger.name]
    assert len(records) == 1
    assert records[0].getMessage() == "collection_capability_failed"
    assert records[0].action == execution.descriptor.name
    assert records[0].error_type == "RuntimeError"
    assert records[0].exc_info is None
    assert _ERROR_SENTINEL not in repr(records[0].__dict__)
    record(request, key, "collections_read_error")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", collections_parameters("collections_read_timeout"))
async def test_collections_read_io_timeout_cleans_up(
    key, db_session, monkeypatch, request
):
    execution = await make_execution(key, db_session, monkeypatch)
    dependency = DEPENDENCIES[key[0]]
    entered = asyncio.Event()
    cleaned = asyncio.Event()

    async def block_dependency(*args, **kwargs):
        assert_trusted_dependency_call(execution, args, kwargs)
        entered.set()
        try:
            await asyncio.Event().wait()
        finally:
            cleaned.set()

    monkeypatch.setattr(collections_module, dependency, block_dependency)
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
        result = await dispatch_task
    finally:
        if not dispatch_task.done():
            dispatch_task.cancel()
        await asyncio.gather(dispatch_task, return_exceptions=True)

    assert entered.is_set() and cleaned.is_set()
    assert result.status == "timeout" and result.error_code == "timeout"
    events = execution.dispatcher.events
    assert [event.event_type for event in events] == [
        "invocation_start",
        "invocation_end",
    ]
    assert events[0].invocation_id == events[1].invocation_id == result.invocation_id
    assert events[1].payload["status"] == "timeout"
    record(request, key, "collections_read_timeout")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", collections_parameters("collections_read_isolation"))
async def test_collections_read_recovers_and_keeps_user_scope(
    key, db_session, monkeypatch, request
):
    execution = await make_execution(key, db_session, monkeypatch)
    dependency = DEPENDENCIES[key[0]]
    read_dependency = getattr(collections_module, dependency)
    calls = 0

    async def fail_once_then_read(*args, **kwargs):
        nonlocal calls
        assert_trusted_dependency_call(execution, args, kwargs)
        calls += 1
        if calls == 1:
            raise RuntimeError(_ERROR_SENTINEL)
        return await read_dependency(*args, **kwargs)

    monkeypatch.setattr(collections_module, dependency, fail_once_then_read)
    failed = await execution.dispatch()
    recovered = await execution.dispatch()

    assert calls == 2
    assert failed.status == "failed" and failed.error_code == "internal"
    assert _ERROR_SENTINEL not in json.dumps(
        failed.model_dump(mode="json"), allow_nan=False
    )
    _assert_owned_success(execution, recovered)

    if key[0] == "get_collection":
        foreign_result = await execution.dispatch(
            {
                "source": "bangumi",
                "source_id": execution.env.foreign_only_source_id,
            }
        )
        assert foreign_result.status == "failed"
        assert foreign_result.error_code == "not_found"
        assert FOREIGN_COMMENT not in json.dumps(
            foreign_result.model_dump(mode="json"), allow_nan=False
        )
        assert calls == 3
    record(request, key, "collections_read_isolation")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "key", collections_parameters("collections_read_serialization")
)
async def test_collections_read_serializes_unified_models_safely(
    key, db_session, monkeypatch, request
):
    execution = await make_execution(key, db_session, monkeypatch)
    dependency = DEPENDENCIES[key[0]]
    unified = _unified_collection(execution)

    async def return_unified(db, search, **kwargs):
        assert_trusted_dependency_call(execution, (db, search), kwargs)
        return _read_result(key[0], unified)

    monkeypatch.setattr(collections_module, dependency, return_unified)
    result = await execution.dispatch()

    assert result.status == "succeeded", result.model_dump()
    assert result.error_code is None and result.output["success"] is True
    encoded = json.dumps(result.model_dump(mode="json"), allow_nan=False)
    assert "2026-10-20T12:00:00" in encoded
    assert '"user_id"' not in encoded
    assert InvocationResult.model_validate(json.loads(encoded)) == result

    for kind in ("object", "nan", "bad_shape"):
        raw = unified.model_dump(mode="json")
        if kind == "object":
            raw["collection"]["comment"] = _UnsafeValue()
        elif kind == "nan":
            raw["collection"]["type"] = float("nan")
        else:
            raw.pop("subject")

        async def return_malformed(db, search, *, malformed=raw, **kwargs):
            assert_trusted_dependency_call(execution, (db, search), kwargs)
            if key[0] == "get_collection":
                return malformed
            return {"total": 1, "items": [malformed]}

        monkeypatch.setattr(collections_module, dependency, return_malformed)
        rejected = await execution.dispatch()

        assert rejected.status == "failed", rejected.model_dump()
        assert rejected.error_code == "invalid_output"
        rejected_json = json.dumps(rejected.model_dump(mode="json"), allow_nan=False)
        assert _OUTPUT_SENTINEL not in rejected_json
    record(request, key, "collections_read_serialization")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "key", collections_parameters("collections_read_authorization")
)
async def test_collections_read_authorization_precedes_dependency(
    key, db_session, monkeypatch, request
):
    anonymous = await make_execution(key, db_session, monkeypatch, authenticated=False)
    dependency = DEPENDENCIES[key[0]]
    calls = []

    async def unexpected_dependency(*args, **kwargs):
        calls.append((args, kwargs))
        raise AssertionError("Unauthorized Collections read reached its dependency")

    monkeypatch.setattr(collections_module, dependency, unexpected_dependency)
    anonymous_result = await anonymous.dispatch()
    assert anonymous_result.status == "denied"
    assert anonymous_result.error_code == "unauthorized"
    assert not calls

    execution = await make_execution(key, db_session, monkeypatch)
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

    invalid = await execution.dispatch({**execution.arguments(), "save": True})
    assert invalid.status == "denied" and invalid.error_code == "invalid_request"
    assert not calls

    wrong_version = await execution.dispatch(version="v999")
    assert (
        wrong_version.status == "denied"
        and wrong_version.error_code == "not_configured"
    )
    denied_allowlist = await execution.dispatch(
        context=execution.context.model_copy(
            update={"capability_allowlist": frozenset({"unrelated.action"})}
        )
    )
    assert denied_allowlist.status == "denied"
    assert denied_allowlist.error_code == "policy_denied"
    assert not calls and not execution.dispatcher.events
    record(request, key, "collections_read_authorization")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", collections_parameters("collections_read_dispatcher"))
async def test_collections_read_dispatcher_contract_and_event_correlation(
    key, db_session, monkeypatch, request
):
    execution = await make_execution(key, db_session, monkeypatch)
    dependency = DEPENDENCIES[key[0]]
    read_dependency = getattr(collections_module, dependency)
    calls = []

    async def track_dependency(*args, **kwargs):
        assert_trusted_dependency_call(execution, args, kwargs)
        calls.append((args, kwargs))
        return await read_dependency(*args, **kwargs)

    monkeypatch.setattr(collections_module, dependency, track_dependency)

    assert execution.descriptor.version == "v1"
    assert execution.descriptor.requires_auth is True
    assert execution.descriptor.is_side_effect is False
    input_schema = execution.descriptor.input_schema
    assert input_schema["type"] == "object"
    assert input_schema["additionalProperties"] is False
    properties = input_schema["properties"]
    if key[0] in {"list_collections", "search_collections"}:
        assert properties["type"]["enum"] == [1, 2, 3, 4, 6]
        assert properties["sort_by"]["enum"] == [
            "updated_at",
            "rate",
            "score",
            "date",
        ]
    else:
        assert set(input_schema["required"]) == {"source", "source_id"}
        assert properties["source"]["enum"] == ["bangumi", "douban"]

    output_schema = execution.descriptor.output_schema
    assert output_schema != {"type": "object", "additionalProperties": True}
    assert output_schema["type"] == "object"
    output_properties = output_schema["properties"]
    if key[0] == "get_collection":
        assert output_schema["required"] == ["collection"]
        unified_schema = output_properties["collection"]
    else:
        assert output_schema["required"] == ["total", "collections"]
        assert set(output_properties) == {"total", "collections"}
        assert output_properties["total"]["type"] == "integer"
        assert output_properties["total"]["minimum"] == 0
        assert output_properties["collections"]["type"] == "array"
        unified_schema = output_properties["collections"]["items"]
    assert set(unified_schema["required"]) == {"collection", "subject"}
    assert set(unified_schema["properties"]) == {"collection", "subject"}
    collection_schema = unified_schema["properties"]["collection"]
    assert set(collection_schema["required"]) == {"source", "source_id", "type"}
    subject_schema = unified_schema["properties"]["subject"]
    subject_object = next(
        branch for branch in subject_schema["anyOf"] if branch.get("type") == "object"
    )
    assert set(subject_object["required"]) == {
        "id",
        "name",
        "source",
        "source_id",
    }

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

    for name, schema in properties.items():
        if schema.get("type") not in {"array", "integer", "string"}:
            continue
        invalid_arguments = execution.arguments()
        invalid_arguments[name] = {"wrong": "type"}
        invalid = await execution.dispatch(invalid_arguments)
        assert invalid.status == "denied"
        assert invalid.error_code == "invalid_request"
        assert not calls and not execution.dispatcher.events

    if key[0] in {"list_collections", "search_collections"}:
        for name, value in (("type", 99), ("sort_by", "arbitrary-sql")):
            invalid_arguments = execution.arguments()
            invalid_arguments[name] = value
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
    assert (
        result.run_id == execution.context.run_id
        and result.trace_id == execution.context.trace_id
    )
    assert result.capability == key[0] and result.capability_version == key[1]
    record(request, key, "collections_read_dispatcher")
