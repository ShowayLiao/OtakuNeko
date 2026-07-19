"""Tests for the AgentTask model (HARNESS-001 Step 01)."""

from datetime import datetime, timezone

from app.harness.task import AgentTask


class TestAgentTaskInstantiation:
    def test_minimal_construction(self) -> None:
        task = AgentTask(user_id=1, goal="Find me an anime to watch")
        assert task.user_id == 1
        assert task.goal == "Find me an anime to watch"
        assert task.metadata == {}
        assert task.task_id is None
        assert isinstance(task.created_at, datetime)

    def test_full_construction(self) -> None:
        created = datetime(2026, 7, 19, 12, 0, 0, tzinfo=timezone.utc)
        task = AgentTask(
            task_id=42,
            user_id=7,
            goal="Recommend a psychological thriller",
            metadata={"source": "chat", "priority": "high"},
            created_at=created,
        )
        assert task.task_id == 42
        assert task.user_id == 7
        assert task.goal == "Recommend a psychological thriller"
        assert task.metadata == {"source": "chat", "priority": "high"}
        assert task.created_at == created

    def test_metadata_defaults_to_empty_dict(self) -> None:
        task = AgentTask(user_id=1, goal="test")
        assert task.metadata == {}
        assert isinstance(task.metadata, dict)

    def test_created_at_auto_populated(self) -> None:
        before = datetime.now(timezone.utc)
        task = AgentTask(user_id=1, goal="test")
        after = datetime.now(timezone.utc)
        assert before <= task.created_at <= after

    def test_model_dump_includes_all_fields(self) -> None:
        task = AgentTask(user_id=1, goal="test", metadata={"key": "val"})
        data = task.model_dump()
        assert set(data.keys()) == {"task_id", "user_id", "goal", "metadata", "created_at"}
        assert data["user_id"] == 1
        assert data["goal"] == "test"
        assert data["metadata"] == {"key": "val"}
        assert data["task_id"] is None

    def test_model_dump_json(self) -> None:
        task = AgentTask(user_id=1, goal="test")
        json_str = task.model_dump_json()
        assert '"user_id":1' in json_str
        assert '"goal":"test"' in json_str
