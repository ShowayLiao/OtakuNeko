"""Tests for the AgentState model (HARNESS-001 Step 02)."""

from app.harness.task import AgentTask
from app.harness.state import AgentState


class TestAgentStateInstantiation:
    def test_default_state(self) -> None:
        task = AgentTask(user_id=1, goal="test")
        state = AgentState(task=task)
        assert state.task == task
        assert state.current_step == ""
        assert state.context == {}
        assert state.result is None
        assert state.status == "pending"

    def test_running_state(self) -> None:
        task = AgentTask(user_id=1, goal="test")
        state = AgentState(
            task=task,
            current_step="thinking",
            context={"key": "val"},
            status="running",
        )
        assert state.status == "running"
        assert state.current_step == "thinking"
        assert state.context == {"key": "val"}

    def test_state_independent_update(self) -> None:
        task = AgentTask(user_id=1, goal="test")
        state = AgentState(task=task)
        updated = state.model_copy(
            update={"current_step": "tools", "status": "running"}
        )
        assert updated.current_step == "tools"
        assert updated.status == "running"
        assert state.status == "pending"

    def test_completed_state(self) -> None:
        task = AgentTask(user_id=1, goal="test")
        state = AgentState(
            task=task,
            status="completed",
            result={"recommendations": ["Steins;Gate", "EVA"]},
        )
        assert state.status == "completed"
        assert state.result == {"recommendations": ["Steins;Gate", "EVA"]}

    def test_model_dump(self) -> None:
        task = AgentTask(user_id=2, goal="test")
        state = AgentState(task=task, current_step="speak", status="completed")
        data = state.model_dump()
        assert set(data.keys()) == {
            "task",
            "current_step",
            "context",
            "result",
            "status",
        }
        assert data["status"] == "completed"
        assert data["current_step"] == "speak"
        assert data["task"]["user_id"] == 2
