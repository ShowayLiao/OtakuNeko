from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.harness.model_gateway import (
    LangChainModelAdapter,
    OpenAICompatibleModelAdapter,
    OpenAIModelGateway,
    provider_error_code,
    safe_provider_detail,
)
from app.harness.context_manager import ContextManager
from app.harness.contracts import ExecutionContext
from app.harness.model_types import ModelCallResult, ModelUsage
from app.harness.model_types import ModelDelta, ModelStreamEvent
from app.trace import AgentTrace, TraceEventType
from app.trace.recorder import bind_trace


class FakeCompletions:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls: list[dict] = []

    async def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.response


class FakeClient:
    def __init__(self, completions):
        self.chat = SimpleNamespace(completions=completions)
        self.models = SimpleNamespace(list=self._list_models)

    async def _list_models(self):
        return SimpleNamespace(data=[])


def response(*, content="answer", usage=None, finish_reason="stop"):
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason=finish_reason,
            )
        ],
        usage=usage,
    )


def test_model_contract_rejects_unknown_status_and_preserves_unknown_usage():
    usage = ModelUsage(latency_ms=4)
    assert usage.prompt_tokens is None
    assert usage.completion_tokens is None
    assert usage.total_tokens is None
    assert usage.estimated_cost_usd is None

    with pytest.raises(ValidationError):
        ModelCallResult(
            provider="openai",
            model="test-model",
            operation="complete",
            status="unknown",
        )


@pytest.mark.asyncio
async def test_openai_adapter_normalizes_completion_usage_and_finish_reason():
    completion = response(
        content="normalized",
        usage=SimpleNamespace(prompt_tokens=3, completion_tokens=5, total_tokens=8),
    )
    completions = FakeCompletions(response=completion)
    adapter = OpenAICompatibleModelAdapter(
        FakeClient(completions), provider="openai-compatible"
    )

    result = await adapter.complete(
        messages=[{"role": "user", "content": "hello"}],
        model="test-model",
        temperature=0.2,
    )

    assert result.status == "completed"
    assert result.text == "normalized"
    assert result.finish_reason == "stop"
    assert result.usage.prompt_tokens == 3
    assert result.usage.completion_tokens == 5
    assert result.usage.total_tokens == 8
    assert result.usage.latency_ms >= 0
    assert "api_key" not in result.model_dump()


@pytest.mark.asyncio
async def test_openai_adapter_keeps_missing_provider_usage_as_none():
    completions = FakeCompletions(response=response(usage=None))
    adapter = OpenAICompatibleModelAdapter(FakeClient(completions), provider="openai")

    result = await adapter.complete(
        messages=[{"role": "user", "content": "hello"}],
        model="test-model",
    )

    assert result.status == "completed"
    assert result.usage.prompt_tokens is None
    assert result.usage.completion_tokens is None
    assert result.usage.total_tokens is None
    assert result.usage.estimated_cost_usd is None


@pytest.mark.asyncio
async def test_provider_error_is_classified_and_does_not_expose_raw_detail():
    class RateLimitError(Exception):
        pass

    completions = FakeCompletions(error=RateLimitError("sensitive provider detail"))
    adapter = OpenAICompatibleModelAdapter(FakeClient(completions), provider="openai")

    result = await adapter.complete(
        messages=[{"role": "user", "content": "hello"}],
        model="test-model",
    )

    assert result.status == "failed"
    assert result.error_code == "rate_limited"
    assert result.retryable is True
    assert "sensitive provider detail" not in str(result.model_dump())


def test_provider_endpoint_failures_have_safe_ssrf_category():
    error = ValueError("provider endpoint resolved address is not public: 169.254.169.254")

    assert provider_error_code(error) == ("ssrf", False)
    assert safe_provider_detail(error) == "Provider endpoint is not allowed"
    assert "169.254.169.254" not in safe_provider_detail(error)


class AsyncChunkStream:
    def __init__(self, chunks):
        self.chunks = chunks

    def __aiter__(self):
        return self._iterate()

    async def _iterate(self):
        for chunk in self.chunks:
            yield chunk


@pytest.mark.asyncio
async def test_provider_stream_normalizes_reasoning_tool_and_final_chunks():
    chunks = [
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(
                        content=None,
                        reasoning_content="thinking",
                        tool_calls=[],
                    ),
                    finish_reason=None,
                )
            ],
            usage=None,
        ),
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(
                        content="answer",
                        reasoning_content=None,
                        tool_calls=[
                            SimpleNamespace(
                                index=0,
                                id="call-1",
                                function=SimpleNamespace(
                                    name="search",
                                    arguments='{"q":"x"}',
                                ),
                            )
                        ],
                    ),
                    finish_reason=None,
                )
            ],
            usage=None,
        ),
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(
                        content=None,
                        reasoning_content=None,
                        tool_calls=[],
                    ),
                    finish_reason="stop",
                )
            ],
            usage=SimpleNamespace(prompt_tokens=1, completion_tokens=2, total_tokens=3),
        ),
    ]
    completions = FakeCompletions()

    async def create(**kwargs):
        completions.calls.append(kwargs)
        return AsyncChunkStream(chunks)

    completions.create = create
    adapter = OpenAICompatibleModelAdapter(FakeClient(completions), provider="deepseek")

    deltas = [
        delta
        async for delta in adapter.stream(
            messages=[{"role": "user", "content": "hello"}],
            model="deepseek-chat",
        )
    ]

    assert [delta.kind for delta in deltas] == ["reasoning", "tool_call", "text"]
    assert deltas[0].text == "thinking"
    assert deltas[1].tool_call["id"] == "call-1"
    assert deltas[2].text == "answer"
    assert adapter.last_result is not None
    assert adapter.last_result.finish_reason == "stop"
    assert adapter.last_result.usage.total_tokens == 3
    assert completions.calls[0]["stream_options"] == {"include_usage": True}


@pytest.mark.asyncio
async def test_provider_stream_accumulates_reasoning_and_final_decision():
    decision_text = (
        '{"schema_version":"v1","decision_id":"d-stream",'
        '"action":"respond","content":"answer"}'
    )
    chunks = [
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(
                        content=decision_text[:35],
                        reasoning_content="first ",
                        tool_calls=[],
                    ),
                    finish_reason=None,
                )
            ],
            usage=None,
        ),
        SimpleNamespace(
            choices=[
                SimpleNamespace(
                    delta=SimpleNamespace(
                        content=decision_text[35:],
                        reasoning_content="second",
                        tool_calls=[],
                    ),
                    finish_reason="stop",
                )
            ],
            usage=None,
        ),
    ]
    completions = FakeCompletions()

    async def create(**kwargs):
        completions.calls.append(kwargs)
        return AsyncChunkStream(chunks)

    completions.create = create
    adapter = OpenAICompatibleModelAdapter(FakeClient(completions), provider="deepseek")

    deltas = [
        delta
        async for delta in adapter.stream(
            messages=[{"role": "user", "content": "hello"}],
            model="deepseek-chat",
        )
    ]

    assert [delta.kind for delta in deltas] == ["reasoning", "text", "reasoning", "text"]
    assert adapter.last_result is not None
    assert adapter.last_result.reasoning == "first second"
    assert adapter.last_result.text == decision_text
    assert adapter.last_result.decision == {
        "schema_version": "v1",
        "decision_id": "d-stream",
        "action": "respond",
        "content": "answer",
    }


@pytest.mark.asyncio
async def test_gateway_stream_infer_emits_deltas_then_final_result():
    class StreamingAdapter:
        last_result = ModelCallResult(
            provider="fake",
            model="stream-model",
            operation="stream",
            status="completed",
            text='{"action":"finish","content":"done"}',
            decision={"action": "finish", "content": "done"},
        )

        async def complete(self, **kwargs):
            raise AssertionError("streaming test must not call complete")

        async def stream(self, **kwargs):
            yield ModelDelta(kind="reasoning", text="thinking")
            yield ModelDelta(kind="text", text="decision")

    gateway = OpenAIModelGateway(
        api_key="test-key",
        base_url="https://example.test/v1",
        model="stream-model",
        adapter=StreamingAdapter(),
    )

    events = [event async for event in gateway.stream_infer(goal="goal", messages=[])]

    assert events[:2] == [
        ModelStreamEvent(delta=ModelDelta(kind="reasoning", text="thinking")),
        ModelStreamEvent(delta=ModelDelta(kind="text", text="decision")),
    ]
    assert events[-1].result is not None
    assert events[-1].result.decision == {"action": "finish", "content": "done"}
    assert gateway.last_result is events[-1].result


@pytest.mark.asyncio
async def test_provider_stream_keeps_normalized_error_after_partial_deltas():
    class RateLimitError(Exception):
        pass

    class FailingStream:
        def __aiter__(self):
            return self

        async def __anext__(self):
            raise RateLimitError("sensitive provider detail")

    completions = FakeCompletions()

    async def create(**kwargs):
        completions.calls.append(kwargs)
        return FailingStream()

    completions.create = create
    adapter = OpenAICompatibleModelAdapter(FakeClient(completions), provider="openai")

    deltas = [
        delta
        async for delta in adapter.stream(
            messages=[{"role": "user", "content": "hello"}],
            model="test-model",
        )
    ]

    assert deltas[-1].kind == "error"
    assert deltas[-1].error_code == "rate_limited"
    assert adapter.last_result is not None
    assert adapter.last_result.status == "failed"
    assert adapter.last_result.error_code == "rate_limited"
    assert "sensitive provider detail" not in str(adapter.last_result.model_dump())


@pytest.mark.asyncio
async def test_gateway_keeps_synthesize_signature_and_records_safe_result():
    completions = FakeCompletions(response=response(content="final"))
    client = FakeClient(completions)
    gateway = OpenAIModelGateway(
        api_key="test-key",
        base_url="https://example.test/v1",
        model="test-model",
        client=client,
    )
    trace = AgentTrace(agent_name="model-test")

    with bind_trace(trace):
        text = await gateway.synthesize(
            goal="goal",
            messages=[{"role": "user", "content": "hello"}],
            results=[],
        )

    assert text == "final"
    assert gateway.last_result is not None
    assert gateway.last_result.provider == "openai-compatible"
    events = [event for step in trace.steps for event in step.events]
    model_events = [event for event in events if event.event_type == TraceEventType.MODEL_CALL]
    assert model_events
    assert model_events[0].data["provider"] == "openai-compatible"
    assert "test-key" not in str(model_events[0].data)
    assert "hello" not in str(model_events[0].data)


@pytest.mark.asyncio
async def test_gateway_accepts_only_provider_neutral_context_snapshot():
    completions = FakeCompletions(response=response(content='{"action":"finish"}'))
    gateway = OpenAIModelGateway(
        api_key="test-key",
        base_url="https://example.test/v1",
        model="test-model",
        client=FakeClient(completions),
    )
    snapshot = ContextManager(
        ExecutionContext(
            principal_id=42,
            tenant_id="tenant-a",
            role="admin",
            scope=frozenset({"tenant:read"}),
            run_id="run-1",
            trace_id="trace-1",
            capability_allowlist=frozenset({"catalog.search"}),
        )
    ).build_snapshot()

    await gateway.infer(
        goal="goal",
        messages=[{"role": "user", "content": "hello"}],
        context=snapshot.model_dump(mode="json"),
    )

    provider_messages = completions.calls[0]["messages"]
    serialized = str(provider_messages)
    assert "principal_id" not in serialized
    assert "tenant_id" not in serialized
    assert "catalog.search" in serialized
    assert "snapshot_hash" in serialized


@pytest.mark.asyncio
async def test_gateway_infer_prompt_describes_required_decision_fields():
    completions = FakeCompletions(response=response(content='{"action":"respond","content":"done"}'))
    gateway = OpenAIModelGateway(
        api_key="test-key",
        base_url="https://example.test/v1",
        model="test-model",
        client=FakeClient(completions),
    )

    await gateway.infer(
        goal="goal",
        messages=[{"role": "user", "content": "hello"}],
    )

    instruction = completions.calls[0]["messages"][-1]["content"]
    assert "decision_id" in instruction
    assert "content" in instruction
    assert 'the JSON field "arguments"' in instruction
    assert 'never use "public_arguments"' in instruction
    assert completions.calls[0]["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_gateway_infer_prompt_includes_public_capability_catalog():
    completions = FakeCompletions(
        response=response(
            content='{"action":"invoke","capability":"search_anime_advanced"}'
        )
    )
    gateway = OpenAIModelGateway(
        api_key="test-key",
        base_url="https://example.test/v1",
        model="test-model",
        client=FakeClient(completions),
    )

    await gateway.infer(
        goal="search anime",
        messages=[{"role": "user", "content": "search anime"}],
        capability_catalog=[
            {
                "public_name": "search_anime_advanced",
                "version": "v1",
                "description": "Search anime by keyword",
                "input_schema": {
                    "type": "object",
                    "properties": {"keyword": {"type": "string"}},
                    "required": ["keyword"],
                },
            }
        ],
    )

    serialized_messages = str(completions.calls[0]["messages"])
    assert "search_anime_advanced" in serialized_messages
    assert '"keyword"' in serialized_messages


@pytest.mark.asyncio
async def test_gateway_prompt_requires_bangumi_calendar_detail_followup():
    completions = FakeCompletions(response=response(content='{"action":"finish"}'))
    gateway = OpenAIModelGateway(
        api_key="test-key",
        base_url="https://example.test/v1",
        model="test-model",
        client=FakeClient(completions),
    )

    await gateway.infer(
        goal="整理本周值得关注的新番",
        messages=[{"role": "user", "content": "整理本周值得关注的新番"}],
        capability_catalog=[
            {
                "public_name": "get_bangumi_calendar",
                "version": "v1",
                "description": "Get the current Bangumi broadcast calendar",
                "input_schema": {"type": "object", "properties": {}, "required": []},
            },
            {
                "public_name": "get_anime_info_batch",
                "version": "v1",
                "description": "Get details for selected anime IDs",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "subject_ids": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "maxItems": 5,
                        }
                    },
                    "required": ["subject_ids"],
                },
            },
        ],
    )

    instruction = "\n".join(
        message["content"]
        for message in completions.calls[0]["messages"]
        if message["role"] == "system"
    )
    assert "get_anime_info_batch" in instruction
    assert "must not answer" in instruction


class FakeLangChainModel:
    async def ainvoke(self, _messages):
        return SimpleNamespace(
            content="answer",
            response_metadata={
                "finish_reason": "stop",
                "token_usage": {
                    "prompt_tokens": 2,
                    "completion_tokens": 3,
                    "total_tokens": 5,
                },
            },
        )

    async def astream(self, _messages):
        yield SimpleNamespace(content="part", additional_kwargs={})


@pytest.mark.asyncio
async def test_langchain_adapter_produces_same_result_contract():
    adapter = LangChainModelAdapter(
        FakeLangChainModel(), provider="deepseek", model_name="deepseek-chat"
    )

    result = await adapter.complete(messages=[{"role": "user", "content": "hello"}])
    deltas = [delta async for delta in adapter.stream(messages=[])]

    assert result.status == "completed"
    assert result.usage.total_tokens == 5
    assert deltas[0].kind == "text"
    assert deltas[0].text == "part"
