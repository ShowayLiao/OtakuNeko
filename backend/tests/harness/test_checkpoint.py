"""Tests for checkpoint store (HARNESS-002 Step 02)."""

from app.harness.task import AgentTask
from app.harness.state import AgentState
from app.harness.checkpoint import InMemoryCheckpointStore


class TestInMemoryCheckpointStore:
    async def test_save_and_load_state(self) -> None:
        store = InMemoryCheckpointStore()
        task = AgentTask(task_id=1, user_id=42, goal="test")
        state = AgentState(task=task, current_step="tools", status="running")
        await store.save_state(state)
        loaded = await store.load_state(1)
        assert loaded is not None
        assert loaded.status == "running"
        assert loaded.current_step == "tools"
        assert loaded.task.user_id == 42

    async def test_load_missing_returns_none(self) -> None:
        store = InMemoryCheckpointStore()
        loaded = await store.load_state(999)
        assert loaded is None

    async def test_overwrite_state(self) -> None:
        store = InMemoryCheckpointStore()
        task = AgentTask(task_id=1, user_id=1, goal="first")
        state1 = AgentState(task=task, status="running")
        await store.save_state(state1)

        state2 = AgentState(task=task, status="completed", result={"done": True})
        await store.save_state(state2)

        loaded = await store.load_state(1)
        assert loaded is not None
        assert loaded.status == "completed"
        assert loaded.result == {"done": True}

    async def test_multiple_tasks(self) -> None:
        store = InMemoryCheckpointStore()
        t1 = AgentTask(task_id=1, user_id=1, goal="task 1")
        t2 = AgentTask(task_id=2, user_id=1, goal="task 2")
        await store.save_state(AgentState(task=t1, status="completed"))
        await store.save_state(AgentState(task=t2, status="running"))

        assert (await store.load_state(1)).status == "completed"
        assert (await store.load_state(2)).status == "running"
