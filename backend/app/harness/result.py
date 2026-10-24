from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from app.harness.contracts import ErrorCode, InvocationResult


class AgentResult(BaseModel):
    """Normalized result returned by a Capability or Subagent.

    The harness treats this as an opaque, domain-neutral tool result.  Domain
    agents can put their facts in ``data`` and bounded audit information in
    ``evidence``; neither field is interpreted by the runtime.
    """

    kind: Literal["capability", "subagent"]
    name: str
    status: Literal["completed", "degraded", "failed"] = "completed"
    data: dict[str, Any] = Field(default_factory=dict)
    evidence: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None
    content: str | None = None

    def prompt_payload(self) -> dict[str, Any]:
        """Return the safe, structured payload exposed to the model gateway."""
        payload: dict[str, Any] = {
            "kind": self.kind,
            "name": self.name,
            "status": self.status,
            "data": self.data,
            "evidence": self.evidence,
        }
        if self.error_code:
            payload["error_code"] = self.error_code
        return payload

    @classmethod
    def from_raw(
        cls,
        value: Any,
        *,
        kind: Literal["capability", "subagent"],
        name: str,
    ) -> "AgentResult":
        """Normalize a new or legacy execution result.

        Keeping this boundary tolerant lets existing agents migrate without
        forcing the Runtime to understand their domain-specific dictionary.
        """
        if isinstance(value, InvocationResult):
            return cls.from_invocation_result(value, kind=kind, name=name)
        if isinstance(value, BaseException):
            return cls(
                kind=kind,
                name=name,
                status="failed",
                error_code="permanent",
            )
        if isinstance(value, cls):
            return value
        if not isinstance(value, dict):
            return cls(kind=kind, name=name, data={"value": value})

        if "data" in value:
            return cls(
                kind=value.get("kind", kind),
                name=str(value.get("name", name)),
                status=value.get("status", "completed"),
                data=value.get("data") or {},
                evidence=value.get("evidence") or {},
                error_code=value.get("error_code"),
                content=value.get("content"),
            )

        reserved = {
            "role",
            "content",
            "evidence",
            "status",
            "error_code",
            "success",
        }
        data = {key: item for key, item in value.items() if key not in reserved}
        if not value.get("success", True):
            data = {key: item for key, item in data.items() if key != "profile"}
        return cls(
            kind=kind,
            name=name,
            status="completed" if value.get("success", True) else "failed",
            data=data,
            evidence=value.get("evidence") or {},
            error_code=value.get("error_code"),
            content=value.get("content"),
        )

    @classmethod
    def from_invocation_result(
        cls,
        result: InvocationResult,
        *,
        kind: Literal["capability", "subagent"],
        name: str,
    ) -> "AgentResult":
        """Convert the versioned invocation contract into the legacy result."""
        return cls(
            kind=kind,
            name=name,
            status="completed" if result.status == "succeeded" else "failed",
            data=result.output,
            error_code=(
                result.error_code.value
                if isinstance(result.error_code, ErrorCode)
                else result.error_code
            ),
        )
