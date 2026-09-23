"""Routing contracts — MULTI-AGENT-001 Step 01.

Defines route intent, handoff metadata, and validation for multi-agent
dispatch.  Independent of LangGraph message classes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum

MAX_HANDOFFS = 5


class RouteIntent(StrEnum):
    """Known routing intents the router can handle deterministically."""

    RECOMMENDATION = "recommendation"
    SCHEDULE = "schedule"
    ANIME_KNOWLEDGE = "anime_knowledge"
    COMPANION = "companion"
    UNKNOWN = "unknown"  # fall through to legacy


@dataclass
class Handoff:
    """Metadata for a single agent handoff.

    ``from_agent`` and ``to_agent`` are registry names.
    ``rationale`` is a safe summary (no raw chain-of-thought).
    """

    from_agent: str
    to_agent: str
    rationale: str = ""


@dataclass
class RouteDecision:
    """Result of routing an incoming task.

    The ``selected_agent`` is the registry name of the target agent,
    or ``"fallback"`` when no specialist applies.
    """

    intent: RouteIntent
    selected_agent: str
    confidence: float = 1.0
    rationale: str = ""
    handoffs: list[Handoff] = field(default_factory=list)


def validate_handoff(decision: RouteDecision) -> None:
    """Reject cycles and excessive handoffs.

    Raises ``ValueError`` if the handoff chain exceeds ``MAX_HANDOFFS``
    or contains a cycle.
    """
    if len(decision.handoffs) > MAX_HANDOFFS:
        raise ValueError(
            f"Handoff count {len(decision.handoffs)} exceeds limit {MAX_HANDOFFS}"
        )

    visited: set[str] = set()
    previous_to: str | None = None
    for index, handoff in enumerate(decision.handoffs):
        if index and handoff.from_agent != previous_to:
            raise ValueError("Handoff chain is disconnected")
        if handoff.from_agent in visited and handoff.from_agent != previous_to:
            raise ValueError(f"Cycle detected: agent '{handoff.from_agent}' revisited")
        if handoff.to_agent in visited:
            raise ValueError(f"Cycle detected: agent '{handoff.to_agent}' visited twice")
        visited.add(handoff.from_agent)
        visited.add(handoff.to_agent)
        previous_to = handoff.to_agent

    if decision.selected_agent in visited and decision.selected_agent != previous_to:
        raise ValueError(
            f"Final agent '{decision.selected_agent}' already visited in handoff chain"
        )
