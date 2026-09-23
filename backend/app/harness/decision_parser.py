"""Convert provider-neutral model output into the versioned Decision contract."""

from __future__ import annotations

import json
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from app.harness.contracts import (
    AgentDecision,
    ErrorCode,
    InvocationRequest,
)
from app.harness.authority import contains_runtime_owned_field
from app.harness.model_types import ModelCallResult


_SAFE_PROVIDER_CODES = frozenset(
    {
        "auth",
        "rate_limited",
        "timeout",
        "invalid_request",
        "transient",
        "permanent",
        "cancelled",
        "dns",
        "ssrf",
    }
)


class DecisionParseError(ValueError):
    """Safe, structured parse failure; raw provider payload is never retained."""

    def __init__(
        self,
        error_code: ErrorCode,
        message: str = "Invalid model decision",
        *,
        retryable: bool = False,
    ) -> None:
        self.error_code = error_code
        self.retryable = retryable
        super().__init__(message)


def _contains_authority(value: Any) -> bool:
    return contains_runtime_owned_field(value)


def _decode_json_object(text: str) -> dict[str, Any]:
    """Decode a provider JSON object while tolerating an outer markdown fence."""
    candidate = text.strip()
    lines = candidate.splitlines()
    if (
        len(lines) >= 3
        and lines[0].strip().lower() in {"```", "```json"}
        and lines[-1].strip() == "```"
    ):
        candidate = "\n".join(lines[1:-1]).strip()
    payload = json.loads(candidate)
    if not isinstance(payload, dict):
        raise TypeError("decision payload must be a JSON object")
    return payload


class DecisionParser:
    """Parse exactly one public, versioned Decision from a model result."""

    def __init__(
        self,
        *,
        schema_version: str = "v1",
        max_arguments_bytes: int = 8192,
        capability_aliases: dict[str, tuple[str, str]] | None = None,
    ) -> None:
        if max_arguments_bytes < 1:
            raise ValueError("max_arguments_bytes must be positive")
        self.schema_version = schema_version
        self.max_arguments_bytes = max_arguments_bytes
        self.capability_aliases = dict(capability_aliases or {})

    def parse(
        self,
        result: ModelCallResult,
        *,
        expected_run_id: str | None = None,
    ) -> AgentDecision:
        if not isinstance(result, ModelCallResult):
            raise DecisionParseError(ErrorCode.INVALID_REQUEST, retryable=True)
        if result.status == "cancelled" or result.error_code == "cancelled":
            raise DecisionParseError(
                ErrorCode.CANCELLED, "Model decision was cancelled"
            )
        if result.status == "failed":
            code = (
                result.error_code
                if result.error_code in _SAFE_PROVIDER_CODES
                else "permanent"
            )
            mapped = (
                ErrorCode.CANCELLED if code == "cancelled" else ErrorCode.PROVIDER_ERROR
            )
            raise DecisionParseError(mapped, "Model decision failed")

        payload = self._payload(result)
        if not isinstance(payload, dict):
            raise DecisionParseError(ErrorCode.INVALID_REQUEST, retryable=True)
        if payload.get("schema_version", self.schema_version) != self.schema_version:
            raise DecisionParseError(
                ErrorCode.INVALID_REQUEST,
                "Unknown decision schema version",
                retryable=True,
            )

        if expected_run_id is not None:
            proposed_run_id = payload.get("run_id")
            if proposed_run_id not in {None, expected_run_id}:
                raise DecisionParseError(
                    ErrorCode.INVALID_REQUEST, "Run identity mismatch"
                )
            payload = {**payload, "run_id": expected_run_id}

        # Some compatible providers follow the action/content shape but omit
        # the correlation field. Runtime owns the fallback identity so a valid
        # Decision is not rejected solely for that omission.
        if payload.get("action") in {"invoke", "respond", "finish"} and not payload.get(
            "decision_id"
        ):
            payload = {**payload, "decision_id": f"model-decision-{uuid4().hex}"}

        if payload.get("action") == "invoke":
            payload = self._canonicalize_invoke(payload)
            if _contains_authority(payload.get("arguments", {})):
                raise DecisionParseError(
                    ErrorCode.INVALID_REQUEST,
                    "Authority fields are runtime-owned",
                )
        try:
            decision = AgentDecision.model_validate(payload)
        except ValidationError as exc:
            raise DecisionParseError(ErrorCode.INVALID_REQUEST, retryable=True) from exc

        if decision.action == "invoke":
            if not decision.capability or not decision.capability_version:
                raise DecisionParseError(ErrorCode.INVALID_REQUEST, retryable=True)
            if decision.capability_version != self.schema_version:
                raise DecisionParseError(
                    ErrorCode.INVALID_REQUEST,
                    "Unknown capability contract version",
                    retryable=True,
                )
            if _contains_authority(decision.arguments):
                raise DecisionParseError(
                    ErrorCode.UNAUTHORIZED, "Authority fields are runtime-owned"
                )
            try:
                encoded = json.dumps(
                    decision.arguments,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            except (TypeError, ValueError) as exc:
                raise DecisionParseError(
                    ErrorCode.INVALID_REQUEST, retryable=True
                ) from exc
            if len(encoded) > self.max_arguments_bytes:
                raise DecisionParseError(
                    ErrorCode.INVALID_REQUEST,
                    "Decision arguments exceed the public limit",
                    retryable=True,
                )
        return decision

    def _payload(self, result: ModelCallResult) -> dict[str, Any]:
        if result.decision is not None:
            return dict(result.decision)
        if result.tool_calls:
            if len(result.tool_calls) != 1:
                raise DecisionParseError(
                    ErrorCode.INVALID_REQUEST,
                    "Exactly one tool proposal is required",
                    retryable=True,
                )
            call = result.tool_calls[0]
            if not isinstance(call, dict):
                raise DecisionParseError(ErrorCode.INVALID_REQUEST, retryable=True)
            arguments = call.get("arguments", {})
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments or "{}")
                except json.JSONDecodeError as exc:
                    raise DecisionParseError(
                        ErrorCode.INVALID_REQUEST, retryable=True
                    ) from exc
            return {
                "schema_version": call.get("schema_version", self.schema_version),
                "decision_id": call.get("decision_id") or "model-decision",
                "run_id": call.get("run_id") or result.model,
                "action": "invoke",
                "capability": call.get("capability") or call.get("name"),
                "capability_version": call.get("capability_version")
                or call.get("version"),
                "arguments": arguments,
            }
        if not result.text:
            raise DecisionParseError(ErrorCode.INVALID_REQUEST, retryable=True)
        try:
            return _decode_json_object(result.text)
        except (TypeError, json.JSONDecodeError) as exc:
            raise DecisionParseError(ErrorCode.INVALID_REQUEST, retryable=True) from exc

    def _canonicalize_invoke(self, payload: dict[str, Any]) -> dict[str, Any]:
        if "arguments" not in payload and "public_arguments" in payload:
            payload = {
                **payload,
                "arguments": payload["public_arguments"],
            }
            payload.pop("public_arguments", None)
        capability = payload.get("capability")
        if isinstance(capability, str) and capability in self.capability_aliases:
            canonical, version = self.capability_aliases[capability]
            payload = {
                **payload,
                "capability": canonical,
                "capability_version": payload.get("capability_version") or version,
            }
        return payload

    @staticmethod
    def to_invocation(decision: AgentDecision) -> InvocationRequest | None:
        if decision.action != "invoke":
            return None
        if not decision.capability or not decision.capability_version:
            raise DecisionParseError(ErrorCode.INVALID_REQUEST, retryable=True)
        return InvocationRequest(
            invocation_id=decision.decision_id,
            run_id=decision.run_id,
            capability=decision.capability,
            capability_version=decision.capability_version,
            arguments=decision.arguments,
            idempotency_key=decision.arguments.get("idempotency_key"),
        )
