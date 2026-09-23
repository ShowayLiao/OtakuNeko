from __future__ import annotations

import asyncio

import pytest

from app.harness.budget import CancellationToken
from app.harness.checkpoint import InMemoryCheckpointStore
from app.harness.contracts import ErrorCode
from app.harness.runtime import AgentRuntime
from app.harness.state import AgentState
from app.harness.task import AgentTask


class SlowAdapter:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.calls = 0

    async def run(self, state: AgentState):
        self.calls += 1
        self.started.set()
        await asyncio.sleep(10)
        return {"content": "late"}


class ResumeAdapter:
    def __init__(self) -> None:
        self.calls = 0

    async def run(self, state: AgentState):
        self.calls += 1
        return {"content": "resumed"}


@pytest.mark.asyncio
async def test_runtime_observes_durable_cancellation_before_adapter_execution() -> None:
    checkpoints = InMemoryCheckpointStore()
    await checkpoints.request_cancellation(
        "run-durable-cancel",
        requester="user:7",
        reason="cancel from another worker",
    )
    adapter = ResumeAdapter()
    runtime = AgentRuntime(adapter, checkpoint_store=checkpoints)

    state = await runtime.execute(
        AgentTask(
            user_id=7,
            goal="must not run",
            metadata={
                "run_id": "run-durable-cancel",
                "thread_id": "thread-durable-cancel",
            },
        )
    )

    assert state.status == "cancelled"
    assert state.terminal_result is not None
    assert state.terminal_result.error_code == ErrorCode.CANCELLED
    assert adapter.calls == 0


@pytest.mark.asyncio
async def test_cooperative_cancel_before_and_during_execute() -> None:
    before = CancellationToken()
    before.cancel()
    adapter = SlowAdapter()
    runtime = AgentRuntime(adapter)

    cancelled_before = await runtime.execute(
        AgentTask(task_id=10, user_id=1, goal="before"),
        cancellation=before,
    )
    assert cancelled_before.status == "cancelled"
    assert cancelled_before.terminal_result is not None
    assert cancelled_before.terminal_result.error_code == ErrorCode.CANCELLED
    assert adapter.calls == 0

    during_token = CancellationToken()
    task = asyncio.create_task(
        runtime.execute(
            AgentTask(task_id=11, user_id=1, goal="during"),
            cancellation=during_token,
        )
    )
    await adapter.started.wait()
    during_token.cancel()
    cancelled_during = await task
    assert cancelled_during.status == "cancelled"
    assert cancelled_during.terminal_result is not None
    assert cancelled_during.terminal_result.error_code == ErrorCode.CANCELLED


@pytest.mark.asyncio
async def test_resume_loads_nonterminal_checkpoint_and_does_not_rerun_terminal_state() -> None:
    checkpoints = InMemoryCheckpointStore()
    adapter = ResumeAdapter()
    runtime = AgentRuntime(adapter, checkpoint_store=checkpoints)
    task = AgentTask(
        task_id=12,
        user_id=2,
        goal="resume",
        metadata={"run_id": "run-12", "thread_id": "thread-12"},
    )
    await checkpoints.save(
        "run-12",
        "thread-12",
        AgentState(task=task, status="running"),
    )

    resumed = await runtime.resume(task)
    assert resumed is not None
    assert resumed.status == "completed"
    assert adapter.calls == 1

    terminal = await runtime.resume(task)
    assert terminal is not None
    assert terminal.status == "completed"
    assert adapter.calls == 1
