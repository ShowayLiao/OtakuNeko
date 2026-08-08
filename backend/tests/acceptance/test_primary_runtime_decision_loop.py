"""Acceptance contracts for the Runtime-owned primary Decision Loop."""

from __future__ import annotations

import pytest

from app.capabilities.registry import CapabilityRegistry
from app.capabilities.types import ActionDescriptor, CapabilityResult
from app.harness.budget import CancellationToken, RunBudget
from app.harness.contracts import ErrorCode, ExecutionContext, InvocationResult
from app.harness.dispatcher import Dispatcher
from app.harness.model_types import ModelCallResult
from app.harness.runtime import AgentRuntime
from app.harness.task import AgentTask
from app.memory.interfaces import MemoryContext
from app.memory.types import MemoryFact, MemorySourceType


class _CatalogCapability:
    name = "catalog"

    def __init__(self) -> None:
        self.calls: list[dict] = []

    def actions(self):
        return [
            ActionDescriptor(
                name="search",
                public_name="catalog.search",
                description="Read catalog data",
                input_schema={"type": "object"},
            )
        ]

    async def execute(self, action: str, **kwargs):
        self.calls.append({"action": action, **kwargs})
        return CapabilityResult.ok(items=["anime-a"]).to_dict()


class _DecisionGateway:
    def __init__(self, decisions: list[dict]) -> None:
        self.decisions = iter(decisions)
        self.calls: list[dict] = []

    async def infer(self, **kwargs) -> ModelCallResult:
        self.calls.append(kwargs)
        return ModelCallResult(
            provider="fake",
            model="fake-model",
            operation="infer",
            status="completed",
            decision=next(self.decisions),
        )


class _TerminalDispatcher:
    def __init__(self, result: InvocationResult) -> None:
        self.result = result
        self.calls = 0

    async def dispatch(self, decision, context, **kwargs) -> InvocationResult:
        self.calls += 1
        return self.result


class _ModelResultGateway:
    def __init__(self, result: ModelCallResult) -> None:
        self.result = result
        self.calls = 0

    async def infer(self, **kwargs) -> ModelCallResult:
        self.calls += 1
        return self.result


class _ControlObservingGateway:
    def __init__(self, result: ModelCallResult) -> None:
        self.result = result
        self.calls: list[dict] = []

    async def infer(self, **kwargs) -> ModelCallResult:
        self.calls.append(kwargs)
        return self.result


class _MemoryChildService:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    async def extract_and_store_facts(self, thread_id, user_id=None, **kwargs):
        self.calls.append(
            {
                "thread_id": thread_id,
                "user_id": user_id,
                **kwargs,
            }
        )
        self.last_model_call = ModelCallResult(
            provider="fake",
            model="fake-memory-model",
            operation="memory.fact_extraction",
            call_id=kwargs["call_id"],
            trace_id=kwargs["trace_id"],
            status="completed",
        )
        return 0


@pytest.mark.asyncio
async def test_primary_runtime_loop_owns_decision_dispatch_and_terminal_result() -> None:
    capability = _CatalogCapability()
    registry = CapabilityRegistry()
    registry.register(capability)
    gateway = _DecisionGateway(
        [
            {
                "schema_version": "v1",
                "decision_id": "decision-1",
                "run_id": "run-primary-loop",
                "action": "invoke",
                "capability": "catalog.search",
                "capability_version": "v1",
                "arguments": {"query": "anime"},
            },
            {
                "schema_version": "v1",
                "decision_id": "decision-2",
                "run_id": "run-primary-loop",
                "action": "respond",
                "content": "found anime-a",
            },
        ]
    )
    runtime = AgentRuntime(
        object(),
        model_gateway=gateway,
        dispatcher=Dispatcher(registry),
    )

    events = [
        event
        async for event in runtime.stream_decision(
            AgentTask(
                task_id=101,
                user_id=7,
                goal="find anime",
                metadata={"run_id": "run-primary-loop", "messages": []},
            ),
            context=ExecutionContext(
                principal_id=7,
                run_id="run-primary-loop",
                trace_id="trace-primary-loop",
                capability_allowlist=frozenset({"catalog.search"}),
            ),
        )
    ]

    assert events[-1]["type"] == "run_completed"
    assert events[-1]["content"] == "found anime-a"
    assert capability.calls == [{"action": "search", "query": "anime"}]
    assert len(gateway.calls) == 2
    assert all(call["run_id"] == "run-primary-loop" for call in gateway.calls)
    assert [event["type"] for event in events].count("tool_call_end") == 1


@pytest.mark.asyncio
async def test_primary_runtime_passes_memory_only_through_context_snapshot() -> None:
    gateway = _DecisionGateway(
        [
            {
                "schema_version": "v1",
                "decision_id": "decision-memory",
                "run_id": "run-memory",
                "action": "respond",
                "content": "safe response",
            }
        ]
    )
    runtime = AgentRuntime(
        object(),
        model_gateway=gateway,
        dispatcher=Dispatcher(CapabilityRegistry()),
        memory_context=MemoryContext(
            memory_facts=[
                MemoryFact(
                    content="user likes science fiction",
                    source_type=MemorySourceType.USER,
                    source_id="fact-1",
                    user_id=7,
                    verified=True,
                    confidence=0.9,
                )
            ]
        ),
    )

    events = [
        event
        async for event in runtime.stream_decision(
            AgentTask(
                task_id=102,
                user_id=7,
                goal="say hello",
                metadata={"run_id": "run-memory", "messages": []},
            ),
            context=ExecutionContext(
                principal_id=7,
                run_id="run-memory",
                trace_id="trace-memory",
            ),
        )
    ]

    snapshot = gateway.calls[0]["context"]
    assert events[-1]["type"] == "run_completed"
    assert snapshot["memory"][0]["content"] == "user likes science fiction"
    assert snapshot["memory"][0]["trusted"] is True
    assert "user_id" not in str(snapshot)
    assert "principal_id" not in str(snapshot)


@pytest.mark.asyncio
async def test_primary_runtime_runs_memory_extraction_as_a_child_model_call() -> None:
    gateway = _DecisionGateway(
        [
            {
                "schema_version": "v1",
                "decision_id": "decision-memory-child",
                "run_id": "run-memory-child",
                "action": "respond",
                "content": "safe response",
            }
        ]
    )
    memory = _MemoryChildService()
    runtime = AgentRuntime(
        object(),
        model_gateway=gateway,
        dispatcher=Dispatcher(CapabilityRegistry()),
        memory_service=memory,
    )

    events = [
        event
        async for event in runtime.stream_decision(
            AgentTask(
                task_id=108,
                user_id=7,
                goal="remember this",
                metadata={
                    "run_id": "run-memory-child",
                    "thread_id": "thread-memory-child",
                    "messages": [{"role": "user", "content": "I like sci-fi"}],
                },
            ),
            context=ExecutionContext(
                principal_id=7,
                run_id="run-memory-child",
                trace_id="trace-memory-child",
            ),
        )
    ]

    memory_events = [
        event
        for event in events
        if event["type"] == "model_call"
        and event.get("operation") == "memory.fact_extraction"
    ]
    assert len(memory_events) == 1
    assert memory_events[0]["operation"] == "memory.fact_extraction"
    assert memory_events[0]["call_id"] == memory.calls[0]["call_id"]
    assert events.index(memory_events[0]) < events.index(events[-1])
    assert memory.calls[0]["run_id"] == "run-memory-child"
    assert memory.calls[0]["trace_id"] == "trace-memory-child"


@pytest.mark.asyncio
async def test_primary_runtime_loop_stops_before_model_on_cancellation() -> None:
    gateway = _DecisionGateway([])
    runtime = AgentRuntime(
        object(),
        model_gateway=gateway,
        dispatcher=Dispatcher(CapabilityRegistry()),
    )
    cancellation = CancellationToken()
    cancellation.cancel()

    events = [
        event
        async for event in runtime.stream_decision(
            AgentTask(
                task_id=102,
                user_id=7,
                goal="cancel",
                metadata={"run_id": "run-cancel-before-model", "messages": []},
            ),
            cancellation=cancellation,
        )
    ]

    assert events[-1]["type"] == "run_cancelled"
    assert events[-1]["error_code"] == ErrorCode.CANCELLED.value
    assert gateway.calls == []


@pytest.mark.asyncio
async def test_primary_runtime_loop_preserves_dispatcher_timeout_code() -> None:
    gateway = _DecisionGateway(
        [
            {
                "schema_version": "v1",
                "decision_id": "decision-timeout",
                "run_id": "run-timeout",
                "action": "invoke",
                "capability": "catalog.search",
                "capability_version": "v1",
                "arguments": {},
            }
        ]
    )
    runtime = AgentRuntime(
        object(),
        model_gateway=gateway,
        dispatcher=_TerminalDispatcher(
            InvocationResult(
                invocation_id="inv-timeout",
                status="timeout",
                error_code="timeout",
            )
        ),
    )

    events = [
        event
        async for event in runtime.stream_decision(
            AgentTask(
                task_id=103,
                user_id=7,
                goal="timeout",
                metadata={"run_id": "run-timeout", "messages": []},
            )
        )
    ]

    assert events[-1]["type"] == "run_timeout"
    assert events[-1]["error_code"] == ErrorCode.TIMEOUT.value


@pytest.mark.asyncio
async def test_primary_runtime_maps_cancelled_model_result_without_parsing_or_dispatching() -> None:
    gateway = _ModelResultGateway(
        ModelCallResult(
            provider="fake",
            model="fake-model",
            operation="infer",
            status="cancelled",
            error_code="cancelled",
        )
    )
    dispatcher = _TerminalDispatcher(
        InvocationResult(invocation_id="unused", status="succeeded")
    )
    runtime = AgentRuntime(object(), model_gateway=gateway, dispatcher=dispatcher)

    events = [
        event
        async for event in runtime.stream_decision(
            AgentTask(
                task_id=105,
                user_id=7,
                goal="cancel in provider",
                metadata={"run_id": "run-model-cancel", "messages": []},
            )
        )
    ]

    assert events[-1]["type"] == "run_cancelled"
    assert events[-1]["error_code"] == ErrorCode.CANCELLED.value
    assert gateway.calls == 1
    assert dispatcher.calls == 0


@pytest.mark.asyncio
async def test_primary_runtime_maps_provider_timeout_without_next_decision() -> None:
    gateway = _ModelResultGateway(
        ModelCallResult(
            provider="fake",
            model="fake-model",
            operation="infer",
            status="failed",
            error_code="timeout",
            retryable=True,
        )
    )
    dispatcher = _TerminalDispatcher(
        InvocationResult(invocation_id="unused", status="succeeded")
    )
    runtime = AgentRuntime(object(), model_gateway=gateway, dispatcher=dispatcher)

    events = [
        event
        async for event in runtime.stream_decision(
            AgentTask(
                task_id=106,
                user_id=7,
                goal="provider timeout",
                metadata={"run_id": "run-model-timeout", "messages": []},
            )
        )
    ]

    assert events[-1]["type"] == "run_timeout"
    assert events[-1]["error_code"] == ErrorCode.TIMEOUT.value
    assert gateway.calls == 1
    assert dispatcher.calls == 0


@pytest.mark.asyncio
async def test_primary_runtime_passes_controls_without_double_budget_deduction() -> None:
    gateway = _ControlObservingGateway(
        ModelCallResult(
            provider="fake",
            model="fake-model",
            operation="infer",
            status="cancelled",
            error_code="cancelled",
        )
    )
    runtime = AgentRuntime(
        object(),
        model_gateway=gateway,
        dispatcher=_TerminalDispatcher(
            InvocationResult(invocation_id="unused", status="succeeded")
        ),
    )
    cancellation = CancellationToken()
    budget = RunBudget(max_steps=1, max_model_calls=1)

    events = [
        event
        async for event in runtime.stream_decision(
            AgentTask(
                task_id=107,
                user_id=7,
                goal="controlled cancellation",
                metadata={"run_id": "run-budget-controls", "messages": []},
            ),
            budget=budget,
            cancellation=cancellation,
        )
    ]

    assert events[-1]["type"] == "run_cancelled"
    assert len(gateway.calls) == 1
    assert gateway.calls[0]["cancellation"] is cancellation
    assert gateway.calls[0]["deadline"] > 0
    assert gateway.calls[0]["budget"]["model_calls_used"] == 1
    assert budget.steps_used == 1
    assert budget.model_calls_used == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "decision",
    [
        {
            "schema_version": "v1",
            "decision_id": "decision-wrong-run",
            "run_id": "forged-run",
            "action": "respond",
            "content": "must fail",
        },
        {
            "schema_version": "v1",
            "decision_id": "decision-forged-authority",
            "run_id": "run-invalid-decision",
            "action": "invoke",
            "capability": "catalog.search",
            "capability_version": "v1",
            "arguments": {"user_id": 999},
        },
    ],
)
async def test_primary_runtime_loop_rejects_untrusted_model_decisions(
    decision: dict,
) -> None:
    gateway = _DecisionGateway([decision])
    runtime = AgentRuntime(
        object(),
        model_gateway=gateway,
        dispatcher=Dispatcher(CapabilityRegistry()),
    )

    events = [
        event
        async for event in runtime.stream_decision(
            AgentTask(
                task_id=104,
                user_id=7,
                goal="reject forged decision",
                metadata={"run_id": "run-invalid-decision", "messages": []},
            )
        )
    ]

    assert events[-1]["type"] == "run_failed"
    assert events[-1]["error_code"] in {
        ErrorCode.INVALID_REQUEST.value,
        ErrorCode.UNAUTHORIZED.value,
    }
