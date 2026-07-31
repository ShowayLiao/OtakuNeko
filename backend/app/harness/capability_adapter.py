from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.agents.base import BaseAgent
from app.harness.result import AgentResult
from app.trace import TraceEventType
from app.trace.recorder import safe_argument_shape, trace_span


class CapabilityAgent(BaseAgent):
    """Adapt a single Capability operation to the generic agent protocol."""

    def __init__(
        self,
        *,
        name: str,
        capability: Any,
        action: str,
        input_builder: Callable[[Any], dict[str, Any]] | None = None,
    ) -> None:
        self.name = name
        self._capability = capability
        self._action = action
        self._input_builder = input_builder or (lambda task: {})

    async def execute(self, task: Any) -> AgentResult:
        arguments = self._input_builder(task)
        async with trace_span(
            TraceEventType.CAPABILITY_CALL,
            f"capability.{self.name}",
            {
                "action": self._action,
                "argument_shape": safe_argument_shape(arguments),
            },
        ):
            raw = await self._capability.execute(self._action, **arguments)

        if isinstance(raw, AgentResult):
            return raw
        if not isinstance(raw, dict):
            return AgentResult(
                kind="capability",
                name=self.name,
                data={"value": raw},
            )

        success = bool(raw.get("success", True))
        data = {
            key: value
            for key, value in raw.items()
            if key not in {"success", "evidence", "error_code"}
        }
        return AgentResult(
            kind="capability",
            name=self.name,
            status="completed" if success else "failed",
            data=data,
            evidence=raw.get("evidence") or {},
            error_code=raw.get("error_code"),
        )

    async def plan(self, task: Any) -> dict[str, Any]:
        return {
            "goal": getattr(task, "goal", ""),
            "steps": [f"Call capability {self.name}"],
            "estimated_tools": [self.name],
        }

    async def reflect(self, task: Any, result: Any) -> dict[str, Any]:
        status = result.status if isinstance(result, AgentResult) else "unknown"
        return {
            "goal_achieved": status == "completed",
            "observations": [f"Capability {self.name} returned {status}"],
        }
