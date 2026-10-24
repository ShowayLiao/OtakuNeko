"""Trusted Runtime composition for the System capability contract tests."""

from __future__ import annotations

import logging
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterator
from unittest.mock import create_autospec
from uuid import uuid4

import pytest

from app.capabilities.factory import build_capability_registry
from app.harness.budget import CancellationToken, RunBudget
from app.harness.contracts import AgentDecision, ExecutionContext
from app.harness.execution import build_runtime
from app.harness.model_gateway import ModelGateway
from app.models import User
from app.schemas.user import UserRead

FROZEN_ACTIONS = frozenset({"get_current_time"})
SYSTEM_PRIVATE = "system-contract-private-sentinel"


class FixedSystemDateTime(datetime):
    """Shared deterministic clock for the System contract examples."""

    @classmethod
    def now(cls, tz: Any = None) -> "FixedSystemDateTime":
        return cls(2026, 1, 2, 3, 4, 5, tzinfo=tz)


@contextmanager
def capture_application_logs(caplog, level: int = logging.DEBUG) -> Iterator[None]:
    """Propagate app logger records into pytest's caplog for this test."""
    previous: dict[str, tuple[int, bool]] = {}
    for name, logger in list(logging.root.manager.loggerDict.items()):
        if not isinstance(logger, logging.Logger):
            continue
        if name != "app" and not name.startswith("app."):
            continue
        previous[name] = (logger.level, logger.propagate)
        logger.setLevel(level)
        logger.propagate = True
    try:
        with caplog.at_level(level):
            yield
    finally:
        for name, (old_level, old_propagate) in previous.items():
            logger = logging.getLogger(name)
            logger.setLevel(old_level)
            logger.propagate = old_propagate


def system_parameters(scenario: str) -> list[Any]:
    """Build the frozen System inventory from the production Registry."""
    registry = build_capability_registry()
    descriptors = {}
    for descriptor in registry.list_actions():
        public_name = descriptor.public_name or descriptor.name
        owner = registry.find_action(public_name)
        if owner is None or owner[0].name != "system":
            continue
        descriptors[(public_name, owner[1].version)] = owner[1]

    expected = {(name, "v1") for name in FROZEN_ACTIONS}
    assert set(descriptors) == expected
    assert all(not descriptors[key].is_side_effect for key in expected)
    assert all(not descriptors[key].requires_auth for key in expected)

    return [
        pytest.param(
            key,
            id=f"{key[0]}@{key[1]}-{scenario}",
            marks=pytest.mark.capability_contract(*key, scenario),
        )
        for key in sorted(expected)
    ]


@dataclass
class SystemExecution:
    key: tuple[str, str]
    descriptor: Any
    capability: Any
    registry: Any
    dispatcher: Any
    user: UserRead
    other_user: UserRead
    gateway: Any

    def context_for(
        self,
        principal_id: Any = ...,
        *,
        action: str | None = None,
        allowlist: frozenset[str] | None = None,
    ) -> ExecutionContext:
        if principal_id is ...:
            principal_id = self.user.id
        name = action or self.key[0]
        values = {
            "principal_id": principal_id,
            "run_id": "system-contract-run-" + uuid4().hex,
            "trace_id": "system-contract-trace-" + uuid4().hex,
            "capability_allowlist": (
                frozenset({name}) if allowlist is None else allowlist
            ),
        }
        if principal_id is None or type(principal_id) is int:
            return ExecutionContext(**values)
        # Model-construct only hostile trusted-context types that normal request
        # validation would reject before they reach this Dispatcher test.
        return ExecutionContext.model_construct(**values)

    async def dispatch(
        self,
        action: str | None = None,
        arguments: dict[str, Any] | None = None,
        *,
        context: ExecutionContext | None = None,
        version: str | None = None,
        budget: RunBudget | None = None,
        cancellation: CancellationToken | None = None,
        forged_decision: bool = False,
        decision_action: str = "invoke",
        run_id: str | None = None,
    ):
        name = action or self.key[0]
        current = context or self.context_for(action=name)
        values: dict[str, Any] = {
            "decision_id": uuid4().hex,
            "run_id": run_id or current.run_id,
            "action": decision_action,
            "capability": name,
            "capability_version": version or self.key[1],
            "arguments": deepcopy(arguments or {}),
        }
        decision = (
            AgentDecision.model_construct(**values)
            if forged_decision
            else AgentDecision(**values)
        )
        return await self.dispatcher.dispatch(
            decision,
            current,
            budget=budget,
            cancellation=cancellation,
        )


async def make_system_execution(key: tuple[str, str], db: Any) -> SystemExecution:
    """Compose the production Registry, Runtime, Dispatcher, and Adapter."""
    registry = build_capability_registry()
    owner = registry.find_action(key[0])
    assert owner is not None and owner[0].name == "system"
    capability, descriptor = owner
    assert descriptor.version == key[1] and not descriptor.is_side_effect

    suffix = uuid4().hex[:16]
    owner_model = User(username=f"system-contract-owner-{suffix}")
    other_model = User(username=f"system-contract-other-{suffix}")
    db.add_all([owner_model, other_model])
    await db.flush()
    assert owner_model.id is not None and other_model.id is not None
    await db.commit()
    created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    user = UserRead(
        id=owner_model.id,
        username=owner_model.username,
        bangumi_name=owner_model.bangumi_name,
        created_at=created_at,
    )
    other_user = UserRead(
        id=other_model.id,
        username=other_model.username,
        bangumi_name=other_model.bangumi_name,
        created_at=created_at,
    )

    gateway = create_autospec(ModelGateway, instance=True)
    for method in ("infer", "stream_infer", "synthesize", "synthesize_result"):
        getattr(gateway, method).side_effect = AssertionError(
            "System handler contracts must not call a model"
        )
    runtime = build_runtime(
        session=db,
        user=user,
        registry=registry,
        model_gateway=gateway,
        trace_store=None,
        durable=False,
    )
    assert runtime.dispatcher is not None
    return SystemExecution(
        key,
        descriptor,
        capability,
        registry,
        runtime.dispatcher,
        user,
        other_user,
        gateway,
    )


def assert_no_model_calls(execution: SystemExecution) -> None:
    for method in ("infer", "stream_infer", "synthesize", "synthesize_result"):
        assert getattr(execution.gateway, method).call_count == 0
