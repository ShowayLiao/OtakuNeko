"""HTTP chat uses the shared read recovery policy with isolated infrastructure."""

import json
from typing import Any

import httpx
import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.v1 import agent as agent_api
from app.capabilities.registry import CapabilityRegistry
from app.core.security import create_access_token
from app.evaluation.scripted_llm import (
    ObservationExpectation,
    ScriptedLLM,
    ScriptedStep,
)
from app.harness.model_types import ModelCallResult
from app.models import User
from app.models.agent_run import AgentRun
from tests.acceptance.test_runtime_failure_paths import _FailureCapability, _READ


class _HTTPGateway(ScriptedLLM):
    async def infer(self, **kwargs: Any) -> ModelCallResult:
        if kwargs.get("goal") == "memory.fact_extraction":
            return ModelCallResult(
                provider="scripted",
                model="scripted-v1",
                operation="infer",
                status="completed",
                text='{"facts": []}',
            )
        return await super().infer(**kwargs)

    async def close(self) -> None:
        pass


@pytest.mark.asyncio
async def test_authenticated_chat_recovers_read_error_without_task_flag(
    api_client: httpx.AsyncClient,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_session.add(User(id=611, username="http-recovery-fixture"))
    await db_session.commit()
    capability = _FailureCapability()
    registry = CapabilityRegistry()
    registry.register(capability)
    gateway = _HTTPGateway(
        [
            ScriptedStep(
                decision={
                    "schema_version": "v1",
                    "decision_id": "http-read",
                    "action": "invoke",
                    "capability": _READ,
                    "capability_version": "v1",
                    "arguments": {"value": "x"},
                },
                expect=ObservationExpectation(tool_results=0),
            ),
            ScriptedStep(
                decision={
                    "schema_version": "v1",
                    "decision_id": "http-done",
                    "action": "respond",
                    "content": "Read unavailable; explained safely",
                },
                expect=ObservationExpectation(
                    tool_results=1,
                    last_tool_result={"safe_output": {"error_type": "read_failure"}},
                ),
            ),
        ]
    )
    monkeypatch.setattr(agent_api, "OpenAIModelGateway", lambda **kwargs: gateway)
    monkeypatch.setattr(agent_api, "build_capability_registry", lambda: registry)
    response = await api_client.post(
        "/api/v1/chat",
        headers={
            "Authorization": "Bearer " + create_access_token({"sub": "611"}),
            "X-API-Key": "synthetic-test-key",
        },
        json={
            "model": "scripted-v1",
            "thread_id": "http-recovery",
            "messages": [
                {"role": "user", "content": "Read fixture x"},
            ],
        },
    )
    assert response.status_code == 200
    events = [
        json.loads(line[6:])
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    assert sum(event.get("type") == "run_completed" for event in events) == 1
    assert len(gateway.calls) == 2
    assert capability.calls == [{"value": "x", "user_id": 611}]
    runs = (await db_session.exec(select(AgentRun))).all()
    assert len(runs) == 1 and runs[0].status == "succeeded"
