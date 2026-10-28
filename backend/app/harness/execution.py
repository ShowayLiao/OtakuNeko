"""Shared composition for HTTP and headless primary Decision execution.

Identity and infrastructure are supplied by the trusted caller. Model arguments
never participate in dependency construction.
"""

from __future__ import annotations

from typing import Any
from collections.abc import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.agent_registry import AgentRegistry
from app.agents.recommendation_agent import RecommendationAgent
from app.agents.router import AgentRouter
from app.capabilities.registry import CapabilityRegistry
from app.harness.capability_adapter import CapabilityAdapter
from app.harness.dispatcher import Dispatcher
from app.harness.model_gateway import ModelGateway
from app.harness.persistence.event_store import EventStore
from app.harness.persistence.idempotency import SqlIdempotencyStore
from app.harness.persistence.run_store import RunStore
from app.harness.policy import Approval, PolicyEngine
from app.harness.runtime import AgentRuntime
from app.harness.recovery import RecoveryPolicy
from app.schemas.user import UserRead
from app.trace.store import TraceStore


def build_specialist_router(
    registry: CapabilityRegistry,
    memory_service: Any | None,
    enabled: bool,
    version: str = "keyword-v1",
) -> AgentRouter | None:
    """Build the configured specialist implementation from the shared registry."""
    if not enabled:
        return None
    if version not in {"keyword-v1", "model-v1"}:
        raise ValueError(f"unsupported specialist router version: {version}")

    recommendation_owner = registry.find_action("generate_user_profile_tool")
    anime_owner = registry.find_action("search_anime_advanced")
    if recommendation_owner is None or anime_owner is None:
        return None

    agent_registry = AgentRegistry()
    agent_registry.register(
        "recommendation",
        RecommendationAgent(
            recommendation_owner[0],
            anime_capability=anime_owner[0],
            memory_service=memory_service,
        ),
    )
    return AgentRouter(agent_registry, version=version)


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
    recovery_policy: RecoveryPolicy = RecoveryPolicy(read_only_errors=True),
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
        recovery_policy=recovery_policy,
        model_gateway=model_gateway,
        dispatcher=dispatcher,
        trace_store=trace_store,
        run_store=RunStore(session) if durable else None,
        event_store=EventStore(session) if durable else None,
        **runtime_options,
    )
