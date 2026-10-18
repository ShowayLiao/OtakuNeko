"""Actual SQLite checkpoint JSON boundaries under the single-worker adapter."""

from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Callable

import pytest

from app.harness.checkpoint import SqliteCheckpointStore
from app.harness.contracts import InvocationResult
from app.harness.state import AgentState
from app.harness.task import AgentTask

pytestmark = [pytest.mark.integration, pytest.mark.db]


def _state() -> AgentState:
    result = InvocationResult(
        invocation_id="checkpoint-tool",
        status="succeeded",
        output={"items": ["番剧", None, True, 0.5]},
        artifacts=[
            {"ref": "artifact:test/checkpoint.json", "media_type": "application/json"}
        ],
    )
    return AgentState(
        task=AgentTask(
            user_id=501,
            goal="serialization test",
            task_metadata={
                "run_id": "checkpoint-state",
                "thread_id": "user:501:thread:state",
                "tags": ["中文", None],
            },
            created_at=datetime(2026, 10, 17, 0, 0, tzinfo=timezone.utc),
        ),
        status="paused",
        context={
            "tool_state": result.model_dump(mode="json"),
            "pending_decision": {"action": "invoke", "arguments": {"limit": 2}},
        },
        result={"artifacts": result.artifacts},
        budget={"step_count": 9},
    )


async def test_checkpoint_reopen_roundtrips_task_tool_and_artifact_references(
    tmp_path: Path,
    record_property: Callable[[str, object], None],
) -> None:
    path = str(tmp_path / "checkpoint-state.db")
    original = _state()
    first = SqliteCheckpointStore(path)
    try:
        await first.save("checkpoint-state", "user:501:thread:state", original)
    finally:
        await first.close()
    reopened = SqliteCheckpointStore(path)
    try:
        stored = await reopened.load("checkpoint-state", "user:501:thread:state")
        assert stored is not None
        assert stored.task == original.task
        assert stored.status == "paused" and stored.result == original.result
        assert stored.context["tool_state"] == original.context["tool_state"]
        assert (
            stored.context["pending_decision"] == original.context["pending_decision"]
        )
        assert stored.context["checkpoint_version"] == 1
        assert stored.budget == {} and stored.terminal_result is None
        assert await reopened.load("checkpoint-state", "user:502:thread:state") is None
        stored.context["tool_state"]["output"]["items"].append("caller-only")
        again = await reopened.load("checkpoint-state", "user:501:thread:state")
        assert (
            again is not None
            and again.context["tool_state"] == original.context["tool_state"]
        )
    finally:
        await reopened.close()
    record_property("checkpoint_task_tool_artifact_json_roundtrip", "verified")
    record_property("checkpoint_store_reopened", "true")
    record_property("in_memory_budget_and_terminal_result_excluded", "verified")
    record_property("checkpoint_support_scope", "SQLite single-worker only")


async def test_checkpoint_serialization_failure_preserves_previous_state_and_next_save(
    tmp_path: Path,
    record_property: Callable[[str, object], None],
) -> None:
    store = SqliteCheckpointStore(str(tmp_path / "serialization-failure.db"))
    original = _state()
    try:
        await store.save("checkpoint-state", "user:501:thread:state", original)
        invalid = original.model_copy(update={"context": {"unsupported": object()}})
        with pytest.raises(ValueError):
            await store.save("checkpoint-state", "user:501:thread:state", invalid)
        retained = await store.load("checkpoint-state", "user:501:thread:state")
        assert retained is not None
        assert retained.context["tool_state"] == original.context["tool_state"]
        assert retained.context["checkpoint_version"] == 1
        await store.save("checkpoint-state", "user:501:thread:state", original)
        recovered = await store.load("checkpoint-state", "user:501:thread:state")
        assert recovered is not None and recovered.context["checkpoint_version"] == 2
    finally:
        await store.close()
    record_property("expected_failure_category", "checkpoint_serialization_error")
    record_property("failed_save_preserved_previous_version", "true")
    record_property("next_checkpoint_save_succeeded", "true")
