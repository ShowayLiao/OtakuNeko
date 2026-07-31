"""Tests for the run-scoped checkpoint port and adapters."""

import pytest

from app.harness.checkpoint import InMemoryCheckpointStore, SqliteCheckpointStore
from app.harness.task import AgentTask
from app.harness.state import AgentState


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

    async def test_run_scoped_save_and_load_does_not_cross_threads(self) -> None:
        store = InMemoryCheckpointStore()
        state = AgentState(
            task=AgentTask(user_id=7, goal="scoped"),
            status="running",
        )

        await store.save("run-1", "thread-1", state)

        assert (await store.load("run-1", "thread-1")).status == "running"
        assert await store.load("run-1", "thread-2") is None
        assert await store.load("run-2", "thread-1") is None

    async def test_mark_abandoned_preserves_reason_and_terminal_scope(self) -> None:
        store = InMemoryCheckpointStore()
        await store.save(
            "run-abandon",
            "thread-1",
            AgentState(
                task=AgentTask(user_id=7, goal="recover"),
                status="running",
            ),
        )

        await store.mark_abandoned("run-abandon", "worker lease expired")
        abandoned = await store.load("run-abandon", "thread-1")

        assert abandoned is not None
        assert abandoned.status == "abandoned"
        assert abandoned.context["abandon_reason"] == "worker lease expired"


class TestSqliteCheckpointStore:
    async def test_runtime_compatibility_uses_run_metadata_without_task_id(
        self, tmp_path
    ) -> None:
        path = str(tmp_path / "metadata" / "checkpoints.db")
        state = AgentState(
            task=AgentTask(
                user_id=9,
                goal="metadata scope",
                metadata={"run_id": "run-meta", "thread_id": "thread-meta"},
            ),
            status="running",
        )
        store = SqliteCheckpointStore(path)

        await store.save_state(state)
        loaded = await store.load("run-meta", "thread-meta")
        await store.close()

        assert loaded is not None
        assert loaded.task.goal == "metadata scope"

    async def test_checkpoint_reopens_from_file(self, tmp_path) -> None:
        path = str(tmp_path / "nested" / "checkpoints.db")
        state = AgentState(
            task=AgentTask(user_id=9, goal="reopen"),
            status="running",
        )

        first = SqliteCheckpointStore(path)
        await first.save("run-reopen", "thread-reopen", state)
        await first.close()

        second = SqliteCheckpointStore(path)
        loaded = await second.load("run-reopen", "thread-reopen")
        await second.close()

        assert loaded is not None
        assert loaded.task.user_id == 9
        assert loaded.status == "running"

    async def test_abandoned_run_cannot_be_saved_after_restart(self, tmp_path) -> None:
        path = str(tmp_path / "abandoned" / "checkpoints.db")
        first = SqliteCheckpointStore(path)
        await first.mark_abandoned("run-abandoned", "lease expired")
        await first.close()

        second = SqliteCheckpointStore(path)
        with pytest.raises(ValueError, match="abandoned"):
            await second.save(
                "run-abandoned",
                "thread-1",
                AgentState(
                    task=AgentTask(user_id=9, goal="must not resume"),
                    status="running",
                ),
            )
        await second.close()
