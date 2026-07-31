import asyncio
from decimal import Decimal

import pytest

from app.harness.budget import (
    BudgetExceededError,
    CancellationToken,
    RunBudget,
)
from app.harness.contracts import ErrorCode, RunResult
from app.harness.coordinator import RunCoordinator
from app.harness.model_types import ModelCallResult, ModelUsage
from app.harness.checkpoint import InMemoryCheckpointStore
from app.harness.runtime import AgentRuntime
from app.harness.task import AgentTask
from app.trace.store import InMemoryTraceStore


def _terminal(items: list[object]) -> RunResult:
    results = [item for item in items if isinstance(item, RunResult)]
    assert len(results) == 1
    return results[0]


class EventAdapter:
    def __init__(self, events: list[dict[str, object]]) -> None:
        self.events = events
        self.started = False

    async def stream(self, state, **kwargs):
        self.started = True
        for event in self.events:
            yield event


class SlowAdapter:
    async def stream(self, state, **kwargs):
        await asyncio.sleep(0.05)
        yield {"type": "message_chunk", "content": "late"}


class ResultAdapter:
    async def stream(self, state, **kwargs):
        yield {
            "type": "agent_result",
            "agent": "recommendation",
            "kind": "subagent",
            "result": {
                "status": "completed",
                "data": {"candidates": [{"name": "A"}]},
            },
        }


class FakeGateway:
    def __init__(self) -> None:
        self.calls = 0
        self.last_result = ModelCallResult(
            provider="fake",
            model="fake-model",
            operation="complete",
            status="completed",
            text="synthesized",
            usage=ModelUsage(
                prompt_tokens=2,
                completion_tokens=3,
                total_tokens=5,
                estimated_cost_usd=Decimal("0.01"),
            ),
        )

    async def synthesize(self, **kwargs):
        self.calls += 1
        return "synthesized"


def test_run_budget_has_finite_limits_and_tracks_unknown_usage() -> None:
    budget = RunBudget(
        max_steps=1,
        max_tool_calls=1,
        max_model_calls=1,
        max_total_tokens=5,
        max_cost_usd=Decimal("0.10"),
    )

    budget.consume_step()
    budget.consume_model_call(None)

    assert budget.steps_used == 1
    assert budget.model_calls_used == 1
    assert budget.unknown_token_calls == 1
    assert budget.unknown_cost_calls == 1
    assert budget.snapshot()["max_model_calls"] == 1

    with pytest.raises(BudgetExceededError):
        budget.consume_step()


def test_run_budget_rejects_non_finite_or_invalid_limits() -> None:
    with pytest.raises(ValueError):
        RunBudget(max_steps=-1)
    with pytest.raises(ValueError):
        RunBudget(max_cost_usd=Decimal("NaN"))


@pytest.mark.asyncio
async def test_cancellation_token_uses_asyncio_event() -> None:
    token = CancellationToken()
    assert not token.is_cancelled()
    token.cancel()
    assert token.is_cancelled()
    with pytest.raises(asyncio.CancelledError):
        token.raise_if_cancelled()


@pytest.mark.asyncio
async def test_empty_stream_has_one_completed_terminal_result() -> None:
    coordinator = RunCoordinator(EventAdapter([]))
    items = [
        item
        async for item in coordinator.stream(AgentTask(user_id=1, goal="empty"), {})
    ]

    result = _terminal(items)
    assert result.status == "completed"
    assert coordinator.events == []


@pytest.mark.asyncio
async def test_graph_error_is_failed_and_later_terminal_events_are_ignored() -> None:
    adapter = EventAdapter(
        [
            {"type": "error", "error_code": "transient"},
            {"type": "message_chunk", "content": "must not complete"},
        ]
    )
    coordinator = RunCoordinator(adapter)
    items = [
        item
        async for item in coordinator.stream(AgentTask(user_id=1, goal="error"), {})
    ]

    result = _terminal(items)
    assert result.status == "failed"
    assert result.error_code == ErrorCode.TRANSIENT
    assert len([event for event in coordinator.events if event.event_type == "error"]) == 1
    assert not any(
        isinstance(item, dict) and item.get("content") == "must not complete"
        for item in items
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("error_code", "status"),
    [("timeout", "timeout"), ("cancelled", "cancelled")],
)
async def test_error_code_controls_timeout_and_cancelled_status(
    error_code: str, status: str
) -> None:
    coordinator = RunCoordinator(EventAdapter([{"type": "error", "error_code": error_code}]))
    items = [
        item
        async for item in coordinator.stream(AgentTask(user_id=1, goal="status"), {})
    ]

    assert _terminal(items).status == status


@pytest.mark.asyncio
async def test_budget_and_tool_boundaries_are_enforced() -> None:
    adapter = EventAdapter(
        [
            {"type": "tool_call_start", "name": "search", "inputs": {}},
            {"type": "tool_call_end", "name": "search", "status": "success"},
            {"type": "tool_call_start", "name": "search", "inputs": {}},
        ]
    )
    coordinator = RunCoordinator(adapter)
    items = [
        item
        async for item in coordinator.stream(
            AgentTask(user_id=1, goal="budget"),
            {},
            budget=RunBudget(max_steps=10, max_tool_calls=1),
        )
    ]

    result = _terminal(items)
    assert result.status == "failed"
    assert result.error_code == ErrorCode.BUDGET_EXCEEDED


@pytest.mark.asyncio
async def test_deadline_is_reported_as_timeout() -> None:
    coordinator = RunCoordinator(SlowAdapter())
    items = [
        item
        async for item in coordinator.stream(
            AgentTask(user_id=1, goal="slow"),
            {},
            budget=RunBudget(deadline_seconds=0.01),
        )
    ]

    result = _terminal(items)
    assert result.status == "timeout"
    assert result.error_code == ErrorCode.TIMEOUT


@pytest.mark.asyncio
async def test_cancelled_token_stops_adapter_before_start() -> None:
    adapter = EventAdapter([{ "type": "message_chunk", "content": "no" }])
    token = CancellationToken()
    token.cancel()
    coordinator = RunCoordinator(adapter)

    items = [
        item
        async for item in coordinator.stream(
            AgentTask(user_id=1, goal="cancel"), {}, cancellation=token
        )
    ]

    result = _terminal(items)
    assert result.status == "cancelled"
    assert result.error_code == ErrorCode.CANCELLED
    assert adapter.started is False


@pytest.mark.asyncio
async def test_model_synthesis_is_inside_run_budget() -> None:
    gateway = FakeGateway()
    coordinator = RunCoordinator(ResultAdapter(), model_gateway=gateway)
    items = [
        item
        async for item in coordinator.stream(
            AgentTask(user_id=1, goal="recommend"),
            {"messages": []},
            budget=RunBudget(max_model_calls=1),
        )
    ]

    result = _terminal(items)
    assert result.status == "completed"
    assert gateway.calls == 1
    assert any(
        isinstance(item, dict) and item.get("content") == "synthesized"
        for item in items
    )
    assert coordinator.budget is not None
    assert coordinator.budget.model_calls_used == 1


@pytest.mark.asyncio
async def test_runtime_mirrors_graph_error_terminal_state_and_trace() -> None:
    checkpoints = InMemoryCheckpointStore()
    traces = InMemoryTraceStore()
    runtime = AgentRuntime(
        EventAdapter([{"type": "error", "error_code": "transient"}]),
        checkpoint_store=checkpoints,
        trace_store=traces,
    )
    task = AgentTask(task_id=501, user_id=1, goal="graph error")

    chunks = [chunk async for chunk in runtime.stream(task)]

    assert chunks == [{"type": "error", "error_code": "transient"}]
    saved = await checkpoints.load_state(501)
    assert saved is not None
    assert saved.status == "failed"
    assert saved.terminal_result is not None
    assert saved.terminal_result.error_code == ErrorCode.TRANSIENT
    trace = (await traces.list_recent(limit=1))[0]
    assert trace.status == "failed"
