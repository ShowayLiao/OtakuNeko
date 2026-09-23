"""BATCH-26 entrypoint closure tests for MCP and scheduled specialists."""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.capabilities.registry import CapabilityRegistry
from app.capabilities.types import ActionDescriptor, CapabilityResult
from app.harness.contracts import InvocationResult
from app.harness.scheduler.execution import handle_task_def
from app.mcp_server import ExposureMap, MCPServer
from app.mcp_server.context import MCPContext


class _ReadCapability:
    name = "catalog"

    def actions(self):
        return [
            ActionDescriptor(
                name="search",
                public_name="catalog.search",
                description="Search",
                input_schema={"type": "object"},
            )
        ]

    async def execute(self, action: str, **kwargs):
        return CapabilityResult.ok(items=["anime-a"]).to_dict()


@pytest.mark.asyncio
async def test_mcp_tool_dispatches_through_dispatcher(monkeypatch) -> None:
    registry = CapabilityRegistry()
    registry.register(_ReadCapability())
    server = MCPServer(registry, ExposureMap({"catalog": ["search"]}))
    calls: list[tuple[object, object]] = []

    class _Dispatcher:
        def __init__(self, *args, **kwargs):
            pass

        async def dispatch(self, decision, context, **kwargs):
            calls.append((decision, context))
            return InvocationResult(
                invocation_id=decision.decision_id,
                status="succeeded",
                model_output={"safe_output": {"items": ["anime-a"]}},
            )

    monkeypatch.setattr("app.mcp_server.Dispatcher", _Dispatcher)
    result = await server.call_tool(
        "catalog_search",
        {},
        context=MCPContext(user_id=7),
    )

    assert result == {"success": True, "data": {"items": ["anime-a"]}}
    assert len(calls) == 1
    assert calls[0][0].capability == "catalog.search"
    assert calls[0][1].principal_id == 7


@pytest.mark.asyncio
async def test_scheduler_rejects_direct_specialist_bypass() -> None:
    task_def = SimpleNamespace(
        id=1,
        user_id=7,
        task_type="weekly_recommendation",
        payload="{}",
        policy="{}",
        enabled=True,
    )
    run = SimpleNamespace(
        id=2,
        lease_id="lease-1",
        scheduled_slot=datetime.now(timezone.utc),
        trace_id=None,
        status="running",
    )

    class _Router:
        def route(self, goal):
            return object()

        def select(self, decision):
            return object()

    class _Runtime:
        trace_store = None

        async def execute(self, task):
            raise AssertionError("scheduler must not execute a specialist directly")

    class _Repository:
        async def finish(self, run, **kwargs):
            return True

    with pytest.raises(PermissionError, match="Dispatcher"):
        await handle_task_def(task_def, run, _Runtime(), _Router(), repository=_Repository())
    assert run.status == "failed"
    assert run.error_category == "policy_denied"
