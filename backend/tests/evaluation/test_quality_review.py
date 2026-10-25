"""Judge/rubric version, human review, and functional-gate separation."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.evaluation import adapter, real_model
from app.evaluation.config import load_config
from app.evaluation.dataset import load_dataset
from app.evaluation.human_review import load_human_reviews
from app.evaluation.judge import (
    JudgeRequest,
    JudgeScore,
    OpenAICompatibleJudge,
    evaluate_judge,
    rubric_digest,
)
from app.evaluation.runner import run_case, run_evaluation
from app.evaluation.scripted_llm import ScriptedLLM


class _Judge:
    def __init__(self, score: float) -> None:
        self.score = score
        self.requests: list[JudgeRequest] = []

    async def evaluate(self, request: JudgeRequest) -> JudgeScore:
        self.requests.append(request)
        return JudgeScore(score=self.score, explanation="synthetic judge")


class _Gateway(ScriptedLLM):
    async def close(self) -> None:
        return None


def _case_and_gateway():
    dataset = load_dataset("evals/datasets/v1-real-model.jsonl")
    case = next(item for item in dataset.cases if item.id == "real-model-tool-time")
    events = [
        {
            "type": "tool_call_start",
            "name": "get_current_time",
            "arguments": {},
        },
        {"type": "message_chunk", "content": "The current time is noon."},
    ]
    from app.evaluation.types import ExecutionFixture, ScriptEvent

    case = case.model_copy(
        update={
            "fixtures": ExecutionFixture(
                events=[ScriptEvent.model_validate(event) for event in events]
            )
        }
    )
    return dataset, case


def _gateway_factory(case):
    def factory():
        return _Gateway(
            ScriptedLLM.script_steps(case.fixtures.events),
            provider="scripted",
            model="scripted-v1",
        )

    return factory


def _target(config, tmp_path: Path, monkeypatch, gateway_factory):
    monkeypatch.setattr(adapter, "OpenAIModelGateway", lambda **_: gateway_factory())
    return real_model.build_real_model_target(
        config,
        base_url="https://api.openai.com/v1",
        api_key="synthetic-evaluation-key",
        transcript_dir=tmp_path / "transcripts",
    )


@pytest.mark.asyncio
async def test_judge_records_rubric_version_and_digest() -> None:
    request = JudgeRequest(
        input_text="question",
        response_text="answer",
        rubric={"quality": "0..1"},
        rubric_version="rubric-v2",
        model="judge-model",
        provider="judge-provider",
    )
    outcome = await evaluate_judge(_Judge(0.8), request, timeout=1)

    assert outcome.status == "available"
    assert outcome.rubric_version == "rubric-v2"
    assert outcome.rubric_digest == rubric_digest({"quality": "0..1"}, "rubric-v2")


def test_judge_sends_deepseek_thinking_options(monkeypatch) -> None:
    captured: dict = {}

    class _Completions:
        async def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                choices=[
                    SimpleNamespace(message=SimpleNamespace(content='{"score": 0.8}'))
                ],
                usage=SimpleNamespace(prompt_tokens=1, completion_tokens=1),
            )

    class _Client:
        def __init__(self, **_kwargs) -> None:
            self.chat = SimpleNamespace(completions=_Completions())

    monkeypatch.setattr("openai.AsyncOpenAI", _Client)
    judge = OpenAICompatibleJudge(
        api_key="synthetic-key",
        base_url="https://api.deepseek.com",
        input_cost_per_million=0,
        output_cost_per_million=0,
        deepseek_options={"thinking": True, "reasoning_effort": "max"},
    )
    asyncio.run(
        judge.evaluate(
            JudgeRequest(
                input_text="question",
                response_text="answer",
                rubric={"quality": "0..1"},
                model="deepseek-flash",
                provider="deepseek",
            )
        )
    )

    assert captured["reasoning_effort"] == "max"
    assert captured["extra_body"] == {"thinking": {"type": "enabled"}}


@pytest.mark.asyncio
async def test_quality_score_does_not_change_l6_functional_outcome(
    monkeypatch, tmp_path: Path
) -> None:
    config = load_config("evals/config/real-model-quality.yaml")
    dataset, case = _case_and_gateway()
    target = _target(config, tmp_path, monkeypatch, _gateway_factory(case))
    judge = _Judge(0.0)

    case_result = await run_case(case, target, config=config, judge=judge)

    assert case_result.judge.status == "available"
    assert case_result.judge.quality_passed is False
    assert case_result.passed is False
    assert case_result.l6 is not None
    assert case_result.l6.outcome == "passed"
    assert case_result.l6.scores["task_success"] == 1.0

    dataset = dataset.model_copy(update={"cases": [case]})
    report = await run_evaluation(
        config,
        dataset,
        target,
        judge=judge,
    )

    assert report.aggregates["l6_functional_pass_rate"] == 1.0
    assert report.aggregates["quality_pass_rate"] == 0.0
    assert report.aggregates["judge_score"] == 0.0


@pytest.mark.asyncio
async def test_human_review_and_dispute_queue_point_to_redacted_transcript(
    monkeypatch, tmp_path: Path
) -> None:
    config = load_config("evals/config/real-model-quality.yaml")
    dataset, case = _case_and_gateway()
    review_path = tmp_path / "reviews.json"
    review_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "dataset_version": "v1-real-model",
                "cases": {
                    case.id: {
                        "reviewer": "reviewer-1",
                        "verdict": "accept",
                        "rubric_version": "answer-quality-v1",
                        "notes": "Functional answer is correct.",
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    config.human_reviews = str(review_path)
    target = _target(config, tmp_path, monkeypatch, _gateway_factory(case))

    report = await run_evaluation(
        config,
        dataset.model_copy(update={"cases": [case]}),
        target,
        judge=_Judge(0.0),
    )

    reviewed = report.cases[0]
    assert reviewed.human_review is not None
    assert reviewed.human_review.verdict == "accept"
    assert report.aggregates["human_review_count"] == 1
    assert report.aggregates["human_accept_count"] == 1
    assert report.aggregates["quality_human_disagreement_count"] == 1
    assert report.review_queue[0].reason == "human_accepts_quality_failure"

    queue_path = real_model._write_review_queue(
        tmp_path,
        report,
        tmp_path / "transcripts",
    )
    queue = json.loads(queue_path.read_text(encoding="utf-8"))
    entry = queue["entries"][0]
    assert entry["case_id"] == case.id
    transcript = Path(entry["transcript"])
    assert transcript.is_file()
    payload = json.loads(transcript.read_text(encoding="utf-8"))
    assert payload["redaction"]["provider_payload"] == "not exported"
    assert payload["redaction"]["argument_values"] == "omitted (keys only)"


def test_human_review_loader_fails_closed(tmp_path: Path) -> None:
    valid = tmp_path / "valid.json"
    valid.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "dataset_version": "v1-real-model",
                "cases": {},
            }
        ),
        encoding="utf-8",
    )
    assert load_human_reviews(valid, "v1-real-model") == {}

    with pytest.raises(ValueError, match="dataset version mismatch"):
        load_human_reviews(valid, "other-dataset")

    with pytest.raises(ValueError, match="file missing"):
        load_human_reviews(tmp_path / "missing.json", "v1-real-model")


def test_quality_config_records_rubric_and_human_reviews() -> None:
    config = load_config("evals/config/real-model-quality.yaml")

    assert config.judge.enabled is True
    assert config.judge.required is False
    assert config.judge.model == "deepseek-flash"
    assert config.judge.provider == "deepseek"
    assert config.judge.rubric_version == "answer-quality-v1"
    assert config.judge.rubric
    assert config.agent.model == "deepseek-flash"
    assert config.deepseek is not None
    assert config.deepseek.thinking is True
    assert config.deepseek.reasoning_effort == "max"
    assert config.human_reviews == "evals/reviews/v1-real-model.json"
    assert config.judge_factory == "app.evaluation.judge:create_openai_judge"
