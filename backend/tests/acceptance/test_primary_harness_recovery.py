"""Primary Runtime cancellation, checkpoint and recovery acceptance coverage."""

from __future__ import annotations

import asyncio

import pytest

from app.harness.budget import CancellationToken
from app.harness.checkpoint import InMemoryCheckpointStore
from app.harness.contracts import ErrorCode
from app.harness.runtime import AgentRuntime
from app.harness.state import AgentState
from app.harness.task import AgentTask


class _SlowRuntimeAdapter:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.calls = 0

    async def run(self, state: AgentState):
        self.calls += 1
        self.started.set()
        await asyncio.sleep(10)
        return {"content": "late"}


class _ResumeRuntimeAdapter:
    def __init__(self) -> None:
        self.calls = 0

    async def run(self, state: AgentState):
        self.calls += 1
        return {"content": "resumed"}


@pytest.mark.asyncio
async def test_runtime_cancellation_and_resume_preserve_one_terminal_owner() -> None:
    cancellation = CancellationToken()
    adapter = _SlowRuntimeAdapter()
    runtime = AgentRuntime(adapter)
    task = asyncio.create_task(
        runtime.execute(
            AgentTask(task_id=3, user_id=7, goal="cancel"),
            cancellation=cancellation,
        )
    )
    await adapter.started.wait()
    cancellation.cancel()
    cancelled = await task

    assert cancelled.status == "cancelled"
    assert cancelled.terminal_result is not None
    assert cancelled.terminal_result.error_code == ErrorCode.CANCELLED

    checkpoints = InMemoryCheckpointStore()
    resume_adapter = _ResumeRuntimeAdapter()
    resume_runtime = AgentRuntime(resume_adapter, checkpoint_store=checkpoints)
    resume_task = AgentTask(
        task_id=4,
        user_id=7,
        goal="resume",
        metadata={"run_id": "run-recovery", "thread_id": "thread-recovery"},
    )
    await checkpoints.save(
        "run-recovery",
        "thread-recovery",
        AgentState(task=resume_task, status="running"),
    )

    resumed = await resume_runtime.resume(resume_task)
    terminal = await resume_runtime.resume(resume_task)

    assert resumed is not None and resumed.status == "completed"
    assert terminal is not None and terminal.status == "completed"
    assert resume_adapter.calls == 1
