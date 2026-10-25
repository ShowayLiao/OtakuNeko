"""L5 PR benchmark gate tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.evaluation.config import load_config
from app.evaluation.dataset import load_dataset
from app.evaluation.l5_gate import (
    DEFAULT_BASELINE,
    build_diff,
    build_gate_report,
    load_baseline,
    run_gate,
)
from app.evaluation.types import (
    AgentMetadata,
    CaseResult,
    DeterministicScore,
    DimensionScore,
    EvalReport,
)

EXPECTED_IDS = {
    "l5-contract-respond",
    "l5-contract-tool",
    "l5-scenario-single-step",
    "l5-scenario-multi-step",
    "l5-scenario-error-recovery",
    "l5-scenario-write-approval",
}


def _failing_report() -> EvalReport:
    return EvalReport(
        dataset_version="v1-l5-failure",
        config_name="l5-failure",
        code_revision="test-revision",
        agent=AgentMetadata(name="test"),
        cases=[
            CaseResult(
                case_id="l5-failure-case",
                category="recovery",
                passed=False,
                run_id="run-123",
                trace_id="trace-123",
                deterministic=DeterministicScore(
                    case_id="l5-failure-case",
                    task_success=False,
                    dimensions=[
                        DimensionScore(
                            dimension="termination",
                            passed=False,
                            score=0.0,
                            detail="status expected=completed actual=failed",
                        )
                    ],
                ),
            )
        ],
        gate_failures=["threshold failed: pass_rate"],
    )


def test_baseline_covers_the_versioned_l5_datasets() -> None:
    baseline = load_baseline(DEFAULT_BASELINE)

    assert baseline is not None
    assert baseline["schema_version"] == 2
    assert set(baseline["cases"]) == EXPECTED_IDS
    assert all(record["passed"] for record in baseline["cases"].values())
    assert all("behavior" in record for record in baseline["cases"].values())
    assert baseline["versions"]["prompt"] == "decision-contract-v1"
    assert baseline["versions"]["dataset"]["l5-scenarios"] == "v1-l5-scenarios"
    assert baseline["versions"]["model"]["l5-contract"] == "entrypoint-fixture-v1"
    assert baseline["versions"]["code"]
    assert baseline["versions"]["environment"]["python"]
    assert baseline["thresholds"]["max_step_increase"] == 0


def test_gate_report_locates_failure_to_case_run_and_trace() -> None:
    gate = build_gate_report({"l5-failure": _failing_report()})

    assert gate["passed"] is False
    assert gate["failed_cases"] == ["l5-failure-case"]
    assert gate["threshold_failures"] == ["l5-failure: threshold failed: pass_rate"]
    case = gate["cases"][0]
    assert case["run_id"] == "run-123"
    assert case["trace_id"] == "trace-123"
    assert case["task_success"] is False
    assert case["failed_dimensions"] == [
        {
            "dimension": "termination",
            "detail": "status expected=completed actual=failed",
        }
    ]


def test_diff_reports_regressions_and_baseline_drift() -> None:
    gate = build_gate_report({"l5-failure": _failing_report()})
    diff = build_diff(
        gate,
        {
            "schema_version": 1,
            "cases": {
                "l5-failure-case": {"passed": True, "task_success": True},
                "removed-case": {"passed": True, "task_success": True},
            },
        },
    )

    assert diff["regressions"] == ["l5-failure-case"]
    assert diff["missing"] == ["removed-case"]
    assert diff["changed"] is True


@pytest.mark.asyncio
async def test_gate_runs_real_runtime_and_matches_baseline(tmp_path: Path) -> None:
    report, diff = await run_gate(
        (
            "evals/config/l5-contract.yaml",
            "evals/config/l5-scenarios.yaml",
        ),
        baseline_path=DEFAULT_BASELINE,
        report_path=tmp_path / "l5-gate.json",
        diff_path=tmp_path / "l5-gate-diff.json",
    )

    assert report["passed"] is True
    assert report["case_count"] == len(EXPECTED_IDS)
    assert diff == {
        "schema_version": 2,
        "regressions": [],
        "behavior_regressions": [],
        "fixed": [],
        "added": [],
        "missing": [],
        "changed": False,
    }
    versions = report["versions"]
    assert versions["prompt"] == "decision-contract-v1"
    assert versions["dataset"] == {
        "l5-contract": "v1-l5-contract",
        "l5-scenarios": "v1-l5-scenarios",
    }
    assert versions["model"]["l5-scenarios"] == "entrypoint-fixture-v1"
    assert versions["code"]
    assert versions["environment"]["python"]
    for case in report["cases"]:
        assert case["passed"] is True
        assert case["task_success"] is True
        assert isinstance(case["run_id"], str)
        assert isinstance(case["trace_id"], str)
        assert case["behavior"]["success"] is True
        assert case["behavior"]["tool_accuracy"] == 1.0
        assert case["behavior"]["argument_accuracy"] == 1.0
        assert isinstance(case["behavior"]["steps"], int)
        assert case["behavior"]["termination"] == "completed"
    written = json.loads((tmp_path / "l5-gate.json").read_text(encoding="utf-8"))
    assert written["passed"] is True


@pytest.mark.asyncio
async def test_gate_blocks_on_baseline_drift(tmp_path: Path) -> None:
    baseline = json.loads(Path(DEFAULT_BASELINE).read_text(encoding="utf-8"))
    baseline["cases"] = {
        case_id: record
        for case_id, record in baseline["cases"].items()
        if case_id.startswith("l5-scenario-")
    }
    baseline["cases"]["l5-scenario-single-step"] = {
        "passed": False,
        "task_success": False,
    }
    del baseline["cases"]["l5-scenario-error-recovery"]
    baseline["cases"]["l5-ghost-case"] = {"passed": True, "task_success": True}
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")

    report, diff = await run_gate(
        ("evals/config/l5-scenarios.yaml",),
        baseline_path=baseline_path,
        report_path=tmp_path / "l5-gate.json",
        diff_path=tmp_path / "l5-gate-diff.json",
    )

    assert report["passed"] is False
    assert (
        "added without baseline: l5-scenario-error-recovery"
        in (report["baseline_failures"])
    )
    assert "missing from report: l5-ghost-case" in report["baseline_failures"]
    assert diff["fixed"] == ["l5-scenario-single-step"]
    assert diff["added"] == ["l5-scenario-error-recovery"]
    assert diff["missing"] == ["l5-ghost-case"]


def test_l5_configs_reference_versioned_datasets() -> None:
    for config_path in (
        "evals/config/l5-contract.yaml",
        "evals/config/l5-scenarios.yaml",
    ):
        config = load_config(config_path)
        dataset = load_dataset(config.dataset)
        assert dataset.cases


BASE_BEHAVIOR = {
    "success": True,
    "tool_accuracy": 1.0,
    "argument_accuracy": 1.0,
    "steps": 2,
    "tokens": 10,
    "tool_errors": 0,
    "termination": "completed",
    "recovery": False,
}


def _behavior_report(behavior: dict) -> dict:
    return {
        "cases": [
            {
                "case_id": "behavior-case",
                "passed": True,
                "task_success": True,
                "behavior": behavior,
            }
        ]
    }


def _behavior_baseline(behavior: dict, thresholds: dict | None = None) -> dict:
    return {
        "schema_version": 2,
        "thresholds": thresholds or {},
        "cases": {
            "behavior-case": {
                "passed": True,
                "task_success": True,
                "behavior": behavior,
            }
        },
    }


@pytest.mark.parametrize(
    ("metric", "baseline_value", "current_value"),
    [
        ("steps", 2, 3),
        ("tokens", 10, 11),
        ("tool_errors", 0, 1),
        ("tool_accuracy", 1.0, 0.0),
        ("argument_accuracy", 1.0, 0.0),
        ("termination", "completed", "timeout"),
    ],
)
def test_success_with_behavior_degradation_is_reported(
    metric: str,
    baseline_value: object,
    current_value: object,
) -> None:
    baseline = _behavior_baseline({**BASE_BEHAVIOR, metric: baseline_value})
    current = _behavior_report({**BASE_BEHAVIOR, metric: current_value})

    diff = build_diff(current, baseline)

    assert diff["regressions"] == []
    assert diff["behavior_regressions"] == [
        {
            "case_id": "behavior-case",
            "metric": metric,
            "baseline": baseline_value,
            "current": current_value,
        }
    ]
    assert diff["changed"] is True


def test_recovery_loss_is_reported() -> None:
    diff = build_diff(
        _behavior_report({**BASE_BEHAVIOR, "recovery": False}),
        _behavior_baseline({**BASE_BEHAVIOR, "recovery": True}),
    )

    assert [item["metric"] for item in diff["behavior_regressions"]] == ["recovery"]


def test_threshold_tolerance_allows_bounded_step_increase() -> None:
    diff = build_diff(
        _behavior_report({**BASE_BEHAVIOR, "steps": 3}),
        _behavior_baseline(
            {**BASE_BEHAVIOR, "steps": 2},
            {"max_step_increase": 1},
        ),
    )

    assert diff["behavior_regressions"] == []


@pytest.mark.asyncio
async def test_success_but_step_degradation_blocks_the_gate(tmp_path: Path) -> None:
    baseline = json.loads(Path(DEFAULT_BASELINE).read_text(encoding="utf-8"))
    baseline["cases"] = {
        case_id: record
        for case_id, record in baseline["cases"].items()
        if case_id.startswith("l5-scenario-")
    }
    baseline["cases"]["l5-scenario-multi-step"]["behavior"]["steps"] = 2
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")

    report, diff = await run_gate(
        ("evals/config/l5-scenarios.yaml",),
        baseline_path=baseline_path,
        report_path=tmp_path / "l5-gate.json",
        diff_path=tmp_path / "l5-gate-diff.json",
    )

    assert all(case["passed"] for case in report["cases"])
    assert report["passed"] is False
    assert diff["regressions"] == []
    assert diff["behavior_regressions"] == [
        {
            "case_id": "l5-scenario-multi-step",
            "metric": "steps",
            "baseline": 2,
            "current": 3,
        }
    ]
    assert any(
        "behavior regression: l5-scenario-multi-step steps" in failure
        for failure in report["baseline_failures"]
    )
