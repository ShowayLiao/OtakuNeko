"""AgentRouter — deterministic multi-agent dispatch.

Known intents route without a model call.  An optional LLM classifier
may handle ambiguous queries, but timeout, invalid output, or low
confidence falls back to the legacy adapter.  No side effects are
executed in routing.
"""

from __future__ import annotations

import json
import math
import re
import queue
import threading
from typing import Any

from app.agents.agent_registry import AgentRegistry
from app.agents.base import BaseAgent
from app.agents.routing import RouteDecision, RouteIntent
from app.core.logging import get_logger

logger = get_logger(__name__)

_FALLBACK_AGENT = "fallback"

# Deterministic intent patterns (keyword-based, no LLM).
_RECOMMENDATION_PATTERNS: list[re.Pattern] = [
    re.compile(r"(推荐|有什么.*好看|求推荐|推荐.*番)", re.IGNORECASE),
    re.compile(r"(推荐|荐番|找番|追番.*推荐)", re.IGNORECASE),
]


class AgentRouter:
    """Deterministic router with optional LLM fallback.

    Usage::

        router = AgentRouter(registry)
        decision = router.route(task_goal, messages)
        agent = router.select(decision)

    ``select`` is discovery only.  Execution belongs to the Runtime and its
    Dispatcher; callers must not invoke the returned specialist directly.
    """

    def __init__(
        self,
        registry: AgentRegistry,
        classifier: Any | None = None,
        classifier_timeout_seconds: float = 0.5,
        version: str = "keyword-v1",
    ) -> None:
        if version not in {"keyword-v1", "model-v1"}:
            raise ValueError(f"unsupported specialist router version: {version}")
        self._registry = registry
        self._classifier = classifier  # optional LLM-based classifier
        self._classifier_timeout_seconds = classifier_timeout_seconds
        self._classifier_lock = threading.Lock()
        self._classifier_inflight = False
        self.version = version

    @property
    def candidate_agent_names(self) -> list[str]:
        """Return the registered route choices plus the safe fallback name."""
        return [*sorted(self._registry.list_agents()), _FALLBACK_AGENT]

    def route(
        self, goal: str, messages: list[dict[str, Any]] | None = None
    ) -> RouteDecision:
        """Produce a routing decision without executing any side effects.

        Tries deterministic patterns first.  Falls back to classifier
        when no pattern matches.
        """
        if self.version == "model-v1":
            return RouteDecision(
                intent=RouteIntent.UNKNOWN,
                selected_agent=_FALLBACK_AGENT,
                confidence=0.0,
                rationale="model_route_required",
            )

        # 1. Deterministic patterns
        decision = self._deterministic_route(goal)
        if decision.intent != RouteIntent.UNKNOWN:
            return decision

        # 2. Optional classifier
        if self._classifier is not None:
            try:
                classified = self._classify_with_timeout(goal, messages or [])
                if classified is None:
                    raise ValueError("classifier returned no decision")
                if classified.confidence >= 0.5 and self._registry_has(
                    classified.selected_agent
                ):
                    return classified
            except Exception:
                logger.warning("router_classifier_failed", exc_info=True)
                pass

        return RouteDecision(
            intent=RouteIntent.UNKNOWN,
            selected_agent=_FALLBACK_AGENT,
            confidence=0.0,
            rationale="No deterministic or confident route found",
        )

    def route_from_model_output(self, output: str) -> tuple[RouteDecision, str]:
        """Validate a data-only model route and fall back on invalid/weak output."""
        try:
            payload = json.loads(output)
        except (TypeError, json.JSONDecodeError):
            return self._model_fallback(
                "model_classifier_invalid_output"
            ), "invalid_output"

        if not isinstance(payload, dict) or set(payload) != {
            "selected_agent",
            "confidence",
        }:
            return self._model_fallback(
                "model_classifier_invalid_output"
            ), "invalid_output"

        selected_agent = payload.get("selected_agent")
        confidence = payload.get("confidence")
        if (
            not isinstance(selected_agent, str)
            or selected_agent not in self.candidate_agent_names
            or isinstance(confidence, bool)
            or not isinstance(confidence, (int, float))
            or not math.isfinite(float(confidence))
            or not 0.0 <= float(confidence) <= 1.0
        ):
            return self._model_fallback(
                "model_classifier_invalid_output"
            ), "invalid_output"

        confidence_value = float(confidence)
        if selected_agent == _FALLBACK_AGENT:
            return (
                RouteDecision(
                    intent=RouteIntent.UNKNOWN,
                    selected_agent=_FALLBACK_AGENT,
                    confidence=confidence_value,
                    rationale="model_classifier_selected_fallback",
                ),
                "selected",
            )
        if confidence_value < 0.5:
            return self._model_fallback("model_classifier_low_confidence"), "abstained"

        try:
            intent = RouteIntent(selected_agent)
        except ValueError:
            intent = RouteIntent.UNKNOWN
        return (
            RouteDecision(
                intent=intent,
                selected_agent=selected_agent,
                confidence=confidence_value,
                rationale="model_classifier_selected_agent",
            ),
            "selected",
        )

    def route_provider_failure(
        self, status: str = "provider_error"
    ) -> tuple[RouteDecision, str]:
        """Return a safe route with a bounded terminal classifier status."""
        reasons = {
            "provider_error": "model_classifier_provider_error",
            "timeout": "model_classifier_timeout",
            "cancelled": "model_classifier_cancelled",
            "gateway_unavailable": "model_classifier_gateway_unavailable",
        }
        if status not in reasons:
            raise ValueError(f"unsupported model router terminal status: {status}")
        return self._model_fallback(reasons[status]), status

    def _classify_with_timeout(
        self, goal: str, messages: list[dict[str, Any]]
    ) -> RouteDecision | None:
        with self._classifier_lock:
            if self._classifier_inflight:
                logger.warning("router_classifier_busy")
                return None
            self._classifier_inflight = True
        result: queue.Queue[RouteDecision | None] = queue.Queue(maxsize=1)
        classifier = self._classifier

        def classify() -> None:
            try:
                if classifier is None:
                    result.put(None)
                else:
                    result.put(classifier.classify(goal, messages))
            except Exception:
                result.put(None)
            finally:
                with self._classifier_lock:
                    self._classifier_inflight = False

        worker = threading.Thread(target=classify, daemon=True)
        worker.start()
        worker.join(timeout=self._classifier_timeout_seconds)
        if worker.is_alive():
            logger.warning("router_classifier_timeout")
            return None
        return result.get_nowait()

    def select(self, decision: RouteDecision) -> BaseAgent | None:
        """Resolve a route decision to an agent instance.

        Returns ``None`` for the fallback agent (handled by the runtime).
        """
        if decision.selected_agent == _FALLBACK_AGENT:
            return None
        try:
            return self._registry.get(decision.selected_agent)
        except KeyError:
            logger.error("missing_agent", extra={"agent": decision.selected_agent})
            return None

    # -- internal helpers -------------------------------------------------

    def _deterministic_route(self, goal: str) -> RouteDecision:
        """Match known intents from the input goal."""
        for pattern in _RECOMMENDATION_PATTERNS:
            if pattern.search(goal):
                return RouteDecision(
                    intent=RouteIntent.RECOMMENDATION,
                    selected_agent="recommendation",
                    rationale=f"Matched recommendation pattern: {pattern.pattern}",
                )

        return RouteDecision(
            intent=RouteIntent.UNKNOWN,
            selected_agent=_FALLBACK_AGENT,
            confidence=0.0,
            rationale="No deterministic pattern matched",
        )

    def _registry_has(self, name: str) -> bool:
        return name in self._registry.list_agents()

    @staticmethod
    def _model_fallback(reason: str) -> RouteDecision:
        return RouteDecision(
            intent=RouteIntent.UNKNOWN,
            selected_agent=_FALLBACK_AGENT,
            confidence=0.0,
            rationale=reason,
        )
