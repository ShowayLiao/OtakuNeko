import pytest

from app.api.v1 import trace as trace_api
from app.harness.runtime import AgentRuntime
from app.harness.task import AgentTask
from app.trace import AgentTrace
from app.trace.store import InMemoryTraceStore


@pytest.mark.asyncio
async def test_stream_failure_is_recorded_as_failed():
    class FailingAdapter:
        async def stream(self, state, **kwargs):
            raise RuntimeError("boom")
            yield  # pragma: no cover

    store = InMemoryTraceStore()
    runtime = AgentRuntime(FailingAdapter(), trace_store=store)

    with pytest.raises(RuntimeError):
        async for _ in runtime.stream(AgentTask(user_id=7, goal="fail")):
            pass

    traces = await store.list_recent()
    assert len(traces) == 1
    assert traces[0].status == "failed"


@pytest.mark.asyncio
async def test_trace_list_ignores_user_id_override(monkeypatch):
    store = InMemoryTraceStore()
    await store.record(AgentTrace(user_id=1, goal="private"))
    await store.record(AgentTrace(user_id=2, goal="other"))
    trace_api.init_trace_store(store)

    class User:
        id = 1

    response = await trace_api.list_traces(
        limit=20,
        user_id=2,
        user=User(),
        db=None,
        task_id=None,
        status=None,
        started_after=None,
        started_before=None,
    )

    assert response["total"] == 1
    assert response["traces"][0]["user_id"] == 1
