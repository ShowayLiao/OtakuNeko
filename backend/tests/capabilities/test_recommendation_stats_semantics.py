"""Real profile computation and read-only parameter/timeout regressions."""

from __future__ import annotations

import asyncio
from dataclasses import replace
from datetime import datetime
import json
import threading
from unittest.mock import create_autospec
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.capabilities import recommendation as recommendation_module
from app.capabilities.factory import build_capability_registry
from app.capabilities.recommendation import RecommendationCapability
from app.capabilities.stats import StatsCapability
from app.harness.contracts import AgentDecision, ExecutionContext
from app.harness.execution import build_runtime
from app.harness.model_gateway import ModelGateway
from app.harness.normalizer import ResultNormalizer, validate_input, SchemaContractError
from app.schemas.user import UserRead
from app.services import user_profile_service


async def _dispatch(db, monkeypatch, action, *, timeout=0.03):
    registry = build_capability_registry()
    owner = registry.find_action(action)
    assert owner is not None
    capability, descriptor = owner
    descriptors = [
        replace(item, timeout_seconds=timeout) for item in capability.actions()
    ]
    monkeypatch.setattr(capability, "actions", lambda: descriptors)
    registry.unregister(capability.name)
    registry.register(capability)
    runtime = build_runtime(
        session=db,
        user=UserRead(id=7, username="synthetic", created_at=datetime(2026, 1, 1)),
        registry=registry,
        model_gateway=create_autospec(ModelGateway, instance=True),
        trace_store=None,
    )
    run_id = uuid4().hex
    context = ExecutionContext(
        principal_id=7,
        run_id=run_id,
        trace_id=run_id,
        capability_allowlist=frozenset({action}),
    )
    assert runtime.dispatcher is not None
    return await runtime.dispatcher.dispatch(
        AgentDecision(
            decision_id=uuid4().hex,
            run_id=run_id,
            action="invoke",
            capability=action,
            capability_version="v1",
            arguments={},
        ),
        context,
    )


def _profile():
    return {
        "llm_summary": {"total_rated": 2, "taste_dictionary": {"Synthetic": [2, 8]}},
        "chart_data": {"radar": [], "bar_count": [], "bar_score": []},
        "watched_ids": [101],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["generate_profile", "analyse_taste"])
async def test_real_profile_service_error_is_failed_and_safe(
    monkeypatch, action, caplog
):
    def corrupt(*args):
        raise RuntimeError("synthetic-private-profile-diagnostic")

    monkeypatch.setattr(user_profile_service, "_clean_and_extract_data", corrupt)
    logger = user_profile_service.logger
    logger.addHandler(caplog.handler)
    try:
        result = await RecommendationCapability().execute(
            action, collections=[{"rate": 8}]
        )
    finally:
        logger.removeHandler(caplog.handler)
    assert result["success"] is False and result["error_type"] == "internal"
    assert "synthetic-private" not in json.dumps(result)
    assert all(
        "synthetic-private" not in repr(entry.__dict__) for entry in caplog.records
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["recommendation", "stats"])
async def test_capability_exception_text_is_safe(monkeypatch, kind):
    async def fail(*args):
        raise ValueError("synthetic-private-diagnostic")

    if kind == "recommendation":
        monkeypatch.setattr(recommendation_module, "get_user_collections", fail)
        result = await RecommendationCapability().execute(
            "generate_profile", db=object(), user_id=7
        )
    else:
        monkeypatch.setattr("app.capabilities.stats.get_user_stats", fail)
        result = await StatsCapability().execute(
            "get_user_stats", db=object(), user_id=7
        )
    assert result["success"] is False
    assert "synthetic-private" not in json.dumps(result)


@pytest.mark.parametrize("capability", [RecommendationCapability(), StatsCapability()])
def test_only_declared_read_parameters_are_accepted(capability):
    for descriptor in capability.actions():
        assert descriptor.is_side_effect is False
        for arguments in (
            {"save": True},
            {"refresh": True},
            {"sql": "synthetic query"},
        ):
            with pytest.raises(SchemaContractError):
                validate_input(arguments, descriptor)


@pytest.mark.parametrize("capability", [RecommendationCapability(), StatsCapability()])
def test_minimal_success_cannot_bypass_output_contract(capability):
    for descriptor in capability.actions():
        assert descriptor.output_schema.get("required"), descriptor.name
        result = ResultNormalizer().normalize(
            {"success": True},
            descriptor=descriptor,
            run_id="schema",
            decision_id="decision",
            invocation_id="invocation",
            trace_id="schema",
        )
        assert result.status == "failed"


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ["generate_user_profile_tool", "analyse_taste"])
@pytest.mark.parametrize("phase", ["profile", "snapshot"])
async def test_dispatcher_timeout_covers_sync_profile_calculation(
    monkeypatch, db_session, action, phase
):
    started, released, finished = (
        threading.Event(),
        threading.Event(),
        threading.Event(),
    )

    async def collections(*args):
        return SimpleNamespace(items=[{"rate": 8}])

    def compute(*args):
        started.set()
        try:
            assert released.wait(2), "test must release its worker"
            return _profile()
        finally:
            finished.set()

    monkeypatch.setattr(recommendation_module, "get_user_collections", collections)
    if phase == "profile":
        monkeypatch.setattr(recommendation_module, "generate_user_profile", compute)
    else:
        original_copy = recommendation_module.deepcopy

        def snapshot(value):
            compute()
            return original_copy(value)

        monkeypatch.setattr(recommendation_module, "deepcopy", snapshot)
    # Releases even when the old implementation blocks the event loop.
    watchdog = threading.Timer(0.35, released.set)
    watchdog.start()
    beats = 0

    async def heartbeat():
        nonlocal beats
        while True:
            await asyncio.sleep(0.005)
            beats += 1

    heart = asyncio.create_task(heartbeat())
    try:
        result = await _dispatch(db_session, monkeypatch, action)
        assert started.is_set(), json.dumps(result.model_dump(mode="json"))
        assert result.status == "timeout", result.model_dump()
        assert not finished.is_set(), "timeout ends waiting, not a running thread"
        assert beats >= 2, "profile computation must not block the event loop"
    finally:
        released.set()
        watchdog.cancel()
        heart.cancel()
        await asyncio.gather(heart, return_exceptions=True)
        if started.is_set():
            assert await asyncio.to_thread(finished.wait, 2)
        watchdog.join()


@pytest.mark.asyncio
async def test_cancelled_calculations_retain_capacity_until_workers_exit(
    monkeypatch, db_session
):
    started, released = threading.Event(), threading.Event()
    done = [threading.Event(), threading.Event()]
    count = 0
    lock = threading.Lock()

    def compute(*args):
        nonlocal count
        with lock:
            index = count
            count += 1
            if count == 2:
                started.set()
        if index < 2:
            try:
                assert released.wait(3)
            finally:
                done[index].set()
        return _profile()

    async def collections(*args):
        return SimpleNamespace(items=[{"rate": 8}])

    monkeypatch.setattr(recommendation_module, "generate_user_profile", compute)
    monkeypatch.setattr(recommendation_module, "get_user_collections", collections)
    capability = RecommendationCapability()
    first = [
        asyncio.create_task(capability.execute("generate_profile", collections=[{}]))
        for _ in range(2)
    ]
    watchdog = threading.Timer(2, released.set)
    watchdog.start()
    try:
        assert await asyncio.to_thread(started.wait, 1)
        for task in first:
            task.cancel()
        cancelled = await asyncio.gather(*first, return_exceptions=True)
        assert all(isinstance(value, asyncio.CancelledError) for value in cancelled)
        result = await _dispatch(db_session, monkeypatch, "generate_user_profile_tool")
        assert result.status == "timeout"
        assert count == 2, "waiting work must not be queued behind abandoned workers"
        assert not any(event.is_set() for event in done)
    finally:
        released.set()
        for task in first:
            task.cancel()
        await asyncio.gather(*first, return_exceptions=True)
        watchdog.cancel()
        watchdog.join()
        assert all(
            await asyncio.gather(*(asyncio.to_thread(event.wait, 2) for event in done))
        )
    recovered = await _dispatch(
        db_session, monkeypatch, "generate_user_profile_tool", timeout=1
    )
    assert recovered.status == "succeeded"
    assert count == 3


@pytest.mark.asyncio
async def test_late_calculation_failure_is_consumed_without_raw_loop_error(monkeypatch):
    started, released, finished = (
        threading.Event(),
        threading.Event(),
        threading.Event(),
    )
    loop = asyncio.get_running_loop()
    diagnostics = []
    previous = loop.get_exception_handler()

    def fail(*args):
        started.set()
        try:
            assert released.wait(2)
            raise RuntimeError("synthetic-private-late-diagnostic")
        finally:
            finished.set()

    monkeypatch.setattr(recommendation_module, "generate_user_profile", fail)
    loop.set_exception_handler(lambda current, context: diagnostics.append(context))
    task = asyncio.create_task(
        RecommendationCapability().execute("generate_profile", collections=[{}])
    )
    try:
        assert await asyncio.to_thread(started.wait, 1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        released.set()
        assert await asyncio.to_thread(finished.wait, 1)
        for _ in range(3):
            await asyncio.sleep(0)
        assert not diagnostics
    finally:
        released.set()
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
        assert await asyncio.to_thread(finished.wait, 1)
        loop.set_exception_handler(previous)
