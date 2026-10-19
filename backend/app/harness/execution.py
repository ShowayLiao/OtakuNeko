"""Shared composition for HTTP and headless primary Decision execution.

Identity and infrastructure are supplied by the trusted caller. Model arguments
never participate in dependency construction.
"""

from __future__ import annotations

from typing import Any
from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.capabilities.registry import CapabilityRegistry
from app.harness.capability_adapter import CapabilityAdapter
from app.harness.dispatcher import Dispatcher
from app.harness.model_gateway import ModelGateway
from app.harness.persistence.event_store import EventStore
from app.harness.persistence.idempotency import SqlIdempotencyStore
from app.harness.persistence.run_store import RunStore
from app.harness.policy import Approval, PolicyEngine
from app.harness.runtime import AgentRuntime
from app.schemas.user import UserRead
from app.trace.store import TraceStore


def capability_adapter_factory(
    *,
    db: AsyncSession,
    user: UserRead | None,
    policy_engine: PolicyEngine,
    approval: Approval | None,
    idempotency_store: Any | None,
) -> Callable[[Any], CapabilityAdapter]:
    def factory(capability: Any) -> CapabilityAdapter:
        name = getattr(capability, "name", "")
        trusted_args: dict[str, Any] = {}
        if name in {"collections", "subjects", "stats", "schedule", "recommendation"}:
            trusted_args["db"] = db
        if user is not None and name in {"collections", "anime"}:
            trusted_args["user"] = user
        return CapabilityAdapter(
            capability,
            policy_engine=policy_engine,
            approval=approval,
            idempotency_store=idempotency_store,
            trusted_args=trusted_args,
        )

    return factory


def build_runtime(
    *,
    session: AsyncSession,
    user: UserRead | None,
    registry: CapabilityRegistry,
    model_gateway: ModelGateway,
    trace_store: TraceStore | None,
    durable: bool = True,
    allow_side_effects: bool = False,
    approval: Approval | None = None,
    **runtime_options: Any,
) -> AgentRuntime:
    """Use one dependency graph, with headless writes disabled by default."""
    if durable and user is None:
        raise ValueError("durable execution requires a trusted user")
    policy = PolicyEngine(allow_side_effects=allow_side_effects)
    idempotency = SqlIdempotencyStore(session) if durable else None
    dispatcher = Dispatcher(
        registry,
        policy_engine=policy,
        approval=approval,
        idempotency_store=idempotency,
        adapter_factory=capability_adapter_factory(
            db=session,
            user=user,
            policy_engine=policy,
            approval=approval,
            idempotency_store=idempotency,
        ),
    )
    return AgentRuntime(
        model_gateway=model_gateway,
        dispatcher=dispatcher,
        trace_store=trace_store,
        run_store=RunStore(session) if durable else None,
        event_store=EventStore(session) if durable else None,
        **runtime_options,
    )
