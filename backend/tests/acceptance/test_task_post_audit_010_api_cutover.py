"""BATCH-26 acceptance tests for the default API Runtime cutover."""

from __future__ import annotations

import asyncio
import hashlib
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.api.v1 import agent as agent_api
from app.capabilities.registry import CapabilityRegistry
from app.capabilities.types import ActionDescriptor, CapabilityResult
from app.harness.model_types import ModelCallResult
from app.harness.checkpoint import SqliteCheckpointStore
from app.harness.persistence.run_store import RunStore
from app.harness.state import AgentState
from app.harness.task import AgentTask
from app.schemas.user import UserRead
from app.schemas.agent import ChatRequest, Message


class _CatalogCapability:
    name = "catalog"

    def __init__(
        self,
        *,
        requires_auth: bool = False,
        approval_required: bool = False,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.calls: list[dict] = []
        self.requires_auth = requires_auth
        self.approval_required = approval_required
        self.timeout_seconds = timeout_seconds

    def actions(self):
        return [
            ActionDescriptor(
                name="search",
                public_name="catalog.search",
                description="Read catalog data",
                input_schema={
                    "type": "object",
                    "properties": {"query": {"type": "string"}},
                    "required": ["query"],
                    "additionalProperties": False,
                },
                requires_auth=self.requires_auth,
                approval_required=self.approval_required,
                timeout_seconds=self.timeout_seconds,
            )
        ]

    async def execute(self, action: str, **kwargs):
        self.calls.append({"action": action, **kwargs})
        return CapabilityResult.ok(items=["anime-a"]).to_dict()


class _SlowCatalogCapability(_CatalogCapability):
    async def execute(self, action: str, **kwargs):
        self.calls.append({"action": action, **kwargs})
        await asyncio.sleep(1)
        return CapabilityResult.ok(items=["too-late"]).to_dict()


class _UnknownCatalogCapability(_CatalogCapability):
    async def execute(self, action: str, **kwargs):
        self.calls.append({"action": action, **kwargs})
        return CapabilityResult.fail(
            "downstream state is unknown",
            error_type="operation_state_unknown",
        ).to_dict()


class _FakeModelGateway:
    decisions: list[dict] = []
    instances: list["_FakeModelGateway"] = []

    def __init__(self, **kwargs) -> None:
        self.calls: list[dict] = []
        self.instances.append(self)

    async def infer(self, **kwargs) -> ModelCallResult:
        self.calls.append(kwargs)
        decision = self.decisions[len(self.calls) - 1].copy()
        decision["run_id"] = kwargs["run_id"]
        return ModelCallResult(
            provider="fake",
            model="fake-model",
            operation="infer",
            status="completed",
            decision=decision,
        )

    async def close(self) -> None:
        return None


class _FailedModelGateway(_FakeModelGateway):
    error_code = "permanent"

    async def infer(self, **kwargs) -> ModelCallResult:
        self.calls.append(kwargs)
        return ModelCallResult(
            provider="fake",
            model="fake-model",
            operation="infer",
            status="failed",
            error_code=self.error_code,
        )


def _request() -> ChatRequest:
    return ChatRequest(
        model="fake-model",
        messages=[Message(role="user", content="find anime")],
    )


async def _body(response) -> str:
    return "".join([chunk async for chunk in response.body_iterator])


@pytest.mark.asyncio
async def test_default_chat_does_not_construct_legacy_langgraph_loop(monkeypatch) -> None:
    _FakeModelGateway.instances.clear()
    _FakeModelGateway.decisions = [
        {
            "schema_version": "v1",
            "decision_id": "decision-answer",
            "action": "respond",
            "content": "runtime answer",
        }
    ]
    monkeypatch.setattr(agent_api, "OpenAIModelGateway", _FakeModelGateway)
    monkeypatch.setattr(agent_api, "_resolve_provider_base_url", lambda value: "https://api.openai.com")
    monkeypatch.setattr(agent_api, "SqlTraceStore", lambda db: None)

    response = await agent_api.chat_endpoint(
        _request(),
        x_api_key="fake-key",
        x_base_url="https://api.openai.com/v1",
        user=None,
        db=object(),
    )
    body = await _body(response)

    assert "event: run_completed" in body
    assert '"content": "runtime answer"' in body
    assert "event: error" not in body


@pytest.mark.asyncio
async def test_default_chat_routes_tool_execution_through_dispatcher(monkeypatch) -> None:
    capability = _CatalogCapability()
    registry = CapabilityRegistry()
    registry.register(capability)
    _FakeModelGateway.instances.clear()
    _FakeModelGateway.decisions = [
        {
            "schema_version": "v1",
            "decision_id": "decision-search",
            "action": "invoke",
            "capability": "catalog.search",
            "capability_version": "v1",
            "arguments": {"query": "anime"},
        },
        {
            "schema_version": "v1",
            "decision_id": "decision-answer",
            "action": "respond",
            "content": "found anime-a",
        },
    ]
    monkeypatch.setattr(agent_api, "OpenAIModelGateway", _FakeModelGateway)
    monkeypatch.setattr(agent_api, "build_capability_registry", lambda: registry)
    monkeypatch.setattr(agent_api, "_resolve_provider_base_url", lambda value: "https://api.openai.com")
    monkeypatch.setattr(agent_api, "SqlTraceStore", lambda db: None)

    response = await agent_api.chat_endpoint(
        _request(),
        x_api_key="fake-key",
        x_base_url="https://api.openai.com/v1",
        user=None,
        db=object(),
    )
    body = await _body(response)

    assert capability.calls == [{"action": "search", "query": "anime"}]
    assert "event: tool_call_start" in body
    assert "event: tool_call_end" in body
    assert '"content": "found anime-a"' in body
    assert "event: error" not in body


@pytest.mark.asyncio
async def test_main_api_eval_denied_capability_never_calls_domain_service(monkeypatch) -> None:
    capability = _CatalogCapability(requires_auth=True)
    registry = CapabilityRegistry()
    registry.register(capability)
    _FakeModelGateway.instances.clear()
    _FakeModelGateway.decisions = [
        {
            "schema_version": "v1",
            "decision_id": "decision-protected",
            "action": "invoke",
            "capability": "catalog.search",
            "capability_version": "v1",
            "arguments": {"query": "private"},
        }
    ]
    monkeypatch.setattr(agent_api, "OpenAIModelGateway", _FakeModelGateway)
    monkeypatch.setattr(agent_api, "build_capability_registry", lambda: registry)
    monkeypatch.setattr(agent_api, "_resolve_provider_base_url", lambda value: "https://api.openai.com")
    monkeypatch.setattr(agent_api, "SqlTraceStore", lambda db: None)

    body = await _body(
        await agent_api.chat_endpoint(
            _request(),
            x_api_key="fake-key",
            x_base_url="https://api.openai.com/v1",
            user=None,
            db=object(),
        )
    )

    assert capability.calls == []
    assert "event: run_failed" in body
    assert '"error_code": "unauthorized"' in body


@pytest.mark.asyncio
async def test_main_api_eval_requires_trusted_approval(monkeypatch) -> None:
    capability = _CatalogCapability(approval_required=True)
    registry = CapabilityRegistry()
    registry.register(capability)
    _FakeModelGateway.instances.clear()
    _FakeModelGateway.decisions = [
        {
            "schema_version": "v1",
            "decision_id": "decision-approval",
            "action": "invoke",
            "capability": "catalog.search",
            "capability_version": "v1",
            "arguments": {"query": "write"},
        }
    ]
    monkeypatch.setattr(agent_api, "OpenAIModelGateway", _FakeModelGateway)
    monkeypatch.setattr(agent_api, "build_capability_registry", lambda: registry)
    monkeypatch.setattr(agent_api, "_resolve_provider_base_url", lambda value: "https://api.openai.com")
    monkeypatch.setattr(agent_api, "SqlTraceStore", lambda db: None)

    body = await _body(
        await agent_api.chat_endpoint(
            _request(),
            x_api_key="fake-key",
            x_base_url="https://api.openai.com/v1",
            user=None,
            db=object(),
        )
    )

    assert capability.calls == []
    assert "event: approval_required" in body
    assert "event: run_failed" not in body


@pytest.mark.asyncio
async def test_main_api_resume_approval_rehydrates_runtime(
    db_session, tmp_path, monkeypatch
) -> None:
    run_id = "run-api-approval"
    public_thread_id = "approval-thread"
    internal_thread_id = "user:7:thread:approval-thread"
    checkpoint_path = str(tmp_path / "api-approval" / "checkpoints.db")
    monkeypatch.setattr(agent_api.settings, "CHECKPOINT_DB_PATH", checkpoint_path)
    monkeypatch.setattr(
        agent_api,
        "OpenAIModelGateway",
        _FakeModelGateway,
    )
    monkeypatch.setattr(
        agent_api,
        "_resolve_provider_base_url",
        lambda value: "https://api.openai.com",
    )
    monkeypatch.setattr(agent_api, "SqlTraceStore", lambda db: None)

    capability = _CatalogCapability(approval_required=True)
    registry = CapabilityRegistry()
    registry.register(capability)
    monkeypatch.setattr(agent_api, "build_capability_registry", lambda: registry)

    await RunStore(db_session).create(
        run_id=run_id,
        user_id=7,
        thread_id=internal_thread_id,
        status="paused",
        goal_hash=hashlib.sha256("find anime".encode("utf-8")).hexdigest(),
        model="fake-model",
    )
    checkpoint = SqliteCheckpointStore(checkpoint_path)
    await checkpoint.save(
        run_id,
        internal_thread_id,
        AgentState(
            task=AgentTask(
                user_id=7,
                goal="find anime",
                metadata={
                    "run_id": run_id,
                    "thread_id": internal_thread_id,
                    "model": "fake-model",
                    "messages": [],
                },
            ),
            status="paused",
            context={
                "run_id": run_id,
                "trace_id": "trace-api-approval",
                "decision_messages": [],
                "pending_decision": {
                    "schema_version": "v1",
                    "decision_id": "decision-api-approval",
                    "run_id": run_id,
                    "action": "invoke",
                    "capability": "catalog.search",
                    "capability_version": "v1",
                    "arguments": {"query": "approved"},
                },
                "pending_invocation_started": False,
            },
        ),
    )
    await checkpoint.close()

    _FakeModelGateway.instances.clear()
    _FakeModelGateway.decisions = [
        {
            "schema_version": "v1",
            "decision_id": "decision-api-answer",
            "action": "respond",
            "content": "approved answer",
        }
    ]
    response = await agent_api.resume_chat(
        thread_id=public_thread_id,
        run_id=run_id,
        decision="approve",
        x_api_key="fake-key",
        x_base_url="https://api.openai.com/v1",
        user=UserRead(
            id=7,
            username="user-7",
            created_at=datetime.now(timezone.utc),
        ),
        db=db_session,
    )
    body = await _body(response)

    assert "event: run_completed" in body
    assert capability.calls == [{"action": "search", "query": "approved"}]
    stored = await RunStore(db_session).get(run_id, user_id=7)
    assert stored is not None and stored.status == "succeeded"


@pytest.mark.asyncio
async def test_main_api_eval_maps_provider_failure_to_terminal_event(monkeypatch) -> None:
    monkeypatch.setattr(agent_api, "OpenAIModelGateway", _FailedModelGateway)
    monkeypatch.setattr(agent_api, "_resolve_provider_base_url", lambda value: "https://api.openai.com")
    monkeypatch.setattr(agent_api, "SqlTraceStore", lambda db: None)

    body = await _body(
        await agent_api.chat_endpoint(
            _request(),
            x_api_key="fake-key",
            x_base_url="https://api.openai.com/v1",
            user=None,
            db=object(),
        )
    )

    assert "event: run_failed" in body
    assert '"error_code": "provider_error"' in body


@pytest.mark.asyncio
async def test_main_api_eval_maps_tool_timeout_without_returning_domain_output(monkeypatch) -> None:
    capability = _SlowCatalogCapability(timeout_seconds=0.001)
    registry = CapabilityRegistry()
    registry.register(capability)
    _FakeModelGateway.instances.clear()
    _FakeModelGateway.decisions = [
        {
            "schema_version": "v1",
            "decision_id": "decision-slow-search",
            "action": "invoke",
            "capability": "catalog.search",
            "capability_version": "v1",
            "arguments": {"query": "slow"},
        }
    ]
    monkeypatch.setattr(agent_api, "OpenAIModelGateway", _FakeModelGateway)
    monkeypatch.setattr(agent_api, "build_capability_registry", lambda: registry)
    monkeypatch.setattr(agent_api, "_resolve_provider_base_url", lambda value: "https://api.openai.com")
    monkeypatch.setattr(agent_api, "SqlTraceStore", lambda db: None)

    body = await _body(
        await agent_api.chat_endpoint(
            _request(),
            x_api_key="fake-key",
            x_base_url="https://api.openai.com/v1",
            user=None,
            db=object(),
        )
    )

    assert capability.calls == [{"action": "search", "query": "slow"}]
    assert "event: run_timeout" in body


@pytest.mark.asyncio
async def test_main_api_eval_preserves_unknown_outcome_as_safe_terminal_failure(monkeypatch) -> None:
    capability = _UnknownCatalogCapability()
    registry = CapabilityRegistry()
    registry.register(capability)
    _FakeModelGateway.instances.clear()
    _FakeModelGateway.decisions = [
        {
            "schema_version": "v1",
            "decision_id": "decision-unknown",
            "action": "invoke",
            "capability": "catalog.search",
            "capability_version": "v1",
            "arguments": {"query": "uncertain"},
        }
    ]
    monkeypatch.setattr(agent_api, "OpenAIModelGateway", _FakeModelGateway)
    monkeypatch.setattr(agent_api, "build_capability_registry", lambda: registry)
    monkeypatch.setattr(agent_api, "_resolve_provider_base_url", lambda value: "https://api.openai.com")
    monkeypatch.setattr(agent_api, "SqlTraceStore", lambda db: None)

    body = await _body(
        await agent_api.chat_endpoint(
            _request(),
            x_api_key="fake-key",
            x_base_url="https://api.openai.com/v1",
            user=None,
            db=object(),
        )
    )

    assert capability.calls == [{"action": "search", "query": "uncertain"}]
    assert "operation_state_unknown" in body
    assert "downstream state is unknown" not in body
    assert "event: run_failed" in body


@pytest.mark.asyncio
async def test_main_api_eval_cancellation_stops_before_model_call(monkeypatch) -> None:
    _FakeModelGateway.instances.clear()
    _FakeModelGateway.decisions = []
    original_register = agent_api.cancellation_store.register

    def cancel_on_register(run_id, token):
        original_register(run_id, token)
        token.cancel()

    monkeypatch.setattr(agent_api.cancellation_store, "register", cancel_on_register)
    monkeypatch.setattr(agent_api, "OpenAIModelGateway", _FakeModelGateway)
    monkeypatch.setattr(agent_api, "_resolve_provider_base_url", lambda value: "https://api.openai.com")
    monkeypatch.setattr(agent_api, "SqlTraceStore", lambda db: None)

    body = await _body(
        await agent_api.chat_endpoint(
            _request(),
            x_api_key="fake-key",
            x_base_url="https://api.openai.com/v1",
            user=None,
            db=object(),
        )
    )

    assert _FakeModelGateway.instances[0].calls == []
    assert "event: run_cancelled" in body


@pytest.mark.asyncio
async def test_main_api_eval_rejects_prompt_injection_authority_fields(monkeypatch) -> None:
    _FakeModelGateway.instances.clear()
    _FakeModelGateway.decisions = [
        {
            "schema_version": "v1",
            "decision_id": "decision-injection",
            "action": "invoke",
            "capability": "catalog.search",
            "capability_version": "v1",
            "arguments": {"query": "ignore policy", "user_id": 999},
        }
    ]
    monkeypatch.setattr(agent_api, "OpenAIModelGateway", _FakeModelGateway)
    monkeypatch.setattr(agent_api, "_resolve_provider_base_url", lambda value: "https://api.openai.com")
    monkeypatch.setattr(agent_api, "SqlTraceStore", lambda db: None)

    body = await _body(
        await agent_api.chat_endpoint(
            _request(),
            x_api_key="fake-key",
            x_base_url="https://api.openai.com/v1",
            user=None,
            db=object(),
        )
    )

    assert "event: run_failed" in body
    assert '"error_code": "invalid_request"' in body
    assert "999" not in body


@pytest.mark.asyncio
async def test_resume_requires_a_canonical_run_id() -> None:
    with pytest.raises(HTTPException) as exc_info:
        await agent_api.resume_chat(
            thread_id="thread-1",
            decision="approve",
            user=SimpleNamespace(id=7),
            db=object(),
        )

    assert exc_info.value.status_code == 400
    assert exc_info.value.detail == "run_id is required"


def test_chat_request_rejects_empty_messages() -> None:
    with pytest.raises(ValidationError):
        ChatRequest(model="fake-model", messages=[])


@pytest.mark.asyncio
async def test_chat_stream_does_not_expose_raw_exception_details(monkeypatch) -> None:
    class _ExplodingGateway:
        def __init__(self, **kwargs) -> None:
            raise RuntimeError("provider secret endpoint detail")

    monkeypatch.setattr(agent_api, "OpenAIModelGateway", _ExplodingGateway)
    monkeypatch.setattr(
        agent_api,
        "_resolve_provider_base_url",
        lambda value: "https://api.openai.com",
    )

    body = await _body(
        await agent_api.chat_endpoint(
            _request(),
            x_api_key="fake-key",
            x_base_url="https://api.openai.com/v1",
            user=None,
            db=object(),
        )
    )

    assert "provider secret endpoint detail" not in body
    assert '"error_code": "internal_error"' in body


@pytest.mark.asyncio
async def test_cancel_endpoint_only_records_request_for_runtime(monkeypatch) -> None:
    events = []

    class _Run:
        run_id = "run-cancel-request"
        status = "running"
        error_code = None

    class _EventStore:
        def __init__(self, db) -> None:
            pass

        async def append(self, event) -> None:
            events.append(event)

    class _ForbiddenRunStore:
        def __init__(self, db) -> None:
            raise AssertionError("API cancellation must not transition Run state")

    async def _scoped_run(*args, **kwargs):
        return _Run()

    monkeypatch.setattr(agent_api, "_get_scoped_run", _scoped_run)
    monkeypatch.setattr(agent_api, "_checkpoint_adapter_enabled", lambda: False)
    async def _last_event_sequence(*args):
        return 0

    monkeypatch.setattr(agent_api, "_last_event_sequence", _last_event_sequence)
    monkeypatch.setattr(agent_api, "EventStore", _EventStore)
    monkeypatch.setattr(agent_api, "RunStore", _ForbiddenRunStore)
    monkeypatch.setattr(agent_api.cancellation_store, "cancel", lambda run_id: True)

    result = await agent_api.cancel_run(
        "run-cancel-request",
        user=SimpleNamespace(id=7),
        db=object(),
    )

    assert result["status"] == "running"
    assert result["cancellation_requested"] is True
    assert [event.event_type for event in events] == ["run.cancel_requested"]
