"""Shared trusted composition for real Subjects action certification."""

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
    "get_subject": "get_subject_by_source",
    "search_local_subjects": "search_subject_by_name",
    "search_remote_subjects": "search_subject_cloud",
    "search_mixed_subjects": "search_mixed",
    "get_subject_air_time": "get_subject_by_source",
}


def subjects_parameters(scenario: str):
    actions = census()
    registry = build_capability_registry()
    keys = [
        key
        for key in actions
        if (owner := registry.find_action(key[0])) is not None
        and owner[0].name == "subjects"
    ]
    assert {key[0] for key in keys} == set(DEPENDENCIES)
    assert {key for key in keys} <= set(cases())
    return [
        pytest.param(
            key,
            id=f"{key[0]}@{key[1]}-{scenario}",
            marks=pytest.mark.capability_contract(*key, scenario),
        )
        for key in keys
    ]


@dataclass
class SubjectsExecution:
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
) -> SubjectsExecution:
    registry = build_capability_registry()
    owner = registry.find_action(key[0])
    assert owner is not None and owner[0].name == "subjects"
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
    run_id = "subjects-cert-" + uuid4().hex
    context = ExecutionContext(
        principal_id=user.id if authenticated else None,
        run_id=run_id,
        trace_id=run_id,
        capability_allowlist=frozenset({key[0]}),
    )
    return SubjectsExecution(
        key, descriptor, capability, example, env, runtime.dispatcher, context
    )
