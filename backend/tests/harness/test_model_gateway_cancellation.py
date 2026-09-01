from __future__ import annotations

import asyncio

import pytest

from app.harness.budget import (
    CancellationToken,
    DeadlineExceededError,
    RunCancellationError,
)
from app.harness.model_gateway import OpenAICompatibleModelAdapter, OpenAIModelGateway
from app.harness.model_types import ModelCallResult, ModelDelta


class BlockingAdapter:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.finished = asyncio.Event()

    async def complete(self, **kwargs) -> ModelCallResult:
        self.started.set()
        try:
            await asyncio.sleep(60)
        finally:
            self.finished.set()
        raise AssertionError("the provider operation should be cancelled")


class BlockingStreamingAdapter:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.finished = asyncio.Event()

    async def complete(self, **kwargs) -> ModelCallResult:
        raise AssertionError("the test must use the streaming adapter")

    async def _stream(self):
        self.started.set()
        try:
            await asyncio.sleep(60)
        finally:
            self.finished.set()
        yield None

    def stream(self, **kwargs):
        return self._stream()


class CancelledAdapter:
    async def complete(self, **kwargs) -> ModelCallResult:
        raise asyncio.CancelledError()


class FakeCompletions:
    async def create(self, **kwargs):
        raise asyncio.CancelledError()


class FakeClient:
    def __init__(self) -> None:
        self.chat = type("Chat", (), {"completions": FakeCompletions()})()


@pytest.mark.asyncio
async def test_gateway_cancels_provider_task_and_waits_for_cleanup() -> None:
    adapter = BlockingAdapter()
    gateway = OpenAIModelGateway(
        api_key="test-key",
        base_url="https://example.test/v1",
        model="test-model",
        adapter=adapter,
    )
    cancellation = CancellationToken()
    operation = asyncio.create_task(
        gateway.infer(
            goal="goal",
            messages=[],
            cancellation=cancellation,
            deadline=5.0,
        )
    )

    await asyncio.wait_for(adapter.started.wait(), timeout=1)
    cancellation.cancel()

    with pytest.raises(RunCancellationError):
        await asyncio.wait_for(operation, timeout=1)
    assert adapter.finished.is_set()
    assert operation.done()


@pytest.mark.asyncio
async def test_gateway_maps_deadline_and_reclaims_provider_task() -> None:
    adapter = BlockingAdapter()
    gateway = OpenAIModelGateway(
        api_key="test-key",
        base_url="https://example.test/v1",
        model="test-model",
        adapter=adapter,
    )

    with pytest.raises(DeadlineExceededError):
        await asyncio.wait_for(
            gateway.infer(
                goal="goal",
                messages=[],
                deadline=0.01,
            ),
            timeout=0.2,
        )
    assert adapter.finished.is_set()


@pytest.mark.asyncio
async def test_gateway_stream_infer_cancels_provider_iterator_and_waits_for_cleanup() -> None:
    adapter = BlockingStreamingAdapter()
    gateway = OpenAIModelGateway(
        api_key="test-key",
        base_url="https://example.test/v1",
        model="test-model",
        adapter=adapter,
    )
    cancellation = CancellationToken()

    async def consume() -> None:
        async for _event in gateway.stream_infer(
            goal="goal",
            messages=[],
            cancellation=cancellation,
            deadline=5.0,
        ):
            pass

    operation = asyncio.create_task(consume())
    await asyncio.wait_for(adapter.started.wait(), timeout=1)
    cancellation.cancel()

    with pytest.raises(RunCancellationError):
        await asyncio.wait_for(operation, timeout=1)
    assert adapter.finished.is_set()


@pytest.mark.asyncio
async def test_gateway_stream_infer_enforces_one_deadline_across_chunks() -> None:
    class SlowChunksAdapter:
        def __init__(self) -> None:
            self.finished = asyncio.Event()

        async def complete(self, **kwargs) -> ModelCallResult:
            raise AssertionError("the test must use the streaming adapter")

        async def _stream(self):
            try:
                yield ModelDelta(kind="text", text="first")
                await asyncio.sleep(60)
            finally:
                self.finished.set()

        def stream(self, **kwargs):
            return self._stream()

    adapter = SlowChunksAdapter()
    gateway = OpenAIModelGateway(
        api_key="test-key",
        base_url="https://example.test/v1",
        model="test-model",
        adapter=adapter,
    )

    with pytest.raises(DeadlineExceededError):
        async for _event in gateway.stream_infer(
            goal="goal",
            messages=[],
            deadline=0.01,
        ):
            pass
    assert adapter.finished.is_set()


@pytest.mark.asyncio
async def test_provider_cancelled_error_is_not_normalized_as_a_result() -> None:
    adapter = OpenAICompatibleModelAdapter(FakeClient(), provider="openai")

    with pytest.raises(asyncio.CancelledError):
        await adapter.complete(messages=[], model="test-model")


@pytest.mark.asyncio
async def test_gateway_preserves_provider_cancelled_result() -> None:
    result = ModelCallResult(
        provider="fake",
        model="test-model",
        operation="complete",
        status="cancelled",
        error_code="cancelled",
    )

    class ResultAdapter:
        async def complete(self, **kwargs) -> ModelCallResult:
            return result

    gateway = OpenAIModelGateway(
        api_key="test-key",
        base_url="https://example.test/v1",
        model="test-model",
        adapter=ResultAdapter(),
    )

    actual = await gateway.infer(goal="goal", messages=[])
    assert actual.status == "cancelled"
    assert actual.error_code == "cancelled"


@pytest.mark.asyncio
async def test_gateway_synthesis_uses_the_same_cancellation_boundary() -> None:
    adapter = BlockingAdapter()
    gateway = OpenAIModelGateway(
        api_key="test-key",
        base_url="https://example.test/v1",
        model="test-model",
        adapter=adapter,
    )
    cancellation = CancellationToken()
    operation = asyncio.create_task(
        gateway.synthesize(
            goal="goal",
            messages=[],
            results=[],
            cancellation=cancellation,
            deadline=5.0,
        )
    )

    await asyncio.wait_for(adapter.started.wait(), timeout=1)
    cancellation.cancel()

    with pytest.raises(RunCancellationError):
        await asyncio.wait_for(operation, timeout=1)
    assert adapter.finished.is_set()
