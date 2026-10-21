"""Shared trusted composition for Recommendation and Stats certification."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from unittest.mock import create_autospec
from uuid import uuid4

import pytest

from app.capabilities.factory import build_capability_registry
from app.harness.contracts import AgentDecision, ExecutionContext
from app.harness.execution import build_runtime
from app.harness.model_gateway import ModelGateway
from app.schemas.user import UserRead
from tests.capabilities.contracts.catalog import cases, census
from tests.capabilities.contracts.model import Environment

DEPENDENCIES = {
    "generate_user_profile_tool": "get_user_collections",
    "analyse_taste": "get_user_collections",
    "get_user_stats": "get_user_stats",
    "get_collection_statistics": "get_collection_statistics",
}


def profile_stats_parameters(scenario: str):
    registry = build_capability_registry()
    actions = census(registry)
    owner_name = scenario.split("_", maxsplit=1)[0]
    keys = [
        key
        for key in actions
        if (owner := registry.find_action(key[0])) is not None
        and owner[0].name == owner_name
    ]
    assert owner_name in {"recommendation", "stats"}
    assert {key[0] for key in keys} == {
        name
        for name in DEPENDENCIES
        if (
            "recommendation"
            if name in {"generate_user_profile_tool", "analyse_taste"}
            else "stats"
        )
        == owner_name
    }
    assert set(keys) <= set(cases())
    return [
        pytest.param(
            key,
            id=f"{key[0]}@{key[1]}-{scenario}",
            marks=pytest.mark.capability_contract(*key, scenario),
        )
        for key in keys
    ]


@dataclass
class ProfileStatsExecution:
    key: tuple[str, str]
    descriptor: Any
    capability: Any
    example: Any
    env: Environment
    dispatcher: Any
    context: ExecutionContext

    async def dispatch(
        self, arguments=None, *, context=None, version=None, forged=False
    ):
        current = context or self.context
        values = dict(
            decision_id=uuid4().hex,
            run_id=current.run_id,
            action="invoke",
            capability=self.key[0],
            capability_version=version or self.key[1],
            arguments=deepcopy(self.example.arguments)
            if arguments is None
            else arguments,
        )
        decision = (
            AgentDecision.model_construct(**values)
            if forged
            else AgentDecision(**values)
        )
        return await self.dispatcher.dispatch(decision, current)


async def make_execution(
    key, db, monkeypatch, *, authenticated=True
) -> ProfileStatsExecution:
    registry = build_capability_registry()
    owner = registry.find_action(key[0])
    expected_owner = (
        "recommendation"
        if key[0] in {"generate_user_profile_tool", "analyse_taste"}
        else "stats"
    )
    assert owner is not None and owner[0].name == expected_owner
    capability, descriptor = owner
    user = UserRead(
        id=7,
        username="contract-user",
        bangumi_name="contract-bangumi",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    env = Environment(monkeypatch=monkeypatch, db=db, user=user)
    example = cases()[key]
    await example.prepare(env)
    gateway = create_autospec(ModelGateway, instance=True)
    for name in ("infer", "stream_infer", "synthesize", "synthesize_result"):
        getattr(gateway, name).side_effect = AssertionError(
            "No model calls in action contracts"
        )
    runtime = build_runtime(
        session=db,
        user=user if authenticated else None,
        registry=registry,
        model_gateway=gateway,
        trace_store=None,
        durable=authenticated,
    )
    run_id = "profile-stats-cert-" + uuid4().hex
    context = ExecutionContext(
        principal_id=user.id if authenticated else None,
        run_id=run_id,
        trace_id=run_id,
        capability_allowlist=frozenset({key[0]}),
    )
    return ProfileStatsExecution(
        key, descriptor, capability, example, env, runtime.dispatcher, context
    )
