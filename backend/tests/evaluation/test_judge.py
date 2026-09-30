"""Judge availability, cache, and baseline behavior."""

from __future__ import annotations

import asyncio

import pytest

from app.evaluation.judge import (
    Baseline,
    BaselineMetric,
    BudgetedJudge,
    JudgeCache,
    JudgeRequest,
    JudgeScore,
    evaluate_judge,
)


class _Judge:
    def __init__(self, result=None, delay=0, error=None):
        self.result = result or JudgeScore(score=0.8)
        self.delay = delay
        self.error = error

    async def evaluate(self, request):
        await asyncio.sleep(self.delay)
        if self.error:
            raise self.error
        return self.result


def _request(**overrides):
    values = {
        "input_text": "question",
        "response_text": "answer",
        "rubric": {"relevance": "0..1"},
        "model": "model-a",
        "provider": "provider-a",
        "config": {"temperature": 0},
    }
    values.update(overrides)
    return JudgeRequest(**values)


def test_cache_key_includes_model_provider_rubric_and_config():
    cache = JudgeCache()
    cache.put(_request(), JudgeScore(score=0.9))

    assert cache.get(_request()) is not None
    assert cache.get(_request(model="model-b")) is None
    assert cache.get(_request(provider="provider-b")) is None
    assert cache.get(_request(rubric={"safety": "0..1"})) is None


@pytest.mark.asyncio
async def test_judge_timeout_is_visible_and_not_a_pass():
    result = await evaluate_judge(_Judge(delay=0.05), _request(), timeout=0.001)

    assert result.status == "unavailable"
    assert result.score is None
    assert "timeout" in result.error


@pytest.mark.asyncio
async def test_judge_exception_is_visible():
    result = await evaluate_judge(
        _Judge(error=RuntimeError("api_key=sk-secret provider down")),
        _request(),
        timeout=1,
    )

    assert result.status == "unavailable"
    assert result.error == "RuntimeError: judge_failed"
    assert "sk-secret" not in result.error


def test_baseline_supports_direction_tolerance_and_required_metrics():
    baseline = Baseline(
        dataset_version="v1",
        metrics=[
            BaselineMetric(
                metric="pass_rate",
                expected_value=1.0,
                tolerance=0.05,
                direction="min",
            ),
            BaselineMetric(
                metric="latency_ms",
                expected_value=100,
                tolerance=10,
                direction="max",
            ),
            BaselineMetric(
                metric="routing_accuracy",
                expected_value=1,
                required=True,
            ),
        ],
    )

    assert baseline.compare({"pass_rate": 0.96, "latency_ms": 109}) == [
        "missing required baseline metric: routing_accuracy"
    ]
    assert baseline.is_regression(111, "latency_ms")
    assert not baseline.is_regression(109, "latency_ms")


@pytest.mark.asyncio
async def test_budgeted_judge_blocks_calls_after_cost_limit():
    class CostlyJudge:
        def __init__(self):
            self.calls = 0

        async def evaluate(self, request):
            self.calls += 1
            return JudgeScore(score=0.8, cost_usd=0.6)

    delegate = CostlyJudge()
    judge = BudgetedJudge(
        delegate,
        max_cost_usd=0.5,
        max_cost_per_call_usd=0.5,
    )

    with pytest.raises(RuntimeError, match="budget"):
        await judge.evaluate(_request())
    with pytest.raises(RuntimeError, match="budget"):
        await judge.evaluate(_request(response_text="second"))
    assert delegate.calls == 1
