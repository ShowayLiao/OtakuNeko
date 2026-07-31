"""Characterization tests for the pre-refactor interactive harness behavior."""

from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

# The repository .env uses a non-boolean DEBUG label; keep this test process
# self-contained without changing production configuration.
os.environ["DEBUG"] = "false"

from app.api.v1 import rss as rss_module
from app.api.v1.rss import router as rss_router
from app.api.deps import _parse_qb_allowed_user_ids, get_current_user
from app.core.config import settings
from app.harness.checkpoint import InMemoryCheckpointStore
from app.harness.runtime import AgentRuntime
from app.harness.task import AgentTask
from app.schemas.rss import RssItemsResponse, RssRulesResponse
from app.schemas.user import UserRead


class FakeModel:
    """Deterministic local model stand-in; it never calls a provider."""

    async def answer(self, goal: str, tool_results: list[dict[str, Any]]) -> str:
        del tool_results
        return f"answer:{goal}"


class FakeTool:
    """Deterministic local tool stand-in with bounded, safe result metadata."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def call(self, name: str, *, failed: bool = False) -> dict[str, Any]:
        self.calls.append(name)
        return {"success": not failed}


class ScenarioAdapter:
    """Emulate the existing stream event vocabulary without network access."""

    def __init__(self, scenario: str) -> None:
        self.scenario = scenario
        self.model = FakeModel()
        self.tool = FakeTool()
        self._sequence = 0
        self.events: list[dict[str, Any]] = []

    def _event(self, event_type: str, **fields: Any) -> dict[str, Any]:
        self._sequence += 1
        event = {
            "type": event_type,
            "stream_sequence": self._sequence,
            **fields,
        }
        self.events.append(event)
        return event

    async def _run_tool(self, name: str, *, failed: bool = False):
        yield self._event("tool_call_start", name=name, status="started")
        result = await self.tool.call(name, failed=failed)
        yield self._event(
            "tool_call_end",
            name=name,
            status="error" if not result["success"] else "success",
        )

    async def stream(self, state, **kwargs: Any):
        del kwargs
        yield self._event("thinking_start")

        tool_results: list[dict[str, Any]] = []
        if self.scenario in {"single-tool", "multi-tool", "tool-error"}:
            failed = self.scenario == "tool-error"
            async for event in self._run_tool("fake.search", failed=failed):
                yield event
            tool_results.append({"success": not failed})

        if self.scenario == "multi-tool":
            async for event in self._run_tool("fake.details"):
                yield event
            tool_results.append({"success": True})

        if self.scenario == "provider-timeout":
            raise asyncio.TimeoutError("fake provider timeout")
        if self.scenario == "cancel":
            raise asyncio.CancelledError()

        answer = await self.model.answer(state.task.goal, tool_results)
        yield self._event("message_start")
        yield self._event("message_chunk", content=answer)
        yield self._event("message_end", status="success")


async def _run_scenario(scenario: str, task_id: int) -> tuple[list[dict[str, Any]], Any]:
    checkpoints = InMemoryCheckpointStore()
    runtime = AgentRuntime(
        ScenarioAdapter(scenario),
        checkpoint_store=checkpoints,
    )
    task = AgentTask(task_id=task_id, user_id=7, goal=f"baseline:{scenario}")
    chunks = [chunk async for chunk in runtime.stream(task)]
    saved = await checkpoints.load_state(task_id)
    assert saved is not None
    return chunks, saved


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("scenario", "expected_types"),
    [
        (
            "normal",
            ["thinking_start", "message_start", "message_chunk", "message_end"],
        ),
        (
            "single-tool",
            [
                "thinking_start",
                "tool_call_start",
                "tool_call_end",
                "message_start",
                "message_chunk",
                "message_end",
            ],
        ),
        (
            "multi-tool",
            [
                "thinking_start",
                "tool_call_start",
                "tool_call_end",
                "tool_call_start",
                "tool_call_end",
                "message_start",
                "message_chunk",
                "message_end",
            ],
        ),
        (
            "tool-error",
            [
                "thinking_start",
                "tool_call_start",
                "tool_call_end",
                "message_start",
                "message_chunk",
                "message_end",
            ],
        ),
    ],
)
async def test_agent_stream_baseline_paths_are_deterministic(
    scenario: str, expected_types: list[str]
) -> None:
    chunks, saved = await _run_scenario(scenario, task_id=100)

    assert [chunk["type"] for chunk in chunks] == expected_types
    assert [chunk["stream_sequence"] for chunk in chunks] == list(
        range(1, len(chunks) + 1)
    )
    assert saved.status == "completed"
    assert all("content" not in chunk for chunk in chunks if chunk["type"] != "message_chunk")
    tool_events = [
        chunk for chunk in chunks if chunk["type"].startswith("tool_call")
    ]
    assert all(chunk["name"].startswith("fake.") for chunk in tool_events)
    if scenario == "tool-error":
        assert next(chunk for chunk in chunks if chunk["type"] == "tool_call_end")[
            "status"
        ] == "error"


@pytest.mark.asyncio
async def test_provider_timeout_baseline_is_saved_as_failed() -> None:
    checkpoints = InMemoryCheckpointStore()
    adapter = ScenarioAdapter("provider-timeout")
    runtime = AgentRuntime(adapter, checkpoint_store=checkpoints)
    task = AgentTask(task_id=101, user_id=7, goal="baseline:provider-timeout")

    with pytest.raises(asyncio.TimeoutError, match="fake provider timeout"):
        _ = [chunk async for chunk in runtime.stream(task)]

    saved = await checkpoints.load_state(task.task_id)
    assert saved is not None
    assert saved.status == "failed"
    assert [event["type"] for event in adapter.events] == ["thinking_start"]
    assert [event["stream_sequence"] for event in adapter.events] == [1]


@pytest.mark.asyncio
async def test_cancel_baseline_is_saved_as_cancelled() -> None:
    checkpoints = InMemoryCheckpointStore()
    adapter = ScenarioAdapter("cancel")
    runtime = AgentRuntime(adapter, checkpoint_store=checkpoints)
    task = AgentTask(task_id=102, user_id=7, goal="baseline:cancel")

    with pytest.raises(asyncio.CancelledError):
        _ = [chunk async for chunk in runtime.stream(task)]

    saved = await checkpoints.load_state(task.task_id)
    assert saved is not None
    assert saved.status == "cancelled"
    assert [event["type"] for event in adapter.events] == ["thinking_start"]
    assert [event["stream_sequence"] for event in adapter.events] == [1]


class FakeQBService:
    calls: list[tuple[str, dict[str, Any]]] = []

    def __init__(self) -> None:
        self.calls.append(("init", {}))

    def get_rss_items(self) -> RssItemsResponse:
        self.calls.append(("list", {}))
        return RssItemsResponse(items={})

    def get_rss_rules(self) -> RssRulesResponse:
        self.calls.append(("rules", {}))
        return RssRulesResponse(rules={})

    def add_rss_feed(self, **kwargs: Any) -> None:
        self.calls.append(("add", kwargs))

    def upsert_rss_feed(self, **kwargs: Any) -> None:
        self.calls.append(("upsert", kwargs))

    def remove_rss_item(self, **kwargs: Any) -> None:
        self.calls.append(("remove", kwargs))

    def set_rss_rule(self, **kwargs: Any) -> None:
        self.calls.append(("set-rule", kwargs))

    def remove_rss_rule(self, **kwargs: Any) -> None:
        self.calls.append(("remove-rule", kwargs))


def _make_user(user_id: int) -> UserRead:
    return UserRead(
        id=user_id,
        username=f"user-{user_id}",
        created_at=datetime.now(timezone.utc),
    )


def _rss_requests() -> list[tuple[str, str, dict[str, Any] | None]]:
    rule = {
        "affectedFeeds": [],
        "assignedCategory": "anime",
        "enabled": True,
        "episodeFilter": "*",
        "ignoreDays": 0,
        "mustContain": "",
        "mustNotContain": "",
        "previouslyMatchedEpisodes": [],
        "priority": 0,
        "savePath": "",
        "smartFilter": False,
        "useRegex": False,
    }
    return [
        ("GET", "/v1/rss/list", None),
        ("GET", "/v1/rss/rules", None),
        ("POST", "/v1/rss/add", {"url": "https://example.test/feed", "name": "feed"}),
        ("POST", "/v1/rss/upsert", {"url": "https://example.test/feed", "name": "feed"}),
        ("DELETE", "/v1/rss/remove", {"item_path": "feed"}),
        ("POST", "/v1/rss/set-rule", {"rule_name": "rule", "rule": rule}),
        ("DELETE", "/v1/rss/remove-rule", {"rule_name": "rule"}),
    ]


def _make_rss_app(user: UserRead | None = None) -> FastAPI:
    app = FastAPI()
    app.include_router(rss_router, prefix="/v1")
    if user is not None:
        async def override_user() -> UserRead:
            return user

        app.dependency_overrides[get_current_user] = override_user
    return app


async def _request_rss_routes(app: FastAPI) -> list[httpx.Response]:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        responses = []
        for method, path, payload in _rss_requests():
            responses.append(
                await client.request(method, path, json=payload)
                if payload is not None
                else await client.request(method, path)
            )
        return responses


@pytest.mark.parametrize(
    ("raw_value", "expected"),
    [
        ("", set()),
        ("   ", set()),
        ("7, 7", {7}),
        (" 7, 8 ", {7, 8}),
        ("7,not-a-number", None),
        ("0", None),
        ("7,,8", None),
        ("9" * 5000, None),
    ],
)
def test_qb_allowed_user_id_parser_fails_closed(raw_value: str, expected) -> None:
    assert _parse_qb_allowed_user_ids(raw_value) == expected


@pytest.mark.asyncio
async def test_qb_routes_fail_closed_for_anonymous_and_unauthorized_users(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ENABLE_QB_PROXY", True)
    monkeypatch.setattr(settings, "QB_ALLOWED_USER_IDS", "7", raising=False)
    monkeypatch.setattr(rss_module, "QBService", FakeQBService)

    FakeQBService.calls = []
    anonymous_responses = await _request_rss_routes(_make_rss_app())
    assert all(response.status_code in {401, 403} for response in anonymous_responses)
    assert FakeQBService.calls == []

    FakeQBService.calls = []
    unauthorized_responses = await _request_rss_routes(_make_rss_app(_make_user(8)))
    assert [response.status_code for response in unauthorized_responses] == [403] * 7
    assert FakeQBService.calls == []


@pytest.mark.asyncio
async def test_authorized_user_can_reach_all_qb_routes(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ENABLE_QB_PROXY", True)
    monkeypatch.setattr(settings, "QB_ALLOWED_USER_IDS", "7, 7", raising=False)
    monkeypatch.setattr(rss_module, "QBService", FakeQBService)
    FakeQBService.calls = []

    responses = await _request_rss_routes(_make_rss_app(_make_user(7)))

    assert [response.status_code for response in responses] == [200] * 7
    assert [name for name, _ in FakeQBService.calls] == [
        "init",
        "list",
        "init",
        "rules",
        "init",
        "add",
        "init",
        "upsert",
        "init",
        "remove",
        "init",
        "set-rule",
        "init",
        "remove-rule",
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("allowlist", "expected_status"),
    [
        ("", 403),
        ("   ", 403),
        ("7, 7", 200),
        (" 7, 8 ", 200),
        ("7,not-a-number", 403),
        ("0", 403),
        ("7,,8", 403),
    ],
)
async def test_qb_allowlist_parsing_fails_closed(
    monkeypatch, allowlist: str, expected_status: int
) -> None:
    monkeypatch.setattr(settings, "ENABLE_QB_PROXY", True)
    monkeypatch.setattr(settings, "QB_ALLOWED_USER_IDS", allowlist, raising=False)
    monkeypatch.setattr(rss_module, "QBService", FakeQBService)
    FakeQBService.calls = []

    responses = await _request_rss_routes(_make_rss_app(_make_user(7)))

    assert [response.status_code for response in responses] == [expected_status] * 7
    if expected_status == 403:
        assert FakeQBService.calls == []


@pytest.mark.asyncio
async def test_qb_proxy_disabled_stops_before_service(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ENABLE_QB_PROXY", False)
    monkeypatch.setattr(settings, "QB_ALLOWED_USER_IDS", "7", raising=False)
    monkeypatch.setattr(rss_module, "QBService", FakeQBService)
    FakeQBService.calls = []

    responses = await _request_rss_routes(_make_rss_app(_make_user(7)))

    assert [response.status_code for response in responses] == [403] * 7
    assert FakeQBService.calls == []
