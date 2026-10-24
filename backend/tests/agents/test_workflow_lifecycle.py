"""Lifecycle coverage for the Runtime-owned Decision loop."""

from collections.abc import AsyncIterator, Sequence
from typing import Any

import pytest

from app.capabilities.registry import CapabilityRegistry
from app.harness.result import AgentResult
from app.harness.contracts import ExecutionContext
from app.harness.budget import CancellationToken
from app.harness.model_gateway import ModelGateway
from app.harness.model_types import ModelCallResult, ModelStreamEvent
from app.harness.runtime import AgentRuntime
from app.harness.task import AgentTask
from app.harness.dispatcher import Dispatcher


class _Gateway(ModelGateway):
    async def stream_infer(
        self,
        *,
        goal: str,
        messages: list[dict[str, Any]],
        context: dict[str, Any] | None = None,
        run_id: str | None = None,
        trace_id: str | None = None,
        call_id: str | None = None,
        cancellation: CancellationToken | None = None,
        deadline: float | None = None,
        budget: dict[str, Any] | None = None,
        capability_catalog: list[dict[str, Any]] | None = None,
        **kwargs: Any,
    ) -> AsyncIterator[ModelStreamEvent]:
        yield ModelStreamEvent(result=await self.infer(goal=goal, messages=messages))

    async def infer(self, **kwargs):
        return ModelCallResult(
            provider="fake",
            model="fake",
            operation="infer",
            status="completed",
            decision={
                "schema_version": "v1",
                "decision_id": "answer-1",
                "action": "respond",
                "content": "ok",
            },
        )

    async def synthesize(
        self,
        *,
        goal: str,
        messages: list[dict[str, Any]],
        results: Sequence[AgentResult | dict[str, Any]],
        cancellation: CancellationToken | None = None,
        deadline: float | None = None,
        budget: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> str:
        return "ok"

    async def synthesize_result(
        self,
        *,
        goal: str,
        messages: list[dict[str, Any]],
        results: Sequence[AgentResult | dict[str, Any]],
        cancellation: CancellationToken | None = None,
        deadline: float | None = None,
        budget: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> ModelCallResult:
        return ModelCallResult(
            provider="fake",
            model="fake",
            operation="synthesize",
            status="completed",
            text="ok",
        )


@pytest.mark.asyncio
async def test_runtime_decision_loop_emits_input_and_terminal_events():
    runtime = AgentRuntime(
        None,
        model_gateway=_Gateway(),
        dispatcher=Dispatcher(CapabilityRegistry()),
    )
    events = [
        event
        async for event in runtime.stream_decision(
            AgentTask(
                user_id=1,
                goal="hello",
                task_metadata={
                    "run_id": "run-1",
                    "thread_id": "thread-1",
                    "messages": [{"role": "user", "content": "hello"}],
                },
            ),
            context=ExecutionContext(
                principal_id=1,
                run_id="run-1",
                trace_id="trace-1",
            ),
        )
    ]

    assert events[0]["type"] == "message_input"
    assert events[0]["content"] == "hello"
    assert events[-1]["type"] == "run_completed"
