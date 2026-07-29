"""AgentRuntime-backed evaluation targets."""

from __future__ import annotations

import json
import os
import time
from typing import Any, AsyncIterator, Protocol

from app.agents.langgraph_adapter import LangGraphAdapter
from app.agents.graph import ChatWorkflow
from app.evaluation.types import EvalCase, ExecutionResult, ScriptEvent
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
) -> ExecutionResult:
    route = ""
    capabilities: list[str] = []
    text_parts: list[str] = []
    evidence: list[str] = []
    recovered = False
    latency_ms = 0.0
    call_count = 0
    structured: Any = None

    for event in events:
        event_type = event.get("type")
        if event_type == "route":
            route = str(event.get("route") or "")
        elif event_type == "tool_call_end":
            name = event.get("name")
            if name:
                capabilities.append(str(name))
            call_count += 1
            latency_ms += float(event.get("duration_ms") or 0)
            output = event.get("output")
            if isinstance(output, dict):
                raw_evidence = output.get("evidence", [])
                if isinstance(raw_evidence, list):
                    evidence.extend(str(item) for item in raw_evidence)
        elif event_type == "message_chunk":
            text_parts.append(str(event.get("content") or ""))
        elif event_type == "structured_response":
            structured = event.get("value")
        elif event_type == "recovery":
            recovered = event.get("status") == "recovered"

    text = "".join(text_parts)
    return ExecutionResult(
        route=route,
        capabilities=capabilities,
        text=text,
        evidence=evidence,
        schema_valid=_schema_valid(response_schema, text, structured),
        recovered=recovered,
        latency_ms=latency_ms,
        call_count=call_count,
    )


class OfflineOrchestrationAdapter:
    """Runs scripted provider events through the production LangGraph adapter."""

    def __init__(self) -> None:
        self.executed_event_count = 0

    async def run(self, state: AgentState) -> dict[str, Any]:
        raw_events = state.task.metadata["provider_events"]
        events = [ScriptEvent.model_validate(event) for event in raw_events]
        workflow = ScriptedProviderWorkflow(events)
        result = await LangGraphAdapter(workflow).execute(state.task)
        actual_events = result["all_events"]
        self.executed_event_count += len(actual_events)
        normalized = normalize_events(
            actual_events,
            response_schema=state.task.metadata["response_schema"],
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


class ProductionLangGraphTarget:
    """Network-backed target using the production ChatWorkflow and adapter."""

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
        workflow = ChatWorkflow(
            api_key=self._api_key,
            base_url=self._base_url,
            memory_manager=FixtureMemory(case),
            db_path=".runtime/evaluation/checkpoints.db",
        )
        adapter = LangGraphAdapter(workflow)
        task = AgentTask(
            user_id=case.user_fixture.user_id,
            goal=case.input_messages[-1].content,
            task_metadata={
                "model": self._model,
                "messages": [
                    message.model_dump() for message in case.input_messages
                ],
                "temperature": 0,
                "thread_id": f"eval-{case.id}",
            },
        )
        started = time.perf_counter()
        try:
            raw = await adapter.execute(task)
        finally:
            await workflow.close()
        duration_ms = (time.perf_counter() - started) * 1000
        return normalize_production_result(
            case,
            raw,
            duration_ms=duration_ms,
        )


def normalize_production_result(
    case: EvalCase,
    raw: dict[str, Any],
    *,
    duration_ms: float,
) -> ExecutionResult:
    """Normalize the actual LangGraphAdapter result into evaluation fields."""
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


def create_production_target(config) -> ProductionLangGraphTarget:
    return ProductionLangGraphTarget(config)
