"""Lifecycle coverage for the Runtime-owned Decision loop."""

import pytest

from app.capabilities.registry import CapabilityRegistry
from app.harness.contracts import ExecutionContext
from app.harness.model_types import ModelCallResult
from app.harness.runtime import AgentRuntime
from app.harness.task import AgentTask
from app.harness.dispatcher import Dispatcher


class _Gateway:
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


@pytest.mark.asyncio
async def test_runtime_decision_loop_emits_input_and_terminal_events():
    runtime = AgentRuntime(
        object(),
        model_gateway=_Gateway(),
        dispatcher=Dispatcher(CapabilityRegistry()),
    )
    events = [
        event
        async for event in runtime.stream_decision(
            AgentTask(
                user_id=1,
                goal="hello",
                metadata={
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
