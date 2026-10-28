"""AgentRuntime-backed evaluation targets."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
from typing import Any, AsyncIterator, Literal, Protocol, Sequence
from uuid import uuid4

from app.capabilities.factory import build_capability_registry
from app.evaluation.controlled import (
    controlled_allowed_capabilities,
    controlled_external_responses,
    validate_controlled_capabilities,
)
from app.evaluation.types import EvalCase, ExecutionResult, ScriptEvent, ToolErrorSample
from app.evaluation.transcript import transcript_path
from app.agents.provider_endpoint import (
    ProviderEndpointPolicy,
    is_local_endpoint,
    make_provider_endpoint_policy,
    parse_provider_allowlists,
    resolve_provider_base_url,
)
from app.harness.model_gateway import OpenAIModelGateway
from app.harness.runtime import AgentRuntime
from app.harness.state import AgentState
from app.harness.task import AgentTask
from app.memory.interfaces import MemoryContext


class EvaluationTarget(Protocol):
    async def evaluate(self, case: EvalCase) -> ExecutionResult: ...


class ProviderCredentialsUnavailable(RuntimeError):
    """The live provider cannot be used without a trusted credential."""


class ScriptedProviderWorkflow:
    """Offline provider/tool double speaking the production workflow event contract."""

    def __init__(self, events: list[ScriptEvent]) -> None:
        self._events = events

    async def stream_chat(self, **_: Any) -> AsyncIterator[dict[str, Any]]:
        for event in self._events:
            if event.type == "provider_error":
                raise RuntimeError(event.code or "provider_error")
            yield event.model_dump(exclude_none=True)


def _schema_valid(schema: str, text: str, structured: Any) -> bool:
    if schema == "text":
        return bool(text.strip())
    if schema == "recommendation_list":
        return isinstance(structured, list) and bool(structured)
    return structured is not None


def _terminal_metadata(event: dict[str, Any]) -> tuple[str | None, str | None]:
    error_code = event.get("error_code")
    reason = event.get("termination_reason")
    return (
        str(error_code) if error_code is not None else None,
        str(reason) if reason is not None else None,
    )


def _partial_result_from_transcript(
    case: EvalCase,
    transcript_dir: str | Path | None,
) -> ExecutionResult | None:
    """Recover measured Runtime evidence when validation fails after execution.

    The headless entrypoint writes a redacted transcript before propagating a
    post-Run validation error. Preserve its observed route, calls, usage, and
    latency while ensuring an incomplete evaluation can never pass.
    """
    if transcript_dir is None:
        return None
    path = transcript_path(transcript_dir, case.id)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or payload.get("case_id") != case.id:
            return None
        raw_result = payload.get("result")
        if not isinstance(raw_result, dict):
            return None
        result = ExecutionResult.model_validate(raw_result)
    except (OSError, TypeError, ValueError):
        return None

    trace = payload.get("trace")
    trace_duration = trace.get("total_duration_ms") if isinstance(trace, dict) else None
    latency_ms = result.latency_ms
    if (
        latency_ms <= 0
        and isinstance(trace_duration, (int, float))
        and math.isfinite(float(trace_duration))
        and trace_duration >= 0
    ):
        latency_ms = float(trace_duration)
    return result.model_copy(
        update={
            "run_id": result.run_id or payload.get("run_id"),
            "trace_id": result.trace_id or payload.get("trace_id") or result.run_id,
            "run_status": "failed",
            "terminal_error_code": result.terminal_error_code or "evaluation_error",
            "benchmark_status": "ERROR",
            "task_success": False,
            "latency_ms": latency_ms,
        }
    )


def normalize_events(
    events: list[dict[str, Any]],
    *,
    response_schema: str,
    run_id: str | None = None,
) -> ExecutionResult:
    route = ""
    capabilities: list[str] = []
    text_parts: list[str] = []
    evidence: list[str] = []
    recovered = False
    latency_ms = 0.0
    structured: Any = None
    run_status: Literal["completed", "failed", "cancelled", "timeout"] = "completed"
    tool_call_count = 0
    tool_success_count = 0
    tool_failure_count = 0
    policy_denied_count = 0
    budget_exceeded_count = 0
    cancelled_count = 0
    reconnect_count = 0
    model_call_count = 0
    model_tokens = 0
    model_prompt_tokens = 0
    model_completion_tokens = 0
    has_model_tokens = False
    has_prompt_tokens = False
    has_completion_tokens = False
    step_count = 0
    terminal_error_code: str | None = None
    provider_failure: dict[str, Any] | None = None
    termination_reason: str | None = None
    tool_errors: list[ToolErrorSample] = []
    estimated_cost_usd = 0.0
    estimated_cost_unknown_count = 0
    tool_argument_keys: set[str] = set()
    providers: list[str] = []
    models: list[str] = []
    open_tools: set[str] = set()

    def append_unique(values: list[str], value: Any) -> None:
        if value and str(value) not in values:
            values.append(str(value))

    def event_tool_key(event: dict[str, Any], index: int) -> str:
        return str(
            event.get("invocation_id")
            or event.get("id")
            or f"{event.get('name') or event.get('capability', 'unknown')}:{index}"
        )

    def usage_tokens(usage: Any) -> int | None:
        if not isinstance(usage, dict):
            return None
        total = usage.get("total_tokens")
        if isinstance(total, int) and total >= 0:
            return total
        input_tokens = usage.get("prompt_tokens", usage.get("input_tokens"))
        output_tokens = usage.get("completion_tokens", usage.get("output_tokens"))
        if isinstance(input_tokens, int) and isinstance(output_tokens, int):
            return input_tokens + output_tokens
        return None

    def usage_parts(usage: Any) -> tuple[int | None, int | None]:
        if not isinstance(usage, dict):
            return None, None
        prompt = usage.get("prompt_tokens", usage.get("input_tokens"))
        completion = usage.get("completion_tokens", usage.get("output_tokens"))
        return (
            prompt if isinstance(prompt, int) and prompt >= 0 else None,
            completion if isinstance(completion, int) and completion >= 0 else None,
        )

    for index, event in enumerate(events):
        event_type = event.get("type")
        if event_type == "route":
            route = str(event.get("route") or "")
        elif event_type == "tool_call_start":
            tool_key = event_tool_key(event, index)
            if tool_key not in open_tools:
                tool_call_count += 1
                open_tools.add(tool_key)
            arguments = event.get("arguments", event.get("inputs"))
            if isinstance(arguments, dict):
                tool_argument_keys.update(str(key) for key in arguments)
            elif isinstance(event.get("argument_keys"), list):
                tool_argument_keys.update(str(key) for key in event["argument_keys"])
        elif event_type == "tool_call_end":
            name = event.get("name") or event.get("capability")
            if name:
                append_unique(capabilities, name)
            tool_key = event_tool_key(event, index)
            if tool_key not in open_tools:
                tool_call_count += 1
            else:
                open_tools.remove(tool_key)
            status = str(event.get("status") or "success").lower()
            if status in {"success", "succeeded", "completed", "ok"}:
                tool_success_count += 1
            else:
                tool_failure_count += 1
                if status in {"denied", "policy_denied"}:
                    policy_denied_count += 1
                raw_error = event.get("error_code")
                raw_output = event.get("output")
                if raw_error is None and isinstance(raw_output, dict):
                    raw_error = raw_output.get("error_type") or raw_output.get(
                        "error_code"
                    )
                tool_errors.append(
                    ToolErrorSample(
                        capability=str(name or "unknown"),
                        error_code=(str(raw_error) if raw_error is not None else None),
                        status=status,
                    )
                )
            latency_ms += float(event.get("duration_ms") or 0)
            arguments = event.get("arguments", event.get("inputs"))
            if isinstance(arguments, dict):
                tool_argument_keys.update(str(key) for key in arguments)
            elif isinstance(event.get("argument_keys"), list):
                tool_argument_keys.update(str(key) for key in event["argument_keys"])
            output = event.get("output")
            if isinstance(output, dict):
                raw_evidence = output.get("evidence", [])
                if isinstance(raw_evidence, list):
                    evidence.extend(str(item) for item in raw_evidence)
        elif event_type == "policy_denied":
            policy_denied_count += 1
        elif event_type == "budget_exceeded":
            budget_exceeded_count += 1
            run_status = "failed"
        elif event_type == "timeout":
            run_status = "timeout"
            latency_ms += float(event.get("duration_ms") or 0)
        elif event_type == "cancelled":
            cancelled_count += 1
            run_status = "cancelled"
        elif event_type == "reconnect":
            reconnect_count += 1
        elif event_type == "provider_error":
            run_status = "failed"
            terminal_error_code = event.get("code")
        elif event_type == "run_completed":
            run_status = "completed"
            terminal_error_code, termination_reason = _terminal_metadata(event)
        elif event_type == "run_failed":
            run_status = "failed"
            terminal_error_code, termination_reason = _terminal_metadata(event)
        elif event_type == "run_cancelled":
            cancelled_count += 1
            run_status = "cancelled"
            terminal_error_code, termination_reason = _terminal_metadata(event)
        elif event_type == "run_timeout":
            run_status = "timeout"
            latency_ms += float(event.get("duration_ms") or 0)
            terminal_error_code, termination_reason = _terminal_metadata(event)
        elif event_type == "model_decision":
            step_count += 1
        elif event_type == "model_call":
            model_call_count += 1
            raw_provider_failure = event.get("provider_failure")
            if isinstance(raw_provider_failure, dict):
                provider_failure = raw_provider_failure
            append_unique(providers, event.get("provider"))
            append_unique(models, event.get("model"))
            tokens = usage_tokens(event.get("usage"))
            if tokens is not None:
                model_tokens += tokens
                has_model_tokens = True
            prompt_tokens, completion_tokens = usage_parts(event.get("usage"))
            if prompt_tokens is not None:
                model_prompt_tokens += prompt_tokens
                has_prompt_tokens = True
            if completion_tokens is not None:
                model_completion_tokens += completion_tokens
                has_completion_tokens = True
            cost = event.get("estimated_cost_usd")
            if isinstance(cost, (int, float)):
                estimated_cost_usd += float(cost)
            else:
                estimated_cost_unknown_count += 1
            latency_ms += float(event.get("duration_ms") or 0)
        elif event_type == "message_chunk":
            text_parts.append(str(event.get("content") or ""))
        elif event_type == "structured_response":
            structured = event.get("value")
        elif event_type == "recovery":
            recovered = event.get("status") == "recovered"
            if recovered and run_status == "failed":
                run_status = "completed"

    if open_tools:
        tool_failure_count += len(open_tools)

    # Observational recovery: a completed Run that previously observed tool
    # failures demonstrates recovery even when the Runtime emits no explicit
    # recovery event. An explicit recovery event still wins when present.
    if run_status == "completed" and tool_failure_count:
        recovered = True

    text = "".join(text_parts)
    return ExecutionResult(
        route=route,
        capabilities=capabilities,
        text=text,
        evidence=evidence,
        schema_valid=_schema_valid(response_schema, text, structured),
        recovered=recovered,
        latency_ms=latency_ms,
        call_count=tool_call_count,
        run_id=run_id,
        run_status=run_status,
        tool_call_count=tool_call_count,
        tool_success_count=tool_success_count,
        tool_failure_count=tool_failure_count,
        policy_denied_count=policy_denied_count,
        budget_exceeded_count=budget_exceeded_count,
        cancelled_count=cancelled_count,
        reconnect_count=reconnect_count,
        model_call_count=model_call_count,
        model_tokens=model_tokens if has_model_tokens else None,
        prompt_tokens=model_prompt_tokens if has_prompt_tokens else None,
        completion_tokens=(model_completion_tokens if has_completion_tokens else None),
        estimated_cost_usd=(
            estimated_cost_usd
            if model_call_count and estimated_cost_unknown_count == 0
            else None
        ),
        estimated_cost_unknown_count=estimated_cost_unknown_count,
        tool_argument_keys=sorted(tool_argument_keys),
        providers=providers,
        models=models,
        terminal_error_code=terminal_error_code,
        provider_failure=provider_failure,
        termination_reason=termination_reason,
        step_count=step_count,
        tool_errors=tool_errors,
    )


class OfflineOrchestrationAdapter:
    """Runs fixture events through the production Runtime boundary."""

    def __init__(self) -> None:
        self.executed_event_count = 0

    async def run(self, state: AgentState) -> dict[str, Any]:
        raw_events = state.task.metadata["provider_events"]
        events = [ScriptEvent.model_validate(event) for event in raw_events]
        actual_events = [event.model_dump(exclude_none=True) for event in events]
        self.executed_event_count += len(actual_events)
        normalized = normalize_events(
            actual_events,
            response_schema=state.task.metadata["response_schema"],
            run_id=str(state.task.metadata["run_id"]),
        )
        return normalized.model_dump()


class RuntimeEvaluationTarget:
    def __init__(self, adapter=None) -> None:
        self._adapter = adapter or OfflineOrchestrationAdapter()
        self.runtime = AgentRuntime(self._adapter)

    @property
    def executed_event_count(self) -> int:
        return getattr(self._adapter, "executed_event_count", 0)

    async def evaluate(self, case: EvalCase) -> ExecutionResult:
        task = AgentTask(
            user_id=case.user_fixture.user_id,
            goal=case.input_messages[-1].content,
            task_metadata={
                "evaluation_case_id": case.id,
                "provider_events": [
                    event.model_dump() for event in case.fixtures.events
                ],
                "response_schema": case.assertions.response_schema,
                "messages": [message.model_dump() for message in case.input_messages],
                "memory_fixtures": [
                    fixture.model_dump() for fixture in case.memory_fixtures
                ],
                "run_id": f"eval-{case.id}",
            },
        )
        state = await self.runtime.execute(task)
        return ExecutionResult.model_validate(state.result)


def create_offline_target(_config=None) -> RuntimeEvaluationTarget:
    return RuntimeEvaluationTarget()


class FixtureMemory:
    """Case-scoped, read-only memory exposed to the production workflow."""

    def __init__(self, case: EvalCase) -> None:
        self._facts = [
            {
                "kind": fixture.kind,
                "content": fixture.content,
                "thread_id": fixture.thread_id,
            }
            for fixture in case.memory_fixtures
        ]
        self._attributes = case.user_fixture.attributes

    async def retrieve_context(
        self,
        _thread_id: str,
        _query: str,
        *_args: Any,
        **_kwargs: Any,
    ) -> MemoryContext:
        sections: list[str] = []
        if self._attributes:
            sections.append(
                "User attributes: "
                + json.dumps(
                    self._attributes,
                    ensure_ascii=False,
                    sort_keys=True,
                )
            )
        sections.extend(
            f"{fact['kind']} memory: {fact['content']}" for fact in self._facts
        )
        return MemoryContext(
            long_term_facts=list(self._facts),
            summary="\n".join(sections),
        )


class ProductionRuntimeTarget:
    """Network-backed target using the Runtime-owned Decision loop.

    Each case goes through the shared headless entrypoint
    (``run_headless_case``), which composes ``build_runtime`` with the
    production CapabilityRegistry, Dispatcher and SQL Run/Event/Trace stores.
    This class only selects the live model gateway; it never executes
    Decisions or capabilities itself.
    """

    def __init__(
        self,
        config,
        *,
        model: str | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
        transcript_dir: str | Path | None = None,
        temperature: float = 0,
        allowed_public_names: Sequence[str] | None = None,
        external_fixtures: str | None = None,
        deepseek_options: dict[str, Any] | None = None,
        anime_benchmark_suite: Any | None = None,
    ) -> None:
        routing = getattr(config, "routing", None)
        self._routing_enabled = bool(getattr(routing, "enabled", False))
        self._routing_version = str(getattr(routing, "version", "keyword-v1"))
        if self._routing_enabled and self._routing_version not in {
            "keyword-v1",
            "model-v1",
        }:
            raise ValueError(
                f"unsupported specialist router version: {self._routing_version}"
            )
        self._api_key = _configured_api_key(api_key)
        self._endpoint_policy = _provider_endpoint_policy()
        self._base_url = resolve_provider_base_url(
            _configured_base_url(base_url),
            policy=self._endpoint_policy,
        )
        self._model = model or config.agent.model
        self._temperature = temperature
        self._deepseek_options = deepseek_options
        self._transcript_dir = (
            transcript_dir if transcript_dir is not None else config.transcript_dir
        )
        self._external_fixtures = external_fixtures
        self._anime_benchmark_suite = anime_benchmark_suite
        self._runtime_budget = getattr(config, "runtime_budget", None)
        self._allowed_public_names: frozenset[str] | None
        if external_fixtures is not None:
            if allowed_public_names is None:
                allowed_public_names = sorted(
                    controlled_allowed_capabilities(external_fixtures)
                )
            self._allowed_public_names = validate_controlled_capabilities(
                external_fixtures,
                allowed_public_names,
            )
        else:
            self._allowed_public_names = (
                frozenset(allowed_public_names)
                if allowed_public_names is not None
                else None
            )
        if not self._api_key and not _local_endpoint_without_key(self._base_url):
            raise ProviderCredentialsUnavailable(
                "production target credentials unavailable"
            )

    async def evaluate(self, case: EvalCase) -> ExecutionResult:
        from app.evaluation.entrypoint import run_headless_case
        from app.harness.budget import RunBudget

        registry = build_capability_registry()
        gateway = OpenAIModelGateway(
            api_key=self._api_key,
            base_url=self._base_url,
            model=self._model,
            temperature=self._temperature,
            deepseek_options=self._deepseek_options,
            endpoint_policy=self._endpoint_policy,
        )
        try:
            scenario = (
                self._anime_benchmark_suite.case_by_id(case.id.split("__r", 1)[0])
                if self._anime_benchmark_suite is not None
                else None
            )
            with controlled_external_responses(
                self._external_fixtures,
                anime_fixture_set=(
                    self._anime_benchmark_suite.fixture_set
                    if scenario is not None
                    else None
                ),
                tool_faults=(scenario.tool_faults if scenario is not None else ()),
            ) as controlled_search:
                session_setup = None
                case_observer = None
                if scenario is not None:
                    from app.evaluation.anime_scoring import (
                        evaluate_anime_hard_checks,
                        seed_and_snapshot,
                    )

                    fixture_set = self._anime_benchmark_suite.fixture_set

                    async def _setup(session, user_id):
                        return await seed_and_snapshot(session, user_id, fixture_set)

                    async def _observe(
                        session,
                        user_id,
                        before,
                        result,
                        events,
                    ):
                        return await evaluate_anime_hard_checks(
                            session,
                            user_id,
                            before,
                            result,
                            events,
                            scenario=scenario,
                            fixture_set=fixture_set,
                            allowed_public_names=(self._allowed_public_names or ()),
                            triggered_faults=(
                                controlled_search.triggered_faults
                                if controlled_search is not None
                                else ()
                            ),
                            successful_search_subject_ids_after_fault=(
                                controlled_search.successful_search_subject_ids_after_fault
                                if controlled_search is not None
                                else ()
                            ),
                        )

                    session_setup = _setup
                    case_observer = _observe

                allowed_public_names = self._allowed_public_names
                if allowed_public_names is not None:
                    available = {
                        definition.public_name
                        for definition in registry.allowed_public_definitions(
                            include_side_effects=bool(case.approvals)
                        )
                    }
                    allowed_public_names = allowed_public_names & available
                run_budget = None
                if self._runtime_budget is not None:
                    budget_values = self._runtime_budget.model_dump(mode="python")
                    budget_values["max_tool_calls"] = min(
                        int(budget_values["max_tool_calls"]),
                        case.assertions.max_calls,
                    )
                    run_budget = RunBudget(**budget_values)
                try:
                    result, _events = await run_headless_case(
                        case,
                        registry=registry,
                        model_gateway=gateway,
                        model=self._model,
                        fail_on_run_failure=False,
                        transcript_dir=self._transcript_dir,
                        allowed_public_names=allowed_public_names,
                        routing_enabled=self._routing_enabled,
                        routing_version=self._routing_version,
                        session_setup=session_setup,
                        case_observer=case_observer,
                        approvals=case.approvals,
                        run_budget=run_budget,
                        run_id=(
                            f"anime-{uuid4().hex}" if scenario is not None else None
                        ),
                    )
                except Exception:
                    result = _partial_result_from_transcript(
                        case,
                        self._transcript_dir,
                    )
                    if result is None:
                        raise
        finally:
            await gateway.close()
        return result


def _provider_endpoint_policy() -> ProviderEndpointPolicy:
    from app.core.config import settings

    allowed_hosts, allowed_ports = parse_provider_allowlists(
        settings.PROVIDER_ALLOWED_HOSTS,
        settings.PROVIDER_ALLOWED_PORTS,
    )
    return make_provider_endpoint_policy(
        deploy_mode=settings.DEPLOY_MODE,
        resolve_dns=settings.PROVIDER_RESOLVE_DNS,
        allowed_hosts=allowed_hosts,
        allowed_ports=allowed_ports,
    )


def _configured_api_key(explicit: str | None) -> str | None:
    """Resolve the live provider key without accepting it as a model argument.

    Explicit callers win. A process variable, when present, also wins over the
    application's dotenv settings: an explicitly empty value means "no key" so
    tests and CI cannot silently pick up a developer's local ``backend/.env``.
    """
    if explicit is not None:
        return explicit or None
    env_value = os.getenv("OPENAI_API_KEY")
    if env_value is not None:
        return env_value or None
    from app.core.config import settings

    return settings.OPENAI_API_KEY or None


def _configured_base_url(explicit: str | None) -> str | None:
    """Resolve the provider endpoint with the same env-over-dotenv precedence."""
    if explicit:
        return explicit
    env_value = os.getenv("OPENAI_BASE_URL")
    if env_value is not None:
        return env_value or None
    from app.core.config import settings

    return settings.OPENAI_BASE_URL or None


def _local_endpoint_without_key(base_url: str) -> bool:
    from app.core.config import settings

    return settings.DEPLOY_MODE == "local" and is_local_endpoint(base_url)


def normalize_production_result(
    case: EvalCase,
    raw: dict[str, Any],
    *,
    duration_ms: float,
) -> ExecutionResult:
    """Normalize a provider-neutral Runtime result into evaluation fields."""
    capabilities = [
        str(call.get("name")) for call in raw["tool_calls"] if call.get("name")
    ]
    route = classify_route(
        raw["all_events"],
        capabilities,
        raw["text"],
    )
    route_agent, route_observed = route_agent_evidence(raw["all_events"])
    evidence: list[str] = []
    for call in raw["tool_calls"]:
        output = call.get("output")
        if isinstance(output, dict) and isinstance(output.get("evidence"), list):
            evidence.extend(str(item) for item in output["evidence"])
    had_error = any(event.get("type") == "error" for event in raw["all_events"])
    return ExecutionResult(
        route=route,
        route_agent=route_agent,
        route_observed=route_observed,
        capabilities=capabilities,
        text=raw["text"],
        evidence=evidence,
        schema_valid=_schema_valid(
            case.assertions.response_schema,
            raw["text"],
            None,
        ),
        recovered=had_error and bool(raw["text"]),
        latency_ms=duration_ms,
        call_count=len(capabilities),
    )


def classify_route(
    events: list[dict[str, Any]],
    capabilities: list[str],
    response_text: str,
) -> str:
    route_decision = next(
        (event for event in events if event.get("type") == "route_decision"),
        None,
    )
    if route_decision is not None:
        if route_decision.get("agent") == "fallback":
            return "chat"
        if route_decision.get("route"):
            return str(route_decision["route"])
    explicit = next(
        (
            event.get("route")
            for event in events
            if event.get("type") == "route" and event.get("route")
        ),
        None,
    )
    if explicit:
        return str(explicit)
    if any("schedule" in name for name in capabilities):
        return "schedule"
    if any(
        name
        in {
            "generate_profile",
            "generate_user_profile_tool",
            "analyse_taste",
        }
        for name in capabilities
    ):
        return "recommendation"
    if any("media" in name for name in capabilities):
        return "media"
    refusal_markers = (
        "cannot",
        "can't",
        "won't",
        "unable to",
        "不能",
        "无法",
        "不会提供",
    )
    lowered = response_text.lower()
    if not capabilities and any(marker in lowered for marker in refusal_markers):
        return "refusal"
    return "chat"


def route_agent_evidence(events: list[dict[str, Any]]) -> tuple[str | None, bool]:
    """Return the selected agent only when a Runtime route event was observed."""
    route_decision = next(
        (event for event in events if event.get("type") == "route_decision"),
        None,
    )
    if route_decision is None:
        return None, False
    agent = route_decision.get("agent")
    return (str(agent) if isinstance(agent, str) and agent else None, True)


def create_production_target(config) -> ProductionRuntimeTarget:
    controlled = getattr(config, "controlled", None)
    deepseek = getattr(config, "deepseek", None)
    return ProductionRuntimeTarget(
        config,
        allowed_public_names=(
            controlled.allowed_capabilities if controlled is not None else None
        ),
        external_fixtures=(
            controlled.external_fixtures if controlled is not None else None
        ),
        deepseek_options=(
            deepseek.model_dump(mode="json") if deepseek is not None else None
        ),
    )
