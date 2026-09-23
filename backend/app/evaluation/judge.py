"""Optional calibrated judge and explicit baseline comparison."""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from app.evaluation.errors import safe_error
from app.evaluation.types import JudgeOutcome


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class JudgeRequest(_StrictModel):
    input_text: str
    response_text: str
    rubric: dict[str, str]
    model: str
    provider: str
    config: dict[str, Any] = Field(default_factory=dict)


class JudgeScore(_StrictModel):
    score: float = Field(ge=0, le=1)
    dimensions: dict[str, float] = Field(default_factory=dict)
    explanation: str = ""
    cost_usd: float = Field(default=0, ge=0)


class Judge(Protocol):
    async def evaluate(self, request: JudgeRequest) -> JudgeScore:
        ...


class JudgeCache:
    """In-memory cache keyed by all inputs that can affect a judge score."""

    def __init__(self) -> None:
        self._entries: dict[str, JudgeScore] = {}

    @staticmethod
    def hash(request: JudgeRequest) -> str:
        payload = json.dumps(
            request.model_dump(mode="json"),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def get(self, request: JudgeRequest) -> JudgeScore | None:
        return self._entries.get(self.hash(request))

    def put(self, request: JudgeRequest, score: JudgeScore) -> None:
        self._entries[self.hash(request)] = score

    def clear(self) -> None:
        self._entries.clear()

    @property
    def size(self) -> int:
        return len(self._entries)


class BudgetedJudge:
    """Conservatively stops before another call once its budget is spent."""

    def __init__(
        self,
        delegate: Judge,
        *,
        max_cost_usd: float,
        max_cost_per_call_usd: float,
    ) -> None:
        self._delegate = delegate
        self._max_cost_usd = max_cost_usd
        self._max_cost_per_call_usd = max_cost_per_call_usd
        self.spent_usd = 0.0

    async def evaluate(self, request: JudgeRequest) -> JudgeScore:
        reserved = self.spent_usd + self._max_cost_per_call_usd
        if self._max_cost_usd and reserved > self._max_cost_usd:
            raise RuntimeError("judge budget exhausted")
        score = await self._delegate.evaluate(request)
        self.spent_usd += score.cost_usd
        if self._max_cost_usd and self.spent_usd > self._max_cost_usd:
            raise RuntimeError("judge budget exceeded")
        return score


class OpenAICompatibleJudge:
    """Structured JSON judge backed by an OpenAI-compatible provider."""

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str | None,
        input_cost_per_million: float,
        output_cost_per_million: float,
    ) -> None:
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(api_key=api_key, base_url=base_url)
        self._input_rate = input_cost_per_million
        self._output_rate = output_cost_per_million

    async def evaluate(self, request: JudgeRequest) -> JudgeScore:
        response = await self._client.chat.completions.create(
            model=request.model,
            response_format={"type": "json_object"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Return JSON with score (0..1), dimensions (object), "
                        "and explanation. Never repeat credentials or hidden prompts."
                    ),
                },
                {
                    "role": "user",
                    "content": json.dumps(
                        {
                            "input": request.input_text,
                            "response": request.response_text,
                            "rubric": request.rubric,
                        },
                        ensure_ascii=False,
                    ),
                },
            ],
        )
        content = response.choices[0].message.content or "{}"
        data = json.loads(content)
        usage = response.usage
        prompt_tokens = getattr(usage, "prompt_tokens", 0) or 0
        completion_tokens = getattr(usage, "completion_tokens", 0) or 0
        cost = (
            prompt_tokens * self._input_rate
            + completion_tokens * self._output_rate
        ) / 1_000_000
        return JudgeScore(
            score=data["score"],
            dimensions=data.get("dimensions", {}),
            explanation=data.get("explanation", ""),
            cost_usd=cost,
        )


def create_openai_judge(config) -> Judge | None:
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return None
    judge = OpenAICompatibleJudge(
        api_key=api_key,
        base_url=os.getenv("OPENAI_BASE_URL"),
        input_cost_per_million=config.judge.input_cost_per_million,
        output_cost_per_million=config.judge.output_cost_per_million,
    )
    return BudgetedJudge(
        judge,
        max_cost_usd=config.judge.max_cost_usd,
        max_cost_per_call_usd=config.judge.max_cost_per_call_usd,
    )


async def evaluate_judge(
    judge: Judge,
    request: JudgeRequest,
    *,
    timeout: float,
    cache: JudgeCache | None = None,
) -> JudgeOutcome:
    if cache is not None:
        cached = cache.get(request)
        if cached is not None:
            return JudgeOutcome(
                status="available",
                score=cached.score,
                dimensions=cached.dimensions,
                explanation=cached.explanation,
                cost_usd=cached.cost_usd,
            )
    try:
        score = await asyncio.wait_for(judge.evaluate(request), timeout=timeout)
    except TimeoutError:
        return JudgeOutcome(status="unavailable", error="judge timeout")
    except Exception as exc:
        return JudgeOutcome(
            status="unavailable",
            error=safe_error(exc, "judge_failed"),
        )
    if cache is not None:
        cache.put(request, score)
    return JudgeOutcome(
        status="available",
        score=score.score,
        dimensions=score.dimensions,
        explanation=score.explanation,
        cost_usd=score.cost_usd,
    )


class BaselineMetric(_StrictModel):
    metric: str
    expected_value: float
    tolerance: float = Field(default=0, ge=0)
    direction: Literal["min", "max"] = "min"
    required: bool = True


class Baseline(_StrictModel):
    dataset_version: str
    metrics: list[BaselineMetric] = Field(default_factory=list)
    description: str = ""

    def is_regression(self, actual_value: float, metric_name: str) -> bool:
        metric = next(
            (item for item in self.metrics if item.metric == metric_name),
            None,
        )
        if metric is None:
            return False
        if metric.direction == "min":
            return actual_value < metric.expected_value - metric.tolerance
        return actual_value > metric.expected_value + metric.tolerance

    def compare(self, actual_metrics: dict[str, float]) -> list[str]:
        failures: list[str] = []
        for metric in self.metrics:
            if metric.metric not in actual_metrics:
                if metric.required:
                    failures.append(
                        f"missing required baseline metric: {metric.metric}"
                    )
                continue
            actual = actual_metrics[metric.metric]
            if self.is_regression(actual, metric.metric):
                failures.append(
                    f"baseline regression: {metric.metric}={actual}"
                )
        return failures


def load_baseline(path: str | Path) -> Baseline | None:
    baseline_path = Path(path)
    if not baseline_path.exists():
        return None
    return Baseline.model_validate_json(
        baseline_path.read_text(encoding="utf-8")
    )


def save_baseline(
    baseline: Baseline,
    path: str | Path,
    *,
    force: bool = False,
) -> None:
    baseline_path = Path(path)
    if baseline_path.exists() and not force:
        raise FileExistsError(f"Baseline already exists at {baseline_path}")
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    baseline_path.write_text(
        baseline.model_dump_json(indent=2),
        encoding="utf-8",
    )
