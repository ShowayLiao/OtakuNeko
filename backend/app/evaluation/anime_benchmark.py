"""Versioned loader and safe EvalCase mapping for Anime Agent Benchmark v1.

The design package remains the source of truth for prompts and scenario
oracles. Only a scenario's user messages are converted to an ``EvalCase``;
hard checks, quality rubrics, and fixture data never enter model-visible task
metadata.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.evaluation.anime_fixtures import AnimeFixtureSet, load_anime_fixture_set
from app.evaluation.types import (
    AnswerQualitySpec,
    ApprovalFixture,
    Category,
    CaseAssertions,
    EvalCase,
    ExecutionFixture,
    InputMessage,
    ScriptEvent,
    UserFixture,
)

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_PACKAGE = _REPO_ROOT / "otakuneko-benchmark-v1"
_FIXTURE_FILES = (
    "calendar.synthetic.json",
    "catalog.synthetic.json",
    "search-snapshots.synthetic.json",
    "user.synthetic.json",
)


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AnimeBenchmarkTurn(_StrictModel):
    role: Literal["user", "assistant"]
    session: str = Field(min_length=1)
    trigger: str = Field(min_length=1)
    content: str


class AnimeHardCheck(_StrictModel):
    rule: str = Field(min_length=1)
    args: dict[str, Any] = Field(default_factory=dict)


class AnimeBenchmarkScenario(_StrictModel):
    schema_version: Literal[1]
    id: str = Field(pattern=r"^ANIME-[0-9]{3}$")
    title: str = Field(min_length=1)
    group: str = Field(min_length=1)
    priority: str = Field(min_length=1)
    environment: dict[str, Any]
    turns: tuple[AnimeBenchmarkTurn, ...] = Field(min_length=1)
    tool_faults: tuple[dict[str, Any], ...] = ()
    requires_confirmation: bool = False
    max_tool_calls: int = Field(ge=1)
    hard_checks: tuple[AnimeHardCheck, ...] = ()
    quality_checks: tuple[str, ...] = ()
    notes: str = ""


class AnimeBenchmarkSuite(_StrictModel):
    dataset_version: str
    content_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    cases: tuple[AnimeBenchmarkScenario, ...]
    fixture_set: AnimeFixtureSet

    def case_by_id(self, case_id: str) -> AnimeBenchmarkScenario:
        for case in self.cases:
            if case.id == case_id:
                return case
        raise KeyError(case_id)


SUPPORTED_SCENARIO_IDS = frozenset(
    {
        "ANIME-001",
        "ANIME-002",
        "ANIME-003",
        "ANIME-005",
        "ANIME-007",
        "ANIME-008",
        "ANIME-009",
        "ANIME-011",
    }
)

UNSUPPORTED_SCENARIO_REASONS = {
    "ANIME-004": (
        "当前 Harness 没有隔离的一次性日历事件能力；Schedule 模型只表示每周重复计划。"
    ),
    "ANIME-006": "当前 headless live runner 每个 Case 只运行一个 Runtime Run，不能保持真实多轮会话。",
    "ANIME-010": "当前聊天路径只读取 Memory；没有在一次对话后写入长期偏好的生产 Runtime 路径。",
    "ANIME-012": "该集成场景依赖一次性日历事件写入，当前 Harness 没有隔离该副作用的能力。",
}


def _scenario_path(package_dir: Path) -> Path:
    return package_dir / "cases" / "anime_benchmark_v1.jsonl"


def _suite_digest(package_dir: Path, scenario_text: str) -> str:
    digest = hashlib.sha256()
    digest.update(scenario_text.replace("\r\n", "\n").replace("\r", "\n").encode())
    fixture_dir = package_dir / "fixtures"
    for name in _FIXTURE_FILES:
        digest.update(name.encode("utf-8"))
        digest.update((fixture_dir / name).read_bytes())
    return digest.hexdigest()


def load_anime_benchmark_suite(
    package_dir: str | Path | None = None,
) -> AnimeBenchmarkSuite:
    """Load the fixed v1 scenarios and explicitly synthetic fixtures."""
    root = Path(package_dir) if package_dir is not None else _DEFAULT_PACKAGE
    scenario_file = _scenario_path(root)
    try:
        text = scenario_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(
            f"{scenario_file}: unable to read benchmark scenarios"
        ) from exc

    scenarios: list[AnimeBenchmarkScenario] = []
    seen: set[str] = set()
    for line_number, raw in enumerate(text.splitlines(), 1):
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        try:
            parsed = json.loads(raw)
            scenario = AnimeBenchmarkScenario.model_validate(parsed)
        except (json.JSONDecodeError, ValidationError) as exc:
            raise ValueError(
                f"{scenario_file}:{line_number}: invalid scenario"
            ) from exc
        if scenario.id in seen:
            raise ValueError(
                f"{scenario_file}:{line_number}: duplicate id {scenario.id}"
            )
        seen.add(scenario.id)
        if scenario.environment.get("fixture_set") != "synthetic_v1":
            raise ValueError(f"{scenario.id}: expected synthetic_v1 fixture marker")
        if scenario.environment.get("write_scope") != "isolated_sandbox_only":
            raise ValueError(f"{scenario.id}: writes must be isolated")
        scenarios.append(scenario)

    expected_ids = {f"ANIME-{index:03d}" for index in range(1, 13)}
    if seen != expected_ids:
        missing = sorted(expected_ids - seen)
        extra = sorted(seen - expected_ids)
        raise ValueError(
            f"benchmark scenario ids mismatch: missing={missing}, extra={extra}"
        )

    fixtures = load_anime_fixture_set(root / "fixtures")
    if fixtures.catalog.get("synthetic") is not True:
        raise ValueError("anime benchmark catalog must be marked synthetic")
    return AnimeBenchmarkSuite(
        dataset_version="anime-agent-benchmark-v1",
        content_digest=_suite_digest(root, text),
        cases=tuple(scenarios),
        fixture_set=fixtures,
    )


def _category(group: str) -> Category:
    return {
        "recommendation": Category.RECOMMENDATION,
        "research": Category.ANIME_KNOWLEDGE,
        "planning": Category.COMPANION,
        "state": Category.COMPANION,
        "multi_turn": Category.RECOVERY,
        "resilience": Category.RECOVERY,
        "entity": Category.ANIME_KNOWLEDGE,
        "memory": Category.COMPANION,
        "security": Category.SAFETY,
        "integration": Category.COMPANION,
    }.get(group, Category.ANIME_KNOWLEDGE)


def scenario_to_eval_case(
    scenario: AnimeBenchmarkScenario,
    *,
    user_id: int,
) -> EvalCase:
    """Map a single-turn prompt to the existing live Runtime evaluator."""
    if len(scenario.turns) != 1 or scenario.requires_confirmation:
        raise ValueError(
            f"{scenario.id}: multi-turn scenario is not single-run supported"
        )
    turn = scenario.turns[0]
    if turn.role != "user":
        raise ValueError(f"{scenario.id}: first live turn must be a user message")
    return EvalCase(
        id=scenario.id,
        category=_category(scenario.group),
        input_messages=[InputMessage(role="user", content=turn.content)],
        user_fixture=UserFixture(user_id=user_id),
        assertions=CaseAssertions(
            response_schema="text",
            max_latency_ms=120_000,
            max_calls=scenario.max_tool_calls,
        ),
        fixtures=ExecutionFixture(
            events=[ScriptEvent(type="message_chunk", content="live-provider-output")]
        ),
        tags=["anime-benchmark-v1", scenario.group, scenario.priority],
        answer_quality=AnswerQualitySpec(
            rubric="\n".join(scenario.quality_checks),
            min_score=0.7,
            required=False,
        ),
        approvals=(
            [ApprovalFixture(action="update_collection")]
            if scenario.id == "ANIME-005"
            else []
        ),
    )


def expected_router_agent(scenario: AnimeBenchmarkScenario) -> str:
    """Current v1 routing diagnostic; it never gates final task success."""
    return "recommendation" if scenario.group == "recommendation" else "fallback"
