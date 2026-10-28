"""Shared trusted composition for real Anime action certification."""

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
from tests.capabilities.contracts.catalog import cases
from tests.capabilities.contracts.model import Environment

DEPENDENCIES = {
    "search_anime_advanced": "search_subjects_advanced",
    "get_anime_info": "fetch_subject_by_id",
    "get_anime_info_batch": "get_bangumi_subject_details",
    "get_anime_staff": "get_staff_info",
    "get_anime_cast": "get_cast_info",
    "fetch_audience_reviews": "get_audience_feedback",
    "get_bangumi_calendar": "get_bangumi_calendar",
    "get_bangumi_user_info": "get_bangumi_user_info",
}


def anime_parameters(scenario, *, required=True):
    registry = build_capability_registry()
    keys = [
        (d.public_name or d.name, d.version) for d in registry.get("anime").actions()
    ]
    assert {key[0] for key in keys} == set(DEPENDENCIES)
    return [
        pytest.param(
            key,
            id=f"{key[0]}@{key[1]}-{scenario}",
            marks=[pytest.mark.capability_contract(*key, scenario)] if required else [],
        )
        for key in keys
    ]


@dataclass
class AnimeExecution:
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
    key, db, monkeypatch, *, authenticated=True, linked_name="contract-bangumi"
):
    registry = build_capability_registry()
    owner = registry.find_action(key[0])
    assert owner is not None and owner[0].name == "anime"
    capability, descriptor = owner
    user = UserRead(
        id=7,
        username="contract-user",
        bangumi_name=linked_name,
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
    run_id = "anime-cert-" + uuid4().hex
    context = ExecutionContext(
        principal_id=user.id if authenticated else None,
        run_id=run_id,
        trace_id=run_id,
        capability_allowlist=frozenset({key[0]}),
    )
    return AnimeExecution(
        key, descriptor, capability, example, env, runtime.dispatcher, context
    )
