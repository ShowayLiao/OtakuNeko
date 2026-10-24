"""Observation-aware scripted model double for offline evaluation and Agent CI.

The fake is a provider boundary: it never executes capabilities or changes
Runtime state. Before returning a scripted Decision it freezes what the Runtime
actually supplied - history messages, untrusted capability feedback and the
model-safe context snapshot - and verifies any declared expectations. A missing
or incorrect observation fails closed instead of replaying the script by index.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass
from functools import cached_property
import json
from typing import Any, cast, get_args

from app.evaluation.types import ScriptEvent
from app.harness.model_gateway import ModelGateway
from app.harness.model_types import (
    ModelCallResult,
    ModelStreamEvent,
    ProviderErrorCode,
)
from app.harness.runtime import TOOL_FEEDBACK_PREFIX

FEEDBACK_PREFIX = TOOL_FEEDBACK_PREFIX

_PROVIDER_ERROR_CODES = frozenset(get_args(ProviderErrorCode))
_DISPLAY_LIMIT = 80


class ScriptedObservationError(RuntimeError):
    """A scripted step did not receive the observation it declared."""

    def __init__(self, message: str, *, call_number: int | None = None) -> None:
        self.reason = message
        self.call_number = call_number
        prefix = (
            f"scripted observation failed at call {call_number}: "
            if call_number is not None
            else "scripted observation failed: "
        )
        super().__init__(prefix + message)


def _bounded(value: Any, limit: int = _DISPLAY_LIMIT) -> str:
    rendered = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
    return rendered if len(rendered) <= limit else f"{rendered[:limit]}..."


def _kind(value: Any) -> str:
    return type(value).__name__


def _subset_mismatches(expected: Any, actual: Any, path: str) -> list[str]:
    """Return human-readable mismatches for a recursive JSON subset match."""
    if isinstance(expected, Mapping):
        if not isinstance(actual, Mapping):
            return [f"{path}: expected an object, observed {_kind(actual)}"]
        failures: list[str] = []
        for key, expected_value in expected.items():
            child = f"{path}.{key}"
            if key not in actual:
                failures.append(f"{child}: missing")
            else:
                failures.extend(_subset_mismatches(expected_value, actual[key], child))
        return failures
    if isinstance(expected, (list, tuple)):
        if not isinstance(actual, (list, tuple)):
            return [f"{path}: expected a list, observed {_kind(actual)}"]
        if len(expected) != len(actual):
            return [f"{path}: expected {len(expected)} item(s), observed {len(actual)}"]
        failures = []
        for index, (expected_item, actual_item) in enumerate(
            zip(expected, actual, strict=True)
        ):
            failures.extend(
                _subset_mismatches(
                    expected_item,
                    actual_item,
                    f"{path}[{index}]",
                )
            )
        return failures
    if isinstance(expected, bool) != isinstance(actual, bool):
        return [f"{path}: expected {_bounded(expected)}, observed {_bounded(actual)}"]
    if expected != actual:
        return [f"{path}: expected {_bounded(expected)}, observed {_bounded(actual)}"]
    return []


@dataclass(frozen=True)
class ExpectedMessage:
    """One message that must exist somewhere in the model history."""

    role: str
    content_contains: str = ""

    def matches(self, message: Mapping[str, Any]) -> bool:
        if message.get("role") != self.role:
            return False
        content = message.get("content")
        return isinstance(content, str) and self.content_contains in content


@dataclass(frozen=True)
class ScriptedObservation:
    """Immutable snapshot of one Runtime-to-provider model call."""

    call_number: int
    goal: str
    messages: tuple[dict[str, Any], ...]
    context: Mapping[str, Any] | None
    run_id: str | None
    trace_id: str | None
    capability_catalog: tuple[Mapping[str, Any], ...]

    @property
    def history(self) -> tuple[dict[str, Any], ...]:
        return self.messages

    @property
    def roles(self) -> tuple[str, ...]:
        return tuple(
            str(message.get("role", ""))
            for message in self.messages
            if isinstance(message, Mapping)
        )

    @cached_property
    def tool_results(self) -> tuple[dict[str, Any], ...]:
        """Parse Runtime capability feedback as untrusted JSON observations."""
        results: list[dict[str, Any]] = []
        for index, message in enumerate(self.messages):
            if not isinstance(message, Mapping):
                continue
            if message.get("role") != "user":
                continue
            content = message.get("content")
            if not isinstance(content, str) or not content.startswith(FEEDBACK_PREFIX):
                continue
            try:
                payload = json.loads(content[len(FEEDBACK_PREFIX) :])
            except json.JSONDecodeError as exc:
                raise ScriptedObservationError(
                    f"tool result feedback at message {index} is not valid JSON",
                    call_number=self.call_number,
                ) from exc
            if (
                not isinstance(payload, dict)
                or not isinstance(payload.get("safe_output"), dict)
                or not isinstance(payload.get("provenance"), dict)
            ):
                raise ScriptedObservationError(
                    f"message {index} starts with the feedback marker but is not "
                    "Runtime capability feedback",
                    call_number=self.call_number,
                )
            results.append(payload)
        return tuple(results)

    @property
    def last_tool_result(self) -> dict[str, Any] | None:
        results = self.tool_results
        return results[-1] if results else None


@dataclass(frozen=True)
class ObservationExpectation:
    """Declarative checks executed before a scripted Decision is returned."""

    tool_results: int | None = None
    last_tool_result: Mapping[str, Any] | None = None
    history_contains: Sequence[ExpectedMessage] = ()
    message_count: int | None = None
    message_roles: Sequence[str] | None = None
    context: Mapping[str, Any] | None = None
    run_id: str | None = None
    trace_id: str | None = None
    check: Callable[[ScriptedObservation], None] | None = None

    def __post_init__(self) -> None:
        if self.tool_results is not None and (
            isinstance(self.tool_results, bool) or self.tool_results < 0
        ):
            raise ValueError("tool_results must be a non-negative integer")
        if self.message_count is not None and (
            isinstance(self.message_count, bool) or self.message_count < 0
        ):
            raise ValueError("message_count must be a non-negative integer")
        object.__setattr__(self, "history_contains", tuple(self.history_contains))
        if self.message_roles is not None:
            object.__setattr__(self, "message_roles", tuple(self.message_roles))
        if self.last_tool_result is not None and not isinstance(
            self.last_tool_result, Mapping
        ):
            raise ValueError("last_tool_result must be a mapping")
        if self.context is not None and not isinstance(self.context, Mapping):
            raise ValueError("context must be a mapping")

    def verify(self, observation: ScriptedObservation) -> list[str]:
        failures: list[str] = []
        results = observation.tool_results
        if self.tool_results is not None and len(results) != self.tool_results:
            failures.append(
                f"expected {self.tool_results} tool result(s), observed {len(results)}"
            )
        if self.last_tool_result is not None:
            if not results:
                failures.append(
                    "expected a last tool result, but no tool result feedback was observed"
                )
            else:
                failures.extend(
                    _subset_mismatches(
                        self.last_tool_result,
                        results[-1],
                        "last tool result",
                    )
                )
        if self.message_count is not None and len(observation.messages) != (
            self.message_count
        ):
            failures.append(
                f"expected {self.message_count} history message(s), "
                f"observed {len(observation.messages)}"
            )
        if self.message_roles is not None and observation.roles != tuple(
            self.message_roles
        ):
            failures.append(
                f"expected history roles {list(self.message_roles)}, "
                f"observed {list(observation.roles)}"
            )
        for expected in self.history_contains:
            if not any(
                isinstance(message, Mapping) and expected.matches(message)
                for message in observation.messages
            ):
                failures.append(
                    f"history message role={expected.role!r} containing "
                    f"{expected.content_contains!r} is missing"
                )
        if self.context is not None:
            if observation.context is None:
                failures.append("expected a Runtime context snapshot, observed none")
            else:
                failures.extend(
                    _subset_mismatches(self.context, observation.context, "context")
                )
        if self.run_id is not None and observation.run_id != self.run_id:
            failures.append(
                f"run_id: expected {_bounded(self.run_id)}, "
                f"observed {_bounded(observation.run_id)}"
            )
        if self.trace_id is not None and observation.trace_id != self.trace_id:
            failures.append(
                f"trace_id: expected {_bounded(self.trace_id)}, "
                f"observed {_bounded(observation.trace_id)}"
            )
        if self.check is not None:
            try:
                self.check(observation)
            except Exception as exc:
                failures.append(
                    f"custom check failed: {type(exc).__name__}: {_bounded(str(exc))}"
                )
        return failures


@dataclass(frozen=True)
class ScriptedStep:
    """One scripted provider response and its optional observation contract."""

    decision: (
        Mapping[str, Any] | Callable[[ScriptedObservation], Mapping[str, Any]] | None
    ) = None
    text: str | None = None
    provider_error: str | None = None
    expect: ObservationExpectation | None = None

    def __post_init__(self) -> None:
        configured = (
            self.decision is not None,
            self.text is not None,
            self.provider_error is not None,
        )
        if sum(configured) != 1:
            raise ValueError(
                "a scripted step requires exactly one of decision, text, provider_error"
            )
        if self.provider_error is not None and (
            self.provider_error not in _PROVIDER_ERROR_CODES
        ):
            raise ValueError(f"unsupported provider error code: {self.provider_error}")
        if self.text is not None and not isinstance(self.text, str):
            raise ValueError("scripted text must be a string")
        if (
            self.decision is not None
            and not isinstance(self.decision, Mapping)
            and not callable(self.decision)
        ):
            raise ValueError("scripted decision must be a mapping or callable")


def _fixture_decision(
    event: ScriptEvent, index: int
) -> Callable[[ScriptedObservation], dict[str, Any]]:
    """Build the entrypoint fixture Decision against the observed Runtime run."""

    def decide(observation: ScriptedObservation) -> dict[str, Any]:
        fixture_id = event.invocation_id or f"fixture-decision-{index}"
        decision: dict[str, Any] = {
            "schema_version": "v1",
            "decision_id": f"{observation.run_id or 'eval'}-{fixture_id}",
            "run_id": observation.run_id,
        }
        if event.type == "tool_call_start":
            decision.update(
                {
                    "action": "invoke",
                    "capability": event.name,
                    "capability_version": "v1",
                    "arguments": dict(event.arguments or {}),
                }
            )
        else:
            decision.update(
                {
                    "action": "respond",
                    "content": event.content or "",
                }
            )
        return decision

    return decide


class ScriptedLLM(ModelGateway):
    """A ModelGateway double that observes before it scripts the next Decision.

    Observation failures raise ``ScriptedObservationError``. The entrypoint
    evaluation executes through ``AgentRuntime.stream_decision``, which maps
    provider exceptions to a failed Run; the eval layer checks
    ``observation_failures`` before canonical validation. Callers of other
    Runtime entrypoints should handle this error explicitly.
    """

    def __init__(
        self,
        steps: Sequence[ScriptedStep],
        *,
        provider: str = "scripted",
        model: str = "scripted-v1",
        verify_context_identity: bool = True,
    ) -> None:
        self.steps = tuple(steps)
        self.provider = provider
        self.model = model
        self.verify_context_identity = verify_context_identity
        self.calls: list[ScriptedObservation] = []
        # Runtime owns terminal mapping and converts provider exceptions into a
        # failed Run. Retain the exact observation failure so tests and Eval
        # evidence can distinguish it from other provider errors.
        self.observation_failures: list[str] = []
        self._expectations_verified = 0

    @staticmethod
    def script_steps(events: Sequence[ScriptEvent]) -> tuple[ScriptedStep, ...]:
        """Translate entrypoint fixture events into observed scripted steps.

        ``tool_call_start`` produces the invoke Decision; a following
        ``tool_call_end`` is declarative and may carry the expected normalized
        capability output via ``output``. Expected ``output`` uses the
        normalized business-data shape (the ``safe_output`` payload), not the
        raw capability result envelope.
        """
        steps: list[ScriptedStep] = []
        invocations = 0
        starts: list[dict[str, Any]] = []
        expected_outputs: list[Mapping[str, Any] | None] = []

        def expectation() -> ObservationExpectation:
            last_output = expected_outputs[-1] if expected_outputs else None
            return ObservationExpectation(
                tool_results=invocations,
                last_tool_result=(
                    {"safe_output": dict(last_output)}
                    if last_output is not None
                    else None
                ),
            )

        for index, event in enumerate(events, 1):
            if event.type == "tool_call_start":
                if not event.name:
                    raise ValueError("scripted invoke event requires a capability name")
                steps.append(
                    ScriptedStep(
                        decision=_fixture_decision(event, index),
                        expect=expectation(),
                    )
                )
                starts.append(
                    {
                        "invocation_id": event.invocation_id,
                        "name": event.name,
                    }
                )
                expected_outputs.append(event.output)
                invocations += 1
            elif event.type == "tool_call_end":
                if not starts:
                    raise ValueError(
                        "scripted tool_call_end requires a preceding invoke"
                    )
                match: int | None = None
                for position in range(len(starts) - 1, -1, -1):
                    started = starts[position]
                    if event.invocation_id is not None:
                        if started["invocation_id"] == event.invocation_id:
                            match = position
                            break
                    elif event.name is not None and started["name"] == event.name:
                        match = position
                        break
                if match is None:
                    if event.invocation_id is not None or event.name is not None:
                        raise ValueError(
                            "scripted tool_call_end does not match a preceding invoke"
                        )
                    match = len(starts) - 1
                if event.output is not None:
                    expected_outputs[match] = event.output
            elif event.type == "message_chunk":
                steps.append(
                    ScriptedStep(
                        decision=_fixture_decision(event, index),
                        expect=expectation(),
                    )
                )
            elif event.type == "provider_error":
                code = (
                    event.code if event.code in _PROVIDER_ERROR_CODES else "permanent"
                )
                steps.append(
                    ScriptedStep(
                        provider_error=code,
                        expect=expectation(),
                    )
                )
            else:
                raise ValueError(f"unsupported scripted entrypoint event: {event.type}")
        return tuple(steps)

    @classmethod
    def from_script_events(
        cls,
        events: Sequence[ScriptEvent],
        *,
        provider: str = "entrypoint-fixture",
        model: str = "entrypoint-fixture-v1",
    ) -> ScriptedLLM:
        """Replay entrypoint fixture events while requiring real feedback."""
        return cls(
            cls.script_steps(events),
            provider=provider,
            model=model,
        )

    def observation_summary(self) -> dict[str, int]:
        tool_results = 0
        for item in self.calls:
            try:
                tool_results += len(item.tool_results)
            except ScriptedObservationError:
                # Malformed feedback is already reported through
                # ``observation_failures``; keep the summary itself usable.
                continue
        return {
            "calls": len(self.calls),
            "history_messages": sum(len(item.messages) for item in self.calls),
            "tool_results": tool_results,
            "context_snapshots": sum(
                1 for item in self.calls if item.context is not None
            ),
            "expectations_verified": self._expectations_verified,
            "observation_failures": len(self.observation_failures),
        }

    def _verify_context_identity(self, observation: ScriptedObservation) -> None:
        context = observation.context
        if context is None:
            if observation.run_id is not None or observation.trace_id is not None:
                raise ScriptedObservationError(
                    "context: expected a Runtime context snapshot, observed none",
                    call_number=observation.call_number,
                )
            return
        if not isinstance(context, Mapping):
            raise ScriptedObservationError(
                f"context: expected an object, observed {_kind(context)}",
                call_number=observation.call_number,
            )
        if (
            observation.run_id is not None
            and context.get("run_id") != observation.run_id
        ):
            raise ScriptedObservationError(
                "context.run_id: expected "
                f"{_bounded(observation.run_id)}, "
                f"observed {_bounded(context.get('run_id'))}",
                call_number=observation.call_number,
            )
        if (
            observation.trace_id is not None
            and context.get("trace_id") != observation.trace_id
        ):
            raise ScriptedObservationError(
                "context.trace_id: expected "
                f"{_bounded(observation.trace_id)}, "
                f"observed {_bounded(context.get('trace_id'))}",
                call_number=observation.call_number,
            )

    async def infer(
        self,
        *,
        goal: str,
        messages: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
        run_id: str | None = None,
        trace_id: str | None = None,
        call_id: str | None = None,
        capability_catalog: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> ModelCallResult:
        del kwargs
        observation = ScriptedObservation(
            call_number=len(self.calls) + 1,
            goal=goal,
            messages=tuple(deepcopy(list(messages))),
            context=deepcopy(context),
            run_id=run_id,
            trace_id=trace_id,
            capability_catalog=tuple(deepcopy(list(capability_catalog or ()))),
        )
        self.calls.append(observation)
        index = observation.call_number - 1
        if index >= len(self.steps):
            message = "script exhausted; Runtime requested an unconfigured model call"
            self.observation_failures.append(message)
            raise ScriptedObservationError(
                message,
                call_number=observation.call_number,
            )
        step = self.steps[index]
        try:
            if self.verify_context_identity:
                self._verify_context_identity(observation)
            if step.expect is not None:
                failures = step.expect.verify(observation)
                if failures:
                    raise ScriptedObservationError(
                        f"step {index + 1}: " + "; ".join(failures),
                        call_number=observation.call_number,
                    )
                self._expectations_verified += 1
        except ScriptedObservationError as exc:
            self.observation_failures.append(exc.reason)
            raise

        call_fields: dict[str, Any] = {"call_id": call_id} if call_id else {}
        if step.provider_error is not None:
            return ModelCallResult(
                provider=self.provider,
                model=self.model,
                operation="infer",
                status="failed",
                error_code=cast(ProviderErrorCode, step.provider_error),
                trace_id=trace_id,
                **call_fields,
            )

        if step.decision is not None:
            try:
                raw = (
                    step.decision(observation)
                    if callable(step.decision)
                    else step.decision
                )
                if not isinstance(raw, Mapping):
                    raise ScriptedObservationError(
                        f"decision builder returned {_kind(raw)}, expected an object",
                        call_number=observation.call_number,
                    )
                decision = deepcopy(dict(raw))
                text = json.dumps(
                    decision,
                    ensure_ascii=False,
                    sort_keys=True,
                    default=str,
                )
            except ScriptedObservationError as exc:
                self.observation_failures.append(exc.reason)
                raise
            except Exception as exc:
                message = (
                    "decision builder failed: "
                    f"{type(exc).__name__}: {_bounded(str(exc))}"
                )
                self.observation_failures.append(message)
                raise ScriptedObservationError(
                    message,
                    call_number=observation.call_number,
                ) from exc
        else:
            decision = None
            text = step.text or ""

        return ModelCallResult(
            provider=self.provider,
            model=self.model,
            operation="infer",
            status="completed",
            text=text,
            decision=decision,
            trace_id=trace_id,
            **call_fields,
        )

    async def stream_infer(self, **kwargs: Any) -> AsyncIterator[ModelStreamEvent]:
        yield ModelStreamEvent(result=await self.infer(**kwargs))

    async def synthesize(self, **kwargs: Any) -> str:
        del kwargs
        raise AssertionError("ScriptedLLM must not synthesize")

    async def synthesize_result(self, **kwargs: Any) -> ModelCallResult:
        del kwargs
        raise AssertionError("ScriptedLLM must not synthesize")
