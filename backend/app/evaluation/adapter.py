"""AgentRuntime-backed evaluation targets."""

from __future__ import annotations

import json
import os
import time
from typing import Any, AsyncIterator, Protocol

from app.capabilities.factory import build_capability_registry
from app.evaluation.types import EvalCase, ExecutionResult, ScriptEvent
from app.harness.budget import CancellationToken, RunBudget
from app.harness.contracts import ExecutionContext
from app.harness.dispatcher import Dispatcher
from app.harness.model_gateway import OpenAIModelGateway
from app.harness.runtime import AgentRuntime
from app.harness.state import AgentState
from app.harness.task import AgentTask
from app.memory.interfaces import MemoryContext


class EvaluationTarget(Protocol):
    async def evaluate(self, case: EvalCase) -> ExecutionResult:
        ...


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
    run_status = "completed"
    tool_call_count = 0
    tool_success_count = 0
    tool_failure_count = 0
    policy_denied_count = 0
    budget_exceeded_count = 0
    cancelled_count = 0
    reconnect_count = 0
    model_call_count = 0
    model_tokens = 0
    has_model_tokens = False
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
        output_tokens = usage.get(
            "completion_tokens", usage.get("output_tokens")
        )
        if isinstance(input_tokens, int) and isinstance(output_tokens, int):
            return input_tokens + output_tokens
        return None

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
            if status in {"success", "completed", "ok"}:
                tool_success_count += 1
            else:
                tool_failure_count += 1
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
        elif event_type == "model_call":
            model_call_count += 1
            append_unique(providers, event.get("provider"))
            append_unique(models, event.get("model"))
            tokens = usage_tokens(event.get("usage"))
            if tokens is not None:
                model_tokens += tokens
                has_model_tokens = True
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
        estimated_cost_usd=(
            estimated_cost_usd
            if model_call_count and estimated_cost_unknown_count == 0
            else None
        ),
        estimated_cost_unknown_count=estimated_cost_unknown_count,
        tool_argument_keys=sorted(tool_argument_keys),
        providers=providers,
        models=models,
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
                "messages": [
                    message.model_dump() for message in case.input_messages
                ],
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
            f"{fact['kind']} memory: {fact['content']}"
            for fact in self._facts
        )
        return MemoryContext(
            long_term_facts=list(self._facts),
            summary="\n".join(sections),
        )


class ProductionRuntimeTarget:
    """Network-backed target using the Runtime-owned Decision loop."""

    def __init__(self, config) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("production target credentials unavailable")
        self._api_key = api_key
        self._base_url = os.getenv(
            "OPENAI_BASE_URL",
            "https://api.openai.com/v1",
        )
        self._model = config.agent.model

    async def evaluate(self, case: EvalCase) -> ExecutionResult:
        gateway = OpenAIModelGateway(
            api_key=self._api_key,
            base_url=self._base_url,
            model=self._model,
            temperature=0,
        )
        registry = build_capability_registry()
        dispatcher = Dispatcher(registry)
        run_id = f"eval-{case.id}"
        context = ExecutionContext(
            principal_id=case.user_fixture.user_id,
            run_id=run_id,
            trace_id=run_id,
            thread_id=run_id,
            capability_allowlist=frozenset(
                definition.public_name
                for definition in registry.allowed_public_definitions()
            ),
        )
        task = AgentTask(
            user_id=case.user_fixture.user_id,
            goal=case.input_messages[-1].content,
            task_metadata={
                "model": self._model,
                "messages": [
                    message.model_dump() for message in case.input_messages
                ],
                "thread_id": run_id,
                "run_id": run_id,
            },
        )
        runtime = AgentRuntime(
            model_gateway=gateway,
            dispatcher=dispatcher,
            memory_context=await FixtureMemory(case).retrieve_context(
                run_id,
                task.goal,
            ),
        )
        started = time.perf_counter()
        try:
            events = [
                event
                async for event in runtime.stream_decision(
                    task,
                    context=context,
                    budget=RunBudget(),
                    cancellation=CancellationToken(),
                )
            ]
        finally:
            await gateway.close()
        duration_ms = (time.perf_counter() - started) * 1000
        normalized = normalize_events(
            events,
            response_schema=case.assertions.response_schema,
            run_id=run_id,
        )
        return normalized.model_copy(
            update={
                "route": classify_route(
                    events,
                    normalized.capabilities,
                    normalized.text,
                ),
                "latency_ms": duration_ms,
            }
        )


def normalize_production_result(
    case: EvalCase,
    raw: dict[str, Any],
    *,
    duration_ms: float,
) -> ExecutionResult:
    """Normalize a provider-neutral Runtime result into evaluation fields."""
    capabilities = [
        str(call.get("name"))
        for call in raw["tool_calls"]
        if call.get("name")
    ]
    route = classify_route(
        raw["all_events"],
        capabilities,
        raw["text"],
    )
    evidence: list[str] = []
    for call in raw["tool_calls"]:
        output = call.get("output")
        if isinstance(output, dict) and isinstance(
            output.get("evidence"), list
        ):
            evidence.extend(str(item) for item in output["evidence"])
    had_error = any(
        event.get("type") == "error" for event in raw["all_events"]
    )
    return ExecutionResult(
        route=route,
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


def create_production_target(config) -> ProductionRuntimeTarget:
    return ProductionRuntimeTarget(config)
