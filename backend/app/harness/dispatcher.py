"""The only execution boundary for model-proposed capability invocations."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
import hashlib
import json
from time import monotonic
from typing import Any
from uuid import uuid4

from pydantic import ValidationError

from app.capabilities.registry import CapabilityRegistry
from app.harness.budget import (
    CancellationToken,
    DeadlineExceededError,
    RunBudget,
    RunCancellationError,
)
from app.harness.capability_adapter import CapabilityAdapter
from app.harness.contracts import (
    AgentDecision,
    ExecutionContext,
    InvocationRequest,
    InvocationResult,
    RunEvent,
)
from app.harness.normalizer import (
    ResultNormalizer,
    SchemaContractError,
    validate_input,
)
from app.harness.policy import Approval, PolicyEngine, Principal


class Dispatcher:
    """Resolve, authorize, execute and normalize one model decision."""

    def __init__(
        self,
        registry: CapabilityRegistry,
        *,
        policy_engine: PolicyEngine | None = None,
        approval: Approval | None = None,
        idempotency_store: Any | None = None,
        adapter_factory: Callable[[Any], CapabilityAdapter] | None = None,
        event_writer: Callable[[RunEvent], Awaitable[Any] | Any] | None = None,
        result_normalizer: ResultNormalizer | None = None,
    ) -> None:
        self.registry = registry
        self.policy_engine = policy_engine or PolicyEngine()
        self.approval = approval
        self.idempotency_store = idempotency_store
        self.adapter_factory = adapter_factory
        self.event_writer = event_writer
        self.result_normalizer = result_normalizer or ResultNormalizer()
        self.events: list[RunEvent] = []
        self._sequence = 0
        self._successful_invocations: dict[tuple[str, str, str], InvocationResult] = {}

    async def dispatch(
        self,
        decision: AgentDecision,
        context: ExecutionContext,
        *,
        budget: RunBudget | None = None,
        cancellation: CancellationToken | None = None,
        approval: Approval | None = None,
        idempotency_key: str | None = None,
    ) -> InvocationResult:
        # The model decision id is the stable invocation proposal identity.  A
        # retry of the same proposal must not manufacture a new correlation id.
        invocation_id = decision.decision_id or uuid4().hex
        if decision.run_id != context.run_id:
            return self._result(
                invocation_id, "denied", "policy_denied", "Run identity mismatch"
            )
        if decision.action != "invoke":
            return self._result(
                invocation_id,
                "denied",
                "invalid_request",
                "Only invoke decisions can be dispatched",
            )
        if not decision.capability or not decision.capability_version:
            return self._result(
                invocation_id,
                "denied",
                "invalid_request",
                "Capability and version are required",
            )

        try:
            request = InvocationRequest(
                invocation_id=invocation_id,
                run_id=decision.run_id,
                capability=decision.capability,
                capability_version=decision.capability_version,
                arguments=decision.arguments,
                idempotency_key=idempotency_key
                or decision.arguments.get("idempotency_key"),
            )
        except ValidationError:
            return self._result(
                invocation_id,
                "denied",
                "identity_spoofing",
                "Runtime-owned fields are not accepted",
            )
        cache_key = (
            request.run_id,
            request.invocation_id,
            hashlib.sha256(
                json.dumps(
                    request.arguments,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                ).encode("utf-8")
            ).hexdigest(),
        )
        cached = self._successful_invocations.get(cache_key)
        if cached is not None:
            return cached.model_copy(deep=True)
        owner = self.registry.find_action(request.capability)
        if owner is None:
            return self._result(
                invocation_id,
                "denied",
                "not_configured",
                "Capability action is not configured",
            )
        capability, descriptor = owner
        if descriptor.version != request.capability_version:
            return self._result(
                invocation_id,
                "denied",
                "not_configured",
                "Capability version is not configured",
            )
        try:
            validate_input(request.arguments, descriptor)
        except (SchemaContractError, ValueError):
            return self._result(
                invocation_id,
                "denied",
                "invalid_request",
                "Capability arguments did not match the declared input contract",
            )

        principal = (
            Principal(context.principal_id)
            if context.principal_id is not None
            else None
        )
        policy = self.policy_engine.authorize(
            principal,
            descriptor,
            approval or self.approval,
            request.idempotency_key,
        )
        if not policy.allowed:
            return self._result(
                invocation_id,
                "denied",
                policy.error_type or "policy_denied",
                policy.reason or "Capability denied",
            )
        if descriptor.is_side_effect and self.idempotency_store is None:
            return self._result(
                invocation_id,
                "denied",
                "idempotency_required",
                "An idempotency store is required for writes",
            )
        if context.capability_allowlist and not (
            request.capability in context.capability_allowlist
            or capability.name in context.capability_allowlist
            or descriptor.name in context.capability_allowlist
        ):
            return self._result(
                invocation_id,
                "denied",
                "policy_denied",
                "Capability is not allowed for this run",
            )

        if budget is not None:
            try:
                budget.consume_tool_call()
            except Exception:
                return self._result(
                    invocation_id, "denied", "budget_exceeded", "Tool budget exceeded"
                )
        cancellation = cancellation or CancellationToken()
        if cancellation.is_cancelled():
            return self._result(
                invocation_id, "cancelled", "cancelled", "Invocation cancelled"
            )

        await self._emit(
            request, "invocation_start", {"capability": request.capability}
        )
        adapter = (
            self.adapter_factory(capability)
            if self.adapter_factory is not None
            else CapabilityAdapter(
                capability,
                policy_engine=self.policy_engine,
                approval=approval or self.approval,
                idempotency_store=self.idempotency_store,
            )
        )
        started = monotonic()
        try:
            raw = await self._run_with_controls(
                adapter.execute(context, descriptor.name, request.arguments),
                descriptor.timeout_seconds,
                cancellation,
            )
            if not isinstance(raw, dict):
                raw = {"success": True, "value": raw}
            normalized = self.result_normalizer.normalize(
                raw,
                descriptor=descriptor,
                run_id=context.run_id,
                decision_id=decision.decision_id,
                invocation_id=invocation_id,
                trace_id=context.trace_id,
                sequence=self._sequence + 1,
                latency_ms=max(0, round((monotonic() - started) * 1000)),
            )
            error_type = normalized.error_code or ""
            denied_types = {
                "unauthorized",
                "policy_denied",
                "identity_spoofing",
                "idempotency_required",
                "idempotency_conflict",
                "not_configured",
            }
            success = normalized.status == "succeeded" and not error_type
            status = (
                "succeeded"
                if success
                else ("denied" if error_type in denied_types else "failed")
            )
            result = self._result(
                invocation_id,
                status,
                None if success else (error_type or "tool_error"),
                None if success else "Capability execution failed",
                output=normalized.ui_projection(),
            )
            result.run_id = normalized.run_id
            result.decision_id = normalized.decision_id
            result.trace_id = normalized.trace_id
            result.sequence = normalized.sequence
            result.capability = normalized.capability
            result.capability_version = normalized.capability_version
            result.artifacts = normalized.artifacts
            result.usage = normalized.usage
            result.latency_ms = normalized.latency_ms
            result.provenance = normalized.provenance
            result.model_output = normalized.model_projection()
        except RunCancellationError:
            result = self._result(
                invocation_id, "cancelled", "cancelled", "Invocation cancelled"
            )
        except asyncio.TimeoutError:
            result = self._result(
                invocation_id,
                "timeout",
                "timeout",
                "Capability execution timed out",
                retryable=True,
            )
        except DeadlineExceededError:
            result = self._result(
                invocation_id, "cancelled", "cancelled", "Invocation cancelled"
            )
        except Exception:
            result = self._result(
                invocation_id, "failed", "internal", "Capability execution failed"
            )
        result.output.setdefault(
            "latency_ms", max(0, round((monotonic() - started) * 1000))
        )
        await self._emit(
            request,
            "invocation_end",
            {"status": result.status, "error_code": result.error_code},
        )
        if result.status == "succeeded":
            self._successful_invocations[cache_key] = result.model_copy(deep=True)
        return result

    async def _run_with_controls(
        self,
        operation: Awaitable[Any],
        timeout_seconds: float,
        cancellation: CancellationToken,
    ) -> Any:
        task = asyncio.ensure_future(operation)
        cancel_event = getattr(cancellation, "_event", None)
        cancel_task = (
            asyncio.create_task(cancel_event.wait())
            if cancel_event is not None
            else None
        )
        try:
            wait_set = {task}
            if cancel_task is not None:
                wait_set.add(cancel_task)
            done, _ = await asyncio.wait(
                wait_set,
                timeout=max(0.001, timeout_seconds),
                return_when=asyncio.FIRST_COMPLETED,
            )
            if task in done:
                return task.result()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            if cancel_task is not None and cancel_task in done:
                raise RunCancellationError()
            raise asyncio.TimeoutError()
        finally:
            if cancel_task is not None and not cancel_task.done():
                cancel_task.cancel()
                await asyncio.gather(cancel_task, return_exceptions=True)

    async def _emit(
        self, request: InvocationRequest, event_type: str, payload: dict[str, Any]
    ) -> None:
        self._sequence += 1
        event = RunEvent(
            run_id=request.run_id,
            sequence=self._sequence,
            event_type=event_type,
            invocation_id=request.invocation_id,
            payload=payload,
        )
        self.events.append(event)
        if self.event_writer is not None:
            result = self.event_writer(event)
            if hasattr(result, "__await__"):
                await result

    @staticmethod
    def _safe_output(raw: dict[str, Any]) -> dict[str, Any]:
        return {"error_type": str(raw.get("error_type") or "tool_error")}

    @staticmethod
    def _result(
        invocation_id: str,
        status: str,
        error_code: str | None,
        message: str | None,
        *,
        output: dict[str, Any] | None = None,
        retryable: bool = False,
    ) -> InvocationResult:
        safe_output = dict(output or {})
        if error_code is not None:
            safe_output.setdefault("error_type", error_code)
        if message is not None:
            safe_output.setdefault("message", message)
        return InvocationResult(
            invocation_id=invocation_id,
            status=status,  # type: ignore[arg-type]
            output=safe_output,
            error_code=error_code,
            retryable=retryable,
        )
