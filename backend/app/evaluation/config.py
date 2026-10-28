"""Strict YAML configuration for evaluation gates."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml  # type: ignore[import-untyped]
from pydantic import ConfigDict, BaseModel, Field, ValidationError

from app.evaluation.types import AgentMetadata


class Threshold(BaseModel):
    model_config = ConfigDict(extra="forbid")
    direction: Literal["min", "max"]
    value: float
    required: bool = True


class JudgeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    required: bool = False
    model: str = ""
    provider: str = ""
    rubric_version: str = "answer-quality-v1"
    rubric: dict[str, str] = Field(
        default_factory=lambda: {"quality": "Score response quality from 0 to 1"}
    )
    timeout_seconds: float = Field(default=30, gt=0)
    max_concurrency: int = Field(default=1, ge=1)
    max_cost_usd: float = Field(default=0, ge=0)
    max_cost_per_call_usd: float = Field(default=0, ge=0)
    input_cost_per_million: float = Field(default=0, ge=0)
    output_cost_per_million: float = Field(default=0, ge=0)


class ControlledEvaluationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    allowed_capabilities: list[str] = Field(min_length=1)
    external_fixtures: Literal["controlled-v1", "controlled-task-v1"] | None = None
    run_scoped_artifacts: bool = False


class DeepSeekOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    thinking: bool = True
    reasoning_effort: Literal["high", "max"] = "high"


class EvaluationRoutingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: bool = False
    version: Literal["keyword-v1", "model-v1"] = "keyword-v1"


class AgentCostConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    input_cost_per_million: float = Field(default=0, ge=0)
    output_cost_per_million: float = Field(default=0, ge=0)


class RuntimeBudgetConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    max_steps: int = Field(default=24, ge=0)
    max_tool_calls: int = Field(default=16, ge=0)
    max_model_calls: int = Field(default=8, ge=0)
    deadline_seconds: float = Field(default=120, gt=0)
    max_total_tokens: int = Field(default=100_000, ge=0)
    max_cost_usd: float = Field(default=10, ge=0)


class EvaluationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    dataset: str
    tags: list[str] | None = None
    thresholds: dict[str, Threshold] = Field(default_factory=dict)
    report_path: str = ".runtime/evaluation/report.json"
    baseline: str | None = None
    transcript_dir: str | None = None
    target_factory: str | None = None
    judge_factory: str | None = None
    human_reviews: str | None = None
    controlled: ControlledEvaluationConfig | None = None
    deepseek: DeepSeekOptions | None = None
    routing: EvaluationRoutingConfig = Field(default_factory=EvaluationRoutingConfig)
    runtime_budget: RuntimeBudgetConfig | None = None
    cost: AgentCostConfig | None = None
    agent: AgentMetadata = Field(
        default_factory=lambda: AgentMetadata(name="deterministic-runtime")
    )
    judge: JudgeConfig = Field(default_factory=JudgeConfig)


def load_config(path: str | Path) -> EvaluationConfig:
    config_path = Path(path)
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"{config_path}: unable to load config: {exc}") from exc
    try:
        return EvaluationConfig.model_validate(raw)
    except ValidationError as exc:
        raise ValueError(f"{config_path}: {exc}") from exc
