"""Real positive actions and separately attributed Dispatcher boundary probes."""

from __future__ import annotations

import asyncio
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone
import json
import math
from uuid import uuid4
from unittest.mock import create_autospec

import pytest

from app.capabilities.factory import build_capability_registry
from app.harness.authority import RUNTIME_OWNED_FIELDS
from app.harness.contracts import AgentDecision, ExecutionContext, InvocationResult
from app.harness.execution import build_runtime
from app.harness.normalizer import _schema_error, validate_input
from app.harness.model_gateway import ModelGateway
from app.harness.policy import Approval
from app.schemas.user import UserRead
from tests.capabilities.contracts.catalog import (
    SCENARIOS,
    cases,
    census,
    fingerprint,
    fixture_errors,
    path_label,
    required_paths,
)
from tests.capabilities.contracts.model import Environment
from tests.capabilities.contracts.plugin import record


def parameters():
    actions, examples = census(), cases()
    errors = fixture_errors(actions, examples)
    if errors:
        raise ValueError("; ".join(errors))
    result = []
    for key, descriptor in actions.items():
        scenarios = list(SCENARIOS)
        scenarios.extend(
            "required:" + path_label(path)
            for path in required_paths(descriptor.input_schema, examples[key].arguments)
        )
        for scenario in scenarios:
            result.append(
                pytest.param(
                    key,
                    scenario,
                    id=f"{key[0]}@{key[1]}-{scenario}",
                    marks=pytest.mark.capability_contract(*key, scenario),
                )
            )
    return result


def assert_subset(expected, actual):
    if isinstance(expected, dict):
        assert isinstance(actual, dict)
        for key, value in expected.items():
            assert key in actual, key
            assert_subset(value, actual[key])
    elif isinstance(expected, list):
        assert isinstance(actual, list) and len(actual) == len(expected)
        for value, result in zip(expected, actual):
            assert_subset(value, result)
    else:
        assert actual == expected


def assert_schema(schema):
    assert isinstance(schema, dict)
    properties = schema.get("properties", {})
    assert isinstance(properties, dict)
    required = schema.get("required", [])
    assert isinstance(required, list) and len(required) == len(set(required))
    # JSON Schema permits required-but-untyped keys when additional properties
    # are allowed. Do not invent a stricter schema dialect for the tests.
    if schema.get("additionalProperties") is False:
        assert set(required) <= set(properties)
    for child in properties.values():
        assert_schema(child)
    if isinstance(schema.get("items"), dict):
        assert_schema(schema["items"])


def assert_public_identity_absent(schema):
    if isinstance(schema, dict):
        assert not (set(schema.get("properties", {})) & RUNTIME_OWNED_FIELDS)
        assert not (set(schema.get("required", [])) & RUNTIME_OWNED_FIELDS)
        for value in schema.values():
            assert_public_identity_absent(value)
    elif isinstance(schema, list):
        for value in schema:
            assert_public_identity_absent(value)


@pytest.mark.asyncio
@pytest.mark.parametrize("key,scenario", parameters())
async def test_action_contract(key, scenario, db_session, monkeypatch, request):
    registry = build_capability_registry()
    descriptor = census(registry)[key]
    example = cases()[key]
    if scenario == "schema":
        from tests.capabilities.contracts.snapshots import FINGERPRINTS

        assert fingerprint(descriptor) == FINGERPRINTS[key], (
            f"Reviewed contract changed: {key}"
        )
        definition = registry.get_public_definition(*key)
        assert definition is not None
        assert_schema(definition.input_schema)
        assert_schema(definition.output_schema)
        assert_public_identity_absent(definition.input_schema)
        assert (
            math.isfinite(descriptor.timeout_seconds) and descriptor.timeout_seconds > 0
        )
        assert descriptor.max_payload_bytes > 0
        assert descriptor.retry_class in {"none", "transient"}
        assert not descriptor.is_side_effect or (
            descriptor.requires_auth
            and descriptor.approval_required
            and descriptor.idempotency_mode == "required"
        )
        validate_input(example.arguments, descriptor)
        json.loads(json.dumps(definition.to_dict(), allow_nan=False))
        record(request, key, scenario)
        return

    user = UserRead(
        id=7,
        username="contract-user",
        bangumi_name="contract-bangumi",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    env = Environment(monkeypatch=monkeypatch, db=db_session, user=user)
    await example.prepare(env)
    owner = registry.find_action(key[0])
    assert owner is not None
    capability, _ = owner
    original_execute = capability.execute
    entered = []
    cleaned = asyncio.Event()
    started = asyncio.Event()

    async def execute(action, **kwargs):
        entered.append(action)
        assert action == descriptor.name
        if descriptor.requires_auth:
            assert kwargs["user_id"] == user.id
        if capability.name in {
            "collections",
            "schedule",
            "stats",
            "subjects",
            "recommendation",
        }:
            assert kwargs["db"] is db_session
        if scenario == "timeout":
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()
        if scenario == "isolation" and len(entered) == 1:
            raise RuntimeError("contract-private-error-sentinel")
        if scenario == "error":
            return {
                "success": False,
                "error_type": "transient",
                "retryable": True,
                "error": "contract-private-error-sentinel",
                **deepcopy(example.expected),
            }
        return await original_execute(action, **kwargs)

    monkeypatch.setattr(capability, "execute", execute)
    if scenario == "timeout":
        descriptors = [
            replace(d, timeout_seconds=0.02) if d.name == descriptor.name else d
            for d in capability.actions()
        ]
        monkeypatch.setattr(capability, "actions", lambda: descriptors)
        registry.unregister(capability.name)
        registry.register(capability)

    gateway = create_autospec(ModelGateway, instance=True)
    for method in ("infer", "stream_infer", "synthesize", "synthesize_result"):
        getattr(gateway, method).side_effect = AssertionError(
            "Contract tests must not call a model"
        )

    runtime = build_runtime(
        session=db_session,
        user=user,
        registry=registry,
        model_gateway=gateway,
        trace_store=None,
        allow_side_effects=True,
        approval=Approval(
            approval_id="contract-approval",
            principal_id=user.id,
            action=descriptor.name,
        ),
    )
    dispatcher = runtime.dispatcher
    assert dispatcher is not None
    if scenario == "timeout":
        # Arm the real deadline only once the injected blocker is active. SQL
        # admission latency is not what this deterministic timeout probe measures.
        controls = dispatcher._run_with_controls

        async def armed_controls(operation, timeout_seconds, cancellation):
            task = asyncio.create_task(operation)
            try:
                await asyncio.wait_for(started.wait(), timeout=5)
                return await controls(task, timeout_seconds, cancellation)
            finally:
                if not task.done():
                    task.cancel()
                await asyncio.gather(task, return_exceptions=True)

        monkeypatch.setattr(dispatcher, "_run_with_controls", armed_controls)
    run_id = "contract-" + uuid4().hex
    context = ExecutionContext(
        principal_id=user.id,
        run_id=run_id,
        trace_id=run_id,
        capability_allowlist=frozenset({key[0]}),
    )
    arguments = deepcopy(example.arguments)
    if descriptor.is_side_effect:
        arguments["idempotency_key"] = uuid4().hex

    async def dispatch(args=None):
        return await dispatcher.dispatch(
            AgentDecision(
                decision_id=uuid4().hex,
                run_id=run_id,
                action="invoke",
                capability=key[0],
                capability_version=key[1],
                arguments=arguments if args is None else args,
            ),
            context,
        )

    if scenario.startswith("required:"):
        path = next(
            path
            for path in required_paths(descriptor.input_schema, example.arguments)
            if "required:" + path_label(path) == scenario
        )
        invalid = deepcopy(arguments)
        parent = invalid
        for part in path[:-1]:
            parent = parent[part]
        del parent[path[-1]]
        result = await dispatch(invalid)
        assert result.status == "denied" and result.error_code == "invalid_request"
        assert not entered and not env.calls
    elif scenario in {"success", "serialization"}:
        result = await dispatch()
        assert result.status == "succeeded", result.model_dump()
        assert result.error_code is None and result.output["success"] is True
        assert entered == [descriptor.name]
        assert env.calls, f"Dependency example was not exercised for {key}"
        assert example.expected, f"Business assertion missing for {key}"
        assert_subset(example.expected, result.output)
        assert (
            _schema_error(
                result.model_output["safe_output"], descriptor.output_schema, "output"
            )
            is None
        )
        if descriptor.is_side_effect:
            count = len(env.calls)
            replay = await dispatch()
            assert replay.status == "succeeded"
            assert entered == [descriptor.name] and len(env.calls) == count
        if scenario == "serialization":
            encoded = json.dumps(result.model_dump(mode="json"), allow_nan=False)
            assert InvocationResult.model_validate(json.loads(encoded)) == result
            factory = dispatcher.adapter_factory
            assert factory is not None
            for value in (object(), float("nan")):
                # A normalizer boundary probe, separate from real SQL write
                # serialization. The positive invocation above uses both.
                def unsafe_factory(capability):
                    adapter = factory(capability)

                    async def unsafe_output(*args, **kwargs):
                        return {"success": True, "invalid": value}

                    monkeypatch.setattr(adapter, "execute", unsafe_output)
                    return adapter

                monkeypatch.setattr(dispatcher, "adapter_factory", unsafe_factory)
                invalid = await dispatch()
                assert (
                    invalid.status == "failed"
                    and invalid.error_code == "invalid_output"
                )
                json.dumps(invalid.model_dump(mode="json"), allow_nan=False)
    elif scenario == "error":
        result = await dispatch()
        assert result.status == "failed" and result.error_code == "transient"
        assert result.retryable is (
            not descriptor.is_side_effect and descriptor.retry_class == "transient"
        )
        assert "contract-private-error-sentinel" not in json.dumps(result.model_dump())
    elif scenario == "timeout":
        result = await dispatch()
        assert result.status == "timeout" and result.error_code == "timeout"
        assert cleaned.is_set() and len(entered) == 1
        assert not result.retryable or not descriptor.is_side_effect
    elif scenario == "isolation":
        result = await dispatch()
        assert result.status == "failed" and result.error_code in {
            "internal",
            "attention_required",
        }
        assert not result.retryable
        assert "contract-private-error-sentinel" not in json.dumps(result.model_dump())
        if descriptor.is_side_effect:
            arguments["idempotency_key"] = uuid4().hex
        recovered = await dispatch()
        assert recovered.status == "succeeded", recovered.model_dump()
        assert_subset(example.expected, recovered.output)
    else:
        raise AssertionError(f"Unknown scenario: {scenario}")
    record(request, key, scenario)
