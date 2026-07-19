"""Tests for the ChatWorkflow harness adapter."""

from app.harness.adapter import ChatWorkflowAdapter
from app.harness.state import AgentState
from app.harness.task import AgentTask


class FakeWorkflow:
    async def stream_chat(self, **kwargs):
        yield {"type": "message_chunk", "content": kwargs["model"]}


async def test_stream_forwards_state_and_workflow_arguments() -> None:
    adapter = ChatWorkflowAdapter(FakeWorkflow())
    state = AgentState(task=AgentTask(user_id=1, goal="test"))

    chunks = [
        chunk
        async for chunk in adapter.stream(
            state,
            model="test-model",
            messages=[],
            temperature=0.2,
        )
    ]

    assert chunks == [{"type": "message_chunk", "content": "test-model"}]
