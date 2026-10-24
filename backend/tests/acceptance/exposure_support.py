"""Synthetic capabilities and specialists for exposure-entry certification."""

from __future__ import annotations

from typing import Any

from app.agents.base import BaseAgent
from app.capabilities.base import BaseCapability
from app.capabilities.types import ActionDescriptor, CapabilityResult
from app.harness.authority import RUNTIME_OWNED_FIELDS
from app.harness.model_gateway import ModelGateway


class RecordingReadCapability(BaseCapability):
    """Read capability that records exactly which trusted arguments it saw."""

    def __init__(
        self,
        *,
        name: str = "synthetic",
        action: str = "echo",
        public_name: str = "synthetic_echo",
        requires_auth: bool = True,
        extra_properties: dict[str, Any] | None = None,
    ) -> None:
        self._name = name
        self._action = action
        self._public_name = public_name
        self._requires_auth = requires_auth
        self._extra_properties = dict(extra_properties or {})
        self.calls: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "Synthetic read capability for exposure certification"

    def actions(self) -> list[ActionDescriptor]:
        properties: dict[str, Any] = {"value": {"type": "string"}}
        properties.update(self._extra_properties)
        return [
            ActionDescriptor(
                name=self._action,
                public_name=self._public_name,
                description=self.description,
                input_schema={
                    "type": "object",
                    "properties": properties,
                    "required": ["value"],
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "properties": {"value": {"type": "string"}},
                    "required": ["value"],
                },
                requires_auth=self._requires_auth,
            )
        ]

    async def execute(self, action: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(dict(kwargs))
        if action != self._action:
            return CapabilityResult.fail(
                "Unknown action", error_type="invalid_action"
            ).to_dict()
        return CapabilityResult.ok(value=str(kwargs.get("value", ""))).to_dict()


class RecordingWriteCapability(BaseCapability):
    """Side-effect capability for MCP policy/idempotency certification."""

    def __init__(
        self,
        *,
        name: str = "synthetic",
        action: str = "append",
        public_name: str = "synthetic_append",
    ) -> None:
        self._name = name
        self._action = action
        self._public_name = public_name
        self.calls: list[dict[str, Any]] = []

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "Synthetic side-effect capability for exposure certification"

    def actions(self) -> list[ActionDescriptor]:
        return [
            ActionDescriptor(
                name=self._action,
                public_name=self._public_name,
                description=self.description,
                input_schema={
                    "type": "object",
                    "properties": {
                        "value": {"type": "string"},
                        "idempotency_key": {"type": "string"},
                    },
                    "required": ["value"],
                    "additionalProperties": False,
                },
                output_schema={
                    "type": "object",
                    "properties": {"appended": {"type": "string"}},
                    "required": ["appended"],
                },
                requires_auth=True,
                is_side_effect=True,
                approval_required=True,
                idempotency_mode="required",
            )
        ]

    async def execute(self, action: str, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(dict(kwargs))
        return CapabilityResult.ok(appended=str(kwargs.get("value", ""))).to_dict()


class SyntheticSpecialist(BaseAgent):
    """Specialist that can only reach capabilities through the Runtime invoker."""

    def __init__(
        self,
        capability: str = "synthetic_echo",
        arguments: dict[str, Any] | None = None,
        *,
        capability_invoker: Any = None,
    ) -> None:
        self._capability = capability
        self._arguments = dict(arguments or {"value": "specialist"})
        self._capability_invoker = capability_invoker

    def bind_runtime(self, *, capability_invoker: Any) -> "SyntheticSpecialist":
        return SyntheticSpecialist(
            self._capability,
            self._arguments,
            capability_invoker=capability_invoker,
        )

    async def execute(self, task: Any) -> dict[str, Any]:
        if self._capability_invoker is None:
            raise AssertionError("specialist must receive a capability invoker")
        result = await self._capability_invoker(self._capability, self._arguments)
        return {
            "kind": "subagent",
            "name": "recommendation",
            "status": "completed" if result.get("success") else "failed",
            "role": "assistant",
            "content": "Synthetic specialist result",
            "data": {"capability_result": result},
            "evidence": {"source": "synthetic-specialist"},
        }

    async def plan(self, task: Any) -> dict[str, Any]:
        return {"goal": getattr(task, "goal", ""), "steps": []}

    async def reflect(self, task: Any, result: Any) -> dict[str, Any]:
        return {"goal_achieved": True, "observations": []}


class NoModelGateway(ModelGateway):
    """The specialist path must not call the primary model gateway."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def infer(self, **kwargs: Any) -> Any:
        self.calls.append("infer")
        raise AssertionError("primary model must not be called")

    def stream_infer(self, **kwargs: Any) -> Any:
        self.calls.append("stream_infer")
        raise AssertionError("primary model must not be called")

    async def synthesize(self, **kwargs: Any) -> str:
        self.calls.append("synthesize")
        raise AssertionError("primary model must not be called")

    async def synthesize_result(self, **kwargs: Any) -> Any:
        self.calls.append("synthesize_result")
        raise AssertionError("primary model must not be called")


def authority_extra_properties() -> dict[str, Any]:
    """Every runtime-owned field as a public schema property for stripping tests."""
    return {field: {"type": "string"} for field in sorted(RUNTIME_OWNED_FIELDS)}
