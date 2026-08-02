"""Red contract tests for TASK-POST-AUDIT-004.

These tests describe the boundary before the implementation is changed:
provider calls carry correlation metadata, memory uses the current Run
namespace, and provider endpoint validation checks resolved addresses.
"""

from __future__ import annotations

from types import SimpleNamespace
from decimal import Decimal

import pytest

from app.agents import provider_endpoint
from app.harness.model_types import ModelCallResult, ModelUsage
from app.harness.budget import BudgetExceededError, RunBudget
from app.harness.model_gateway import OpenAICompatibleModelAdapter, OpenAIModelGateway
from app.memory.manager import MemoryManager
from app.memory.extractor import LLMFactExtractor
from app.memory.service import MemoryServiceImpl


def test_model_result_preserves_provider_call_and_trace_correlation() -> None:
    result = ModelCallResult(
        provider="test-provider",
        model="test-model",
        operation="complete",
        status="completed",
        call_id="provider-call-1",
        trace_id="run-trace-1",
        usage=ModelUsage(prompt_tokens=2, completion_tokens=3, total_tokens=5),
    )

    assert result.call_id == "provider-call-1"
    assert result.trace_id == "run-trace-1"
    assert result.usage.total_tokens == 5


class _CompletionClient:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.chat = SimpleNamespace(completions=self)

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(
            id="provider-call-2",
            choices=[
                SimpleNamespace(
                    message=SimpleNamespace(content='{"facts": []}', tool_calls=[]),
                    finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(prompt_tokens=2, completion_tokens=1, total_tokens=3),
        )


@pytest.mark.asyncio
async def test_provider_adapter_keeps_call_id_and_does_not_send_trace_context() -> None:
    client = _CompletionClient()
    adapter = OpenAICompatibleModelAdapter(client, provider="test-provider")

    result = await adapter.complete(
        messages=[{"role": "user", "content": "hello"}],
        model="test-model",
        trace_id="run-trace-2",
    )

    assert result.call_id == "provider-call-2"
    assert result.trace_id == "run-trace-2"
    assert "trace_id" not in client.calls[0]


@pytest.mark.asyncio
async def test_model_gateway_does_not_forward_trusted_runtime_context_to_provider() -> None:
    client = _CompletionClient()
    gateway = OpenAIModelGateway(
        api_key="test-key",
        base_url="https://provider.example/v1",
        model="test-model",
        client=client,
    )

    await gateway.infer(
        goal="goal",
        messages=[{"role": "user", "content": "hello"}],
        context={"principal_id": 7, "trace_id": "trace-b"},
    )

    assert "context" not in client.calls[0]
    assert "principal_id" not in str(client.calls[0])
    assert "trace_id" not in client.calls[0]
    assert gateway.last_result is not None
    assert gateway.last_result.trace_id == "trace-b"


class _ExtractionGateway:
    def __init__(self) -> None:
        self.calls = 0

    async def infer(self, **kwargs):
        self.calls += 1
        return ModelCallResult(
            provider="test-provider",
            model="test-model",
            operation="memory.fact_extraction",
            status="completed",
            text='{"facts": [{"content": "likes sci-fi", "importance": 0.8}]}',
            usage=ModelUsage(
                prompt_tokens=2,
                completion_tokens=3,
                total_tokens=5,
                estimated_cost_usd=Decimal("0.01"),
            ),
            trace_id=kwargs.get("trace_id"),
        )


@pytest.mark.asyncio
async def test_memory_extraction_uses_the_run_budget_and_provider_contract() -> None:
    gateway = _ExtractionGateway()
    extractor = LLMFactExtractor(
        "test-key",
        "https://provider.example/v1",
        model_gateway=gateway,
    )
    budget = RunBudget(
        max_model_calls=1,
        max_total_tokens=5,
        max_cost_usd=Decimal("0.01"),
    )

    facts = await extractor.extract_for_run(
        [{"role": "user", "content": "I like sci-fi"}],
        run_id="run-a",
        trace_id="trace-a",
        budget=budget,
    )

    assert facts[0]["content"] == "likes sci-fi"
    assert gateway.calls == 1
    assert budget.total_tokens_used == 5
    assert budget.total_cost_usd == Decimal("0.01")
    with pytest.raises(BudgetExceededError):
        await extractor.extract_for_run(
            [{"role": "user", "content": "another"}],
            run_id="run-a",
            trace_id="trace-a",
            budget=budget,
        )


class _CapturingCheckpointer:
    def __init__(self) -> None:
        self.configs: list[dict] = []

    async def aget_tuple(self, config: dict):
        self.configs.append(config)
        return None


@pytest.mark.asyncio
async def test_legacy_memory_manager_reads_the_current_run_namespace() -> None:
    checkpointer = _CapturingCheckpointer()
    manager = MemoryManager(
        api_key="test-key",
        base_url="https://provider.example/v1",
        checkpointer=checkpointer,
    )

    await manager.load_context("thread-1", "query", run_id="run-a")

    assert checkpointer.configs == [
        {"configurable": {"thread_id": "thread-1", "checkpoint_ns": "run-a"}}
    ]


class _EmptyRepository:
    async def get_facts(self, *args, **kwargs):
        return []


class _EmptyExtractor:
    async def extract(self, messages):
        return []


@pytest.mark.asyncio
async def test_typed_memory_service_reads_the_current_run_namespace() -> None:
    checkpointer = _CapturingCheckpointer()
    service = MemoryServiceImpl(
        repository=_EmptyRepository(),
        extractor=_EmptyExtractor(),
        api_key="test-key",
        base_url="https://provider.example/v1",
        checkpointer=checkpointer,
    )

    await service.retrieve_context(
        "thread-1", "query", user_id=7, run_id="run-a"
    )

    assert checkpointer.configs == [
        {"configurable": {"thread_id": "thread-1", "checkpoint_ns": "run-a"}}
    ]


class _RunScopedCheckpointer(_CapturingCheckpointer):
    async def aget_tuple(self, config: dict):
        await super().aget_tuple(config)
        namespace = config["configurable"]["checkpoint_ns"]
        return SimpleNamespace(
            checkpoint={
                "channel_values": {
                    "messages": [
                        SimpleNamespace(type="user", content=f"message-{namespace}")
                    ]
                }
            }
        )


@pytest.mark.asyncio
async def test_memory_run_a_cannot_read_run_b_short_term_context() -> None:
    checkpointer = _RunScopedCheckpointer()
    manager = MemoryManager(
        api_key="test-key",
        base_url="https://provider.example/v1",
        checkpointer=checkpointer,
    )

    run_a = await manager.load_context("thread-1", "query", run_id="run-a")
    run_b = await manager.load_context("thread-1", "query", run_id="run-b")

    assert run_a.short_term_messages[0]["content"] == "message-run-a"
    assert run_b.short_term_messages[0]["content"] == "message-run-b"


def test_provider_endpoint_rejects_dns_rebinding_to_private_address(monkeypatch) -> None:
    def fake_getaddrinfo(host, port, type=None):
        assert host == "provider.example"
        return [
            (SimpleNamespace(name="AF_INET"), type, 6, "", ("93.184.216.34", 443)),
            (SimpleNamespace(name="AF_INET"), type, 6, "", ("169.254.169.254", 443)),
        ]

    monkeypatch.setattr(provider_endpoint.socket, "getaddrinfo", fake_getaddrinfo)

    with pytest.raises(ValueError, match="resolved address"):
        provider_endpoint.validate_provider_endpoint(
            "https://provider.example/v1",
            resolve_dns=True,
        )


def test_provider_redirect_target_is_validated_again() -> None:
    with pytest.raises(ValueError):
        provider_endpoint.validate_provider_redirect(
            "http://169.254.169.254/latest/meta-data"
        )
