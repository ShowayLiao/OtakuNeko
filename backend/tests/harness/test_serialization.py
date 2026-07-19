"""Tests for state serialization (HARNESS-002 Step 01)."""

from datetime import datetime, timezone

from app.harness.task import AgentTask
from app.harness.state import AgentState


class TestAgentStateSerialization:
    def test_round_trip_pending_state(self) -> None:
        task = AgentTask(user_id=1, goal="test")
        original = AgentState(task=task)
        data = original.to_dict()
        restored = AgentState.from_dict(data)
        assert restored.status == original.status == "pending"
        assert restored.current_step == original.current_step == ""
        assert restored.context == original.context == {}
        assert restored.result == original.result
        assert restored.task.user_id == original.task.user_id
        assert restored.task.goal == original.task.goal

    def test_round_trip_running_state(self) -> None:
        task = AgentTask(task_id=7, user_id=3, goal="running test")
        original = AgentState(
            task=task,
            current_step="tools",
            context={"tool_call": "get_anime_info", "args": {"id": 1234}},
            status="running",
        )
        data = original.to_dict()
        restored = AgentState.from_dict(data)
        assert restored.status == "running"
        assert restored.current_step == "tools"
        assert restored.context == {"tool_call": "get_anime_info", "args": {"id": 1234}}
        assert restored.task.task_id == 7

    def test_round_trip_completed_state(self) -> None:
        task = AgentTask(user_id=5, goal="complete test")
        original = AgentState(
            task=task,
            current_step="speak",
            result={"recommendations": ["Steins;Gate"], "reason": "psychological"},
            status="completed",
        )
        data = original.to_dict()
        restored = AgentState.from_dict(data)
        assert restored.status == "completed"
        assert restored.result == {"recommendations": ["Steins;Gate"], "reason": "psychological"}

    def test_round_trip_failed_state(self) -> None:
        task = AgentTask(user_id=1, goal="fail test")
        original = AgentState(
            task=task,
            status="failed",
            result={"error": "Something went wrong"},
        )
        data = original.to_dict()
        restored = AgentState.from_dict(data)
        assert restored.status == "failed"
        assert restored.result == {"error": "Something went wrong"}

    def test_round_trip_preserves_datetime(self) -> None:
        created = datetime(2026, 7, 19, 12, 0, 0, tzinfo=timezone.utc)
        task = AgentTask(user_id=1, goal="time test", created_at=created)
        original = AgentState(task=task)
        data = original.to_dict()
        restored = AgentState.from_dict(data)
        assert restored.task.created_at == created
