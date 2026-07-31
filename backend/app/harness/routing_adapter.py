"""Feature-flagged routing adapter for the Harness boundary."""

from __future__ import annotations

from typing import Any, AsyncIterator

from app.agents.router import AgentRouter
from app.agents.routing import validate_handoff
from app.harness.result import AgentResult
from app.harness.state import AgentState


class FeatureFlagRoutingAdapter:
    """Route supported tasks while preserving the legacy adapter fallback."""

    def __init__(self, fallback: Any, router: AgentRouter, *, enabled: bool) -> None:
        self._fallback = fallback
        self._router = router
        self._enabled = enabled

    async def stream(self, state: AgentState, **kwargs: Any) -> AsyncIterator[dict[str, Any]]:
        if not self._enabled:
            async for chunk in self._fallback.stream(state, **kwargs):
                yield chunk
            return

        messages = kwargs.get("messages") or state.task.metadata.get("messages", [])
        decision = self._router.route(state.task.goal, messages)
        validate_handoff(decision)
        yield {
            "type": "route_decision",
            "route": decision.intent.value,
            "agent": decision.selected_agent,
            "confidence": decision.confidence,
            "rationale": decision.rationale,
        }
        specialist = self._router.select(decision)
        if specialist is None:
            async for chunk in self._fallback.stream(state, **kwargs):
                yield chunk
            return

        result = await specialist.execute(state.task)
        normalized = AgentResult.from_raw(
            result,
            kind="subagent",
            name=decision.selected_agent,
        )
        if state.context.get("orchestrate_results"):
            yield {
                "type": "agent_result",
                "kind": normalized.kind,
                "agent": normalized.name,
                "result": normalized.model_dump(),
            }
            return

        legacy_content = normalized.content or ""
        candidates = normalized.data.get("candidates", [])
        yield {"type": "message_start"}
        yield {
            "type": "message_chunk",
            "content": legacy_content,
        }
        yield {"type": "message_end"}
        yield {
            "type": "agent_complete",
            "agent": decision.selected_agent,
            "candidates": candidates,
            "evidence": normalized.evidence,
        }
