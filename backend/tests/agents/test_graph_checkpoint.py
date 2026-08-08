"""Run-scoped checkpoint coverage after the graph removal."""

import pytest

from app.harness.checkpoint import InMemoryCheckpointStore
from app.harness.state import AgentState
from app.harness.task import AgentTask


@pytest.mark.asyncio
async def test_checkpoint_is_scoped_by_run_and_thread():
    store = InMemoryCheckpointStore()
    state = AgentState(
        task=AgentTask(user_id=1, goal="hello"),
        status="running",
    )
    await store.save("run-1", "thread-1", state)

    assert await store.load("run-1", "thread-1") is not None
    assert await store.load("run-2", "thread-1") is None
    assert await store.load("run-1", "thread-2") is None
