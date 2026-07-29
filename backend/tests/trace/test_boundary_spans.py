from __future__ import annotations

import asyncio

import pytest

from app.capabilities.base import BaseCapability
from app.capabilities.registry import CapabilityRegistry
from app.capabilities.types import ActionDescriptor
from app.agents.langgraph_adapter import LangGraphAdapter
from app.agents.mcp.connection_pool import MCPConnectionPool
from app.mcp_server import ExposureMap, MCPServer
from app.trace import AgentTrace
from app.trace.recorder import bind_trace


class _Capability(BaseCapability):
    @property
    def name(self) -> str:
        return "anime"

    @property
    def description(self) -> str:
        return "test"

    def actions(self) -> list[ActionDescriptor]:
        return [
            ActionDescriptor(
                name="search",
                description="search",
                input_schema={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                },
            )
        ]

    async def execute(self, action: str, **kwargs):
        return {"success": True, "private_result": "do not trace"}


def _events(trace: AgentTrace):
    return [event for step in trace.steps for event in step.events]


@pytest.mark.asyncio
async def test_capability_span_records_shape_without_values():
    trace = AgentTrace(user_id=1)
    with bind_trace(trace):
        result = await _Capability().execute("search", query="private review text")

    assert result["success"] is True
    event = _events(trace)[0]
    assert event.event_type == "capability_call"
    assert event.status == "completed"
    assert event.data["operation"] == "anime.search"
    assert event.data["argument_shape"] == {"query": "str"}
    assert "private review text" not in trace.model_dump_json()
    assert "do not trace" not in trace.model_dump_json()


@pytest.mark.asyncio
async def test_mcp_span_is_parent_of_capability_span():
    registry = CapabilityRegistry()
    registry.register(_Capability())
    server = MCPServer(registry, ExposureMap({"anime": ["search"]}))
    trace = AgentTrace(user_id=1)

    with bind_trace(trace):
        result = await server.call_tool("anime_search", {"query": "private"})

    assert result["success"] is True
    events = _events(trace)
    mcp_event = next(event for event in events if event.event_type == "mcp_call")
    capability_event = next(
        event for event in events if event.event_type == "capability_call"
    )
    assert capability_event.parent_event_id == mcp_event.event_id
    assert capability_event.correlation_id == mcp_event.correlation_id


@pytest.mark.asyncio
async def test_capability_timeout_is_distinguishable():
    class TimeoutCapability(_Capability):
        async def execute(self, action: str, **kwargs):
            raise asyncio.TimeoutError

    trace = AgentTrace(user_id=1)
    with bind_trace(trace):
        with pytest.raises(asyncio.TimeoutError):
            await TimeoutCapability().execute("search", query="private")

    event = _events(trace)[0]
    assert event.status == "timeout"
    assert event.data["error_category"] == "timeout"
    assert trace.steps[0].status == "timeout"


@pytest.mark.asyncio
async def test_failed_capability_result_marks_step_failed():
    class FailedCapability(_Capability):
        async def execute(self, action: str, **kwargs):
            return {"success": False, "error_type": "protocol"}

    trace = AgentTrace(user_id=1)
    with bind_trace(trace):
        await FailedCapability().execute("search", query="private")

    assert _events(trace)[0].status == "failed"
    assert trace.steps[0].status == "failed"


@pytest.mark.asyncio
async def test_langgraph_real_chunk_contract_records_nodes_and_tools_safely():
    class Workflow:
        async def stream_chat(self, **kwargs):
            yield {"type": "thinking_start"}
            yield {"type": "thinking_end"}
            yield {
                "type": "tool_call_start",
                "id": "call-1",
                "name": "search",
                "inputs": {"query": "private prompt"},
            }
            yield {
                "type": "tool_call_end",
                "id": "call-1",
                "name": "search",
                "status": "success",
                "duration_ms": 2.5,
                "output": {"content": "private result"},
            }
            yield {"type": "message_start"}
            yield {"type": "message_chunk", "content": "private answer"}
            yield {"type": "message_end"}

    trace = AgentTrace(user_id=1, agent_name="LangGraphAdapter")
    with bind_trace(trace):
        chunks = [
            chunk
            async for chunk in LangGraphAdapter(Workflow()).stream(object())
        ]

    assert len(chunks) == 7
    events = _events(trace)
    event_types = [event.event_type for event in events]
    assert "model_call" in event_types
    assert event_types.count("node_start") == 2
    assert event_types.count("node_end") == 2
    tool_start = next(
        event for event in events if event.event_type == "tool_call_start"
    )
    tool_end = next(
        event for event in events if event.event_type == "tool_call_end"
    )
    assert tool_end.parent_event_id == tool_start.event_id
    serialized = trace.model_dump_json()
    assert "private prompt" not in serialized
    assert "private result" not in serialized
    assert "private answer" not in serialized


@pytest.mark.asyncio
async def test_mcp_connection_retry_emits_safe_retry_event():
    class Transport:
        server_name = "local"

        def __init__(self):
            self.attempts = 0

        async def connect(self):
            self.attempts += 1
            if self.attempts == 1:
                raise ConnectionError("credential must not be traced")

        async def close(self):
            return None

    trace = AgentTrace(user_id=1)
    pool = MCPConnectionPool(max_retries=2, retry_delay=0)
    with bind_trace(trace):
        await pool.register(Transport())

    retry = next(event for event in _events(trace) if event.event_type == "retry")
    assert retry.data["attempt"] == 2
    assert retry.data["error_category"] == "ConnectionError"
    assert "credential must not be traced" not in trace.model_dump_json()


@pytest.mark.asyncio
async def test_langgraph_close_balances_open_node_and_tool_spans():
    class Workflow:
        async def stream_chat(self, **kwargs):
            yield {"type": "thinking_start"}
            yield {
                "type": "tool_call_start",
                "id": "call-1",
                "name": "search",
                "inputs": {"query": "private"},
            }
            await asyncio.sleep(60)

    trace = AgentTrace(user_id=1, agent_name="LangGraphAdapter")
    with bind_trace(trace):
        stream = LangGraphAdapter(Workflow()).stream(object())
        await anext(stream)
        await anext(stream)
        await stream.aclose()

    events = _events(trace)
    node_start = next(event for event in events if event.event_type == "node_start")
    node_end = next(event for event in events if event.event_type == "node_end")
    tool_start = next(
        event for event in events if event.event_type == "tool_call_start"
    )
    tool_end = next(
        event for event in events if event.event_type == "tool_call_end"
    )
    assert node_end.parent_event_id == node_start.event_id
    assert node_end.status == "cancelled"
    assert tool_end.parent_event_id == tool_start.event_id
    assert tool_end.status == "cancelled"
