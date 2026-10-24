"""Real Anime handler error, timeout, isolation, and serialization contracts."""

from __future__ import annotations

import asyncio
from dataclasses import replace
import json
import logging
from typing import Any

import pytest

from app.capabilities import anime as anime_module
from app.harness.contracts import InvocationResult
from tests.capabilities.contracts.anime_support import (
    DEPENDENCIES,
    anime_parameters,
    make_execution,
)
from tests.capabilities.contracts.plugin import record
from tests.capabilities.contracts.test_contracts import assert_subset

_ERROR_SENTINEL = "anime-private-diagnostic-sentinel"
_OUTPUT_SENTINEL = "anime-private-output-sentinel"


class _UnsafeValue:
    def __repr__(self) -> str:
        return _OUTPUT_SENTINEL


class _ModelPayload:
    def __init__(self, payload: Any) -> None:
        self.payload = payload

    def model_dump(self, *args: Any, **kwargs: Any) -> Any:
        return self.payload


def _malformed_dependency_result(action: str, kind: str) -> Any:
    if kind == "bad_shape":
        # Each value reaches the real registered handler and either fails its
        # native projection or violates the action's declared output shape.
        return None

    unsafe: Any = _UnsafeValue() if kind == "object" else float("nan")
    if action == "search_anime_advanced":
        rating: dict[str, Any] = {"score": 8.7, "rank": 1}
        item = {
            "id": 501,
            "name": "The Contract Case",
            "name_cn": "",
            "summary": "",
            "rating": rating,
            "type": 2,
            "air_date": "2026-01-01",
            "images": {"unsafe": unsafe} if kind == "object" else {},
            "tags": [],
        }
        if kind == "nan":
            rating["score"] = unsafe
        return {"total": 1, "data": [item]}
    if action == "get_anime_info":
        return _ModelPayload(
            {
                "id": 501,
                "name": "The Contract Case",
                "summary": "Contract summary",
                "unsafe": unsafe,
            }
        )
    if action == "get_anime_info_batch":
        return {
            "details": [
                {
                    "id": 501,
                    "name": "The Contract Case",
                    "summary": "Contract summary",
                    "unsafe": unsafe,
                }
            ],
            "failed_subject_ids": [],
        }
    if action == "get_anime_staff":
        return [
            _ModelPayload(
                {"name": "Example Studio", "role": "Studio", "unsafe": unsafe}
            )
        ]
    if action == "get_anime_cast":
        return [
            _ModelPayload(
                {
                    "character_name": "Aki",
                    "role": "Lead",
                    "cv_names": ["Sample Voice Actor"],
                    "unsafe": unsafe,
                }
            )
        ]
    if action == "fetch_audience_reviews":
        return _ModelPayload(
            {
                "subject_id": 501,
                "comments": [{"content": "A review", "unsafe": unsafe}],
                "reviews": [],
            }
        )
    if action == "get_bangumi_calendar":
        item = {"id": 501, "name": "The Contract Case"}
        item["unsafe"] = unsafe
        return [{"weekday": {"id": 1, "en": "Monday"}, "items": [item]}]
    if action == "get_bangumi_user_info":
        return {"id": 7001, "username": "contract-bangumi", "unsafe": unsafe}
    raise AssertionError(f"Unknown Anime action: {action}")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", anime_parameters("anime_error"))
async def test_anime_error(key, db_session, monkeypatch, caplog, request):
    execution = await make_execution(key, db_session, monkeypatch)
    dependency = DEPENDENCIES[key[0]]
    calls = []

    async def fail_dependency(*args, **kwargs):
        calls.append((args, kwargs))
        raise RuntimeError(_ERROR_SENTINEL)

    monkeypatch.setattr(anime_module, dependency, fail_dependency)
    logger = anime_module.logger
    logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.ERROR, logger=logger.name):
            result = await execution.dispatch()
    finally:
        logger.removeHandler(caplog.handler)

    assert len(calls) == 1
    assert result.status == "failed" and result.error_code == "internal"
    assert result.output["success"] is False
    assert result.output["error_type"] == "internal"
    public_result = json.dumps(result.model_dump(mode="json"), allow_nan=False)
    assert _ERROR_SENTINEL not in public_result

    records = [record for record in caplog.records if record.name == logger.name]
    assert len(records) == 1
    assert records[0].getMessage() == "anime_capability_failed"
    assert records[0].action == execution.descriptor.name
    assert records[0].error_type == "RuntimeError"
    assert _ERROR_SENTINEL not in repr(records[0].__dict__)
    record(request, key, "anime_error")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", anime_parameters("anime_timeout"))
async def test_anime_timeout(key, db_session, monkeypatch, request):
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

    monkeypatch.setattr(anime_module, dependency, block_dependency)
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
    record(request, key, "anime_timeout")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", anime_parameters("anime_isolation"))
async def test_anime_isolation(key, db_session, monkeypatch, request):
    execution = await make_execution(key, db_session, monkeypatch)
    dependency = DEPENDENCIES[key[0]]
    positive_dependency = getattr(anime_module, dependency)
    calls = 0

    async def fail_once_then_return_positive(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise RuntimeError(_ERROR_SENTINEL)
        return await positive_dependency(*args, **kwargs)

    monkeypatch.setattr(anime_module, dependency, fail_once_then_return_positive)

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
    record(request, key, "anime_isolation")


@pytest.mark.asyncio
@pytest.mark.parametrize("key", anime_parameters("anime_serialization"))
async def test_anime_serialization(key, db_session, monkeypatch, request):
    execution = await make_execution(key, db_session, monkeypatch)
    dependency = DEPENDENCIES[key[0]]
    positive = await execution.dispatch()

    assert positive.status == "succeeded", positive.model_dump()
    assert positive.error_code is None and positive.output["success"] is True
    assert execution.env.calls
    assert_subset(execution.example.expected, positive.output)
    encoded = json.dumps(positive.model_dump(mode="json"), allow_nan=False)
    assert InvocationResult.model_validate(json.loads(encoded)) == positive

    for kind in ("object", "nan", "bad_shape"):
        calls = []

        async def malformed_dependency(*args, **kwargs):
            calls.append((args, kwargs))
            return _malformed_dependency_result(key[0], kind)

        monkeypatch.setattr(anime_module, dependency, malformed_dependency)
        result = await execution.dispatch()

        assert len(calls) == 1
        assert result.status == "failed", result.model_dump()
        if kind in {"object", "nan"}:
            assert result.error_code == "invalid_output"
        else:
            assert result.error_code in {"invalid_output", "internal"}
        assert result.output["success"] is False
        serialized = json.dumps(result.model_dump(mode="json"), allow_nan=False)
        assert _OUTPUT_SENTINEL not in serialized
        if kind == "bad_shape":
            assert "NoneType" not in serialized

    record(request, key, "anime_serialization")
