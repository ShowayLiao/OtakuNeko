"""Strict YAML configuration for evaluation gates."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
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
    timeout_seconds: float = Field(default=30, gt=0)
    max_concurrency: int = Field(default=1, ge=1)
    max_cost_usd: float = Field(default=0, ge=0)
    max_cost_per_call_usd: float = Field(default=0, ge=0)
    input_cost_per_million: float = Field(default=0, ge=0)
    output_cost_per_million: float = Field(default=0, ge=0)


class EvaluationConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    dataset: str
    tags: list[str] | None = None
    thresholds: dict[str, Threshold] = Field(default_factory=dict)
    report_path: str = ".runtime/evaluation/report.json"
    baseline: str | None = None
    target_factory: str | None = None
    judge_factory: str | None = None
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
