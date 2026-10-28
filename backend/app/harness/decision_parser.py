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
_SAFE_DECISION_FIELDS = frozenset(
    {
        "schema_version",
        "decision_id",
        "run_id",
        "action",
        "capability",
        "capability_version",
        "arguments",
        "content",
    }
)
_DECISION_FAILURE_REASONS = frozenset(
    {
        "invalid_model_result",
        "model_cancelled",
        "provider_failure",
        "invalid_decision_shape",
        "schema_version_mismatch",
        "run_identity_mismatch",
        "authority_field_rejected",
        "decision_schema_invalid",
        "missing_capability",
        "missing_capability_version",
        "capability_version_mismatch",
        "invalid_arguments",
        "arguments_too_large",
        "multiple_tool_proposals",
        "invalid_tool_arguments",
        "empty_model_output",
        "invalid_json",
        "invalid_decision",
    }
)


def _safe_field_paths(locations: list[tuple[Any, ...]]) -> tuple[str, ...]:
    """Project validation locations to fixed public Decision field names."""
    fields: set[str] = set()
    for location in locations:
        root = location[0] if location else None
        field = (
            root if isinstance(root, str) and root in _SAFE_DECISION_FIELDS else "other"
        )
        fields.add(field)
    return tuple(sorted(fields))


class DecisionParseError(ValueError):
    """Safe, structured parse failure; raw provider payload is never retained."""

    def __init__(
        self,
        error_code: ErrorCode,
        message: str = "Invalid model decision",
        *,
        retryable: bool = False,
        reason_code: str = "invalid_decision",
        field_paths: tuple[str, ...] = (),
    ) -> None:
        self.error_code = error_code
        self.retryable = retryable
        self.reason_code = (
            reason_code
            if reason_code in _DECISION_FAILURE_REASONS
            else "invalid_decision"
        )
        self.field_paths = (
            _safe_field_paths([(field,) for field in field_paths])
            if field_paths
            else ()
        )
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
            raise DecisionParseError(
                ErrorCode.INVALID_REQUEST,
                retryable=True,
                reason_code="invalid_model_result",
            )
        if result.status == "cancelled" or result.error_code == "cancelled":
            raise DecisionParseError(
                ErrorCode.CANCELLED,
                "Model decision was cancelled",
                reason_code="model_cancelled",
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
            raise DecisionParseError(
                mapped, "Model decision failed", reason_code="provider_failure"
            )

        payload = self._payload(result)
        if not isinstance(payload, dict):
            raise DecisionParseError(
                ErrorCode.INVALID_REQUEST,
                retryable=True,
                reason_code="invalid_decision_shape",
            )
        if payload.get("schema_version", self.schema_version) != self.schema_version:
            raise DecisionParseError(
                ErrorCode.INVALID_REQUEST,
                "Unknown decision schema version",
                retryable=True,
                reason_code="schema_version_mismatch",
                field_paths=("schema_version",),
            )

        if expected_run_id is not None:
            proposed_run_id = payload.get("run_id")
            if proposed_run_id not in {None, expected_run_id}:
                raise DecisionParseError(
                    ErrorCode.INVALID_REQUEST,
                    "Run identity mismatch",
                    reason_code="run_identity_mismatch",
                    field_paths=("run_id",),
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
                    reason_code="authority_field_rejected",
                    field_paths=("arguments",),
                )
            if not payload.get("capability"):
                raise DecisionParseError(
                    ErrorCode.INVALID_REQUEST,
                    retryable=True,
                    reason_code="missing_capability",
                    field_paths=("capability",),
                )
            if not payload.get("capability_version"):
                raise DecisionParseError(
                    ErrorCode.INVALID_REQUEST,
                    retryable=True,
                    reason_code="missing_capability_version",
                    field_paths=("capability_version",),
                )
        validation_field_paths: tuple[str, ...] | None = None
        try:
            decision = AgentDecision.model_validate(payload)
        except ValidationError as exc:
            locations = [
                tuple(error.get("loc", ()))
                for error in exc.errors(
                    include_input=False, include_context=False, include_url=False
                )
            ]
            validation_field_paths = _safe_field_paths(locations)

        if validation_field_paths is not None:
            raise DecisionParseError(
                ErrorCode.INVALID_REQUEST,
                retryable=True,
                reason_code="decision_schema_invalid",
                field_paths=validation_field_paths,
            )

        if decision.action == "invoke":
            if not decision.capability or not decision.capability_version:
                raise DecisionParseError(
                    ErrorCode.INVALID_REQUEST,
                    retryable=True,
                    reason_code=(
                        "missing_capability"
                        if not decision.capability
                        else "missing_capability_version"
                    ),
                    field_paths=(
                        "capability"
                        if not decision.capability
                        else "capability_version",
                    ),
                )
            if decision.capability_version != self.schema_version:
                raise DecisionParseError(
                    ErrorCode.INVALID_REQUEST,
                    "Unknown capability contract version",
                    retryable=True,
                    reason_code="capability_version_mismatch",
                    field_paths=("capability_version",),
                )
            if _contains_authority(decision.arguments):
                raise DecisionParseError(
                    ErrorCode.UNAUTHORIZED,
                    "Authority fields are runtime-owned",
                    reason_code="authority_field_rejected",
                    field_paths=("arguments",),
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
                    ErrorCode.INVALID_REQUEST,
                    retryable=True,
                    reason_code="invalid_arguments",
                    field_paths=("arguments",),
                ) from exc
            if len(encoded) > self.max_arguments_bytes:
                raise DecisionParseError(
                    ErrorCode.INVALID_REQUEST,
                    "Decision arguments exceed the public limit",
                    retryable=True,
                    reason_code="arguments_too_large",
                    field_paths=("arguments",),
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
                    reason_code="multiple_tool_proposals",
                )
            call = result.tool_calls[0]
            if not isinstance(call, dict):
                raise DecisionParseError(
                    ErrorCode.INVALID_REQUEST,
                    retryable=True,
                    reason_code="invalid_decision_shape",
                )
            arguments = call.get("arguments", {})
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments or "{}")
                except json.JSONDecodeError as exc:
                    raise DecisionParseError(
                        ErrorCode.INVALID_REQUEST,
                        retryable=True,
                        reason_code="invalid_tool_arguments",
                        field_paths=("arguments",),
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
            raise DecisionParseError(
                ErrorCode.INVALID_REQUEST,
                retryable=True,
                reason_code="empty_model_output",
            )
        try:
            return _decode_json_object(result.text)
        except (TypeError, json.JSONDecodeError) as exc:
            raise DecisionParseError(
                ErrorCode.INVALID_REQUEST,
                retryable=True,
                reason_code="invalid_json",
            ) from exc

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
            raise DecisionParseError(
                ErrorCode.INVALID_REQUEST,
                retryable=True,
                reason_code="missing_capability",
                field_paths=("capability",),
            )
        return InvocationRequest(
            invocation_id=decision.decision_id,
            run_id=decision.run_id,
            capability=decision.capability,
            capability_version=decision.capability_version,
            arguments=decision.arguments,
            idempotency_key=decision.arguments.get("idempotency_key"),
        )
