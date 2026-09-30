"""Tests for MULTI-AGENT-001 Step 01: routing contracts."""

from __future__ import annotations

import pytest

from app.agents.routing import (
    RouteDecision,
    RouteIntent,
    Handoff,
    MAX_HANDOFFS,
    validate_handoff,
)


class TestRouteDecision:
    def test_unknown_intent(self):
        d = RouteDecision(intent=RouteIntent.UNKNOWN, selected_agent="fallback")
        assert d.intent == RouteIntent.UNKNOWN
        assert d.selected_agent == "fallback"
        assert len(d.handoffs) == 0

    def test_recommendation_intent(self):
        d = RouteDecision(
            intent=RouteIntent.RECOMMENDATION,
            selected_agent="recommendation",
            rationale="keyword match",
        )
        assert d.selected_agent == "recommendation"

    def test_confidence_default(self):
        d = RouteDecision(intent=RouteIntent.UNKNOWN, selected_agent="fallback")
        assert d.confidence == 1.0


class TestHandoffValidation:
    def test_excessive_handoffs_raises(self):
        handoffs = [
            Handoff(from_agent=f"a{i}", to_agent=f"b{i}", rationale="")
            for i in range(MAX_HANDOFFS + 1)
        ]
        d = RouteDecision(
            intent=RouteIntent.UNKNOWN,
            selected_agent="final",
            handoffs=handoffs,
        )
        with pytest.raises(ValueError, match="exceeds limit"):
            validate_handoff(d)

    def test_cycle_detected(self):
        d = RouteDecision(
            intent=RouteIntent.UNKNOWN,
            selected_agent="final",
            handoffs=[
                Handoff(from_agent="a", to_agent="b", rationale="step1"),
                Handoff(from_agent="b", to_agent="a", rationale="step2"),
            ],
        )
        with pytest.raises(ValueError, match="Cycle"):
            validate_handoff(d)

    def test_final_agent_not_in_chain(self):
        d = RouteDecision(
            intent=RouteIntent.UNKNOWN,
            selected_agent="final",
            handoffs=[
                Handoff(from_agent="a", to_agent="b", rationale="step"),
            ],
        )
        # final not in chain — valid
        validate_handoff(d)

    def test_valid_handoff_succeeds(self):
        d = RouteDecision(
            intent=RouteIntent.RECOMMENDATION,
            selected_agent="recommendation",
            handoffs=[
                Handoff(from_agent="router", to_agent="recommendation"),
            ],
        )
        validate_handoff(d)
