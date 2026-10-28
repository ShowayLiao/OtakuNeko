"""L5 PR benchmark gate tests."""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
import socket

import pytest

from app.evaluation import l5_gate
from app.evaluation.config import load_config
from app.evaluation.dataset import load_dataset
from app.evaluation.l5_gate import (
    DEFAULT_BASELINE,
    DEFAULT_THRESHOLDS,
    _version_failures,
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
    "l5-scenario-evidence",
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
    assert baseline["versions"]["dataset"]["l5-scenarios"] == "v3-l5-scenarios"
    assert baseline["versions"]["model"]["l5-contract"] == "entrypoint-fixture-v1"
    assert baseline["versions"]["code"]
    assert baseline["versions"]["environment"]["python"]
    assert len(baseline["versions"]["digest"]["l5-scenarios"]) == 64
    assert len(baseline["versions"]["digest"]["l5-contract"]) == 64
    assert baseline["thresholds"]["max_step_increase"] == 0
    assert all(
        record["behavior"]["tokens"] > 0 for record in baseline["cases"].values()
    )


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
            "evals/config/l5-contract-v2.yaml",
            "evals/config/l5-scenarios-v3.yaml",
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
        "l5-contract": "v2-l5-contract",
        "l5-scenarios": "v3-l5-scenarios",
    }
    assert len(versions["digest"]["l5-scenarios"]) == 64
    assert len(versions["digest"]["l5-contract"]) == 64
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
        assert case["behavior"]["tokens"] > 0
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
        ("evals/config/l5-scenarios-v3.yaml",),
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
        "evals/config/l5-contract-v2.yaml",
        "evals/config/l5-scenarios-v3.yaml",
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
        ("evals/config/l5-scenarios-v3.yaml",),
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


def _versions(
    *,
    dataset: str = "v2-l5-scenarios",
    model: str = "entrypoint-fixture-v1",
    prompt: str = "decision-contract-v1",
    digest: str | None = "a" * 64,
) -> dict:
    versions: dict = {
        "dataset": {"l5-scenarios": dataset},
        "model": {"l5-scenarios": model},
        "prompt": prompt,
    }
    if digest is not None:
        versions["digest"] = {"l5-scenarios": digest}
    return versions


def test_matching_versions_produce_no_failures() -> None:
    assert _version_failures({"versions": _versions()}, {"versions": _versions()}) == []


def test_dataset_version_mismatch_blocks_the_gate() -> None:
    failures = _version_failures(
        {"versions": _versions(dataset="v2-l5-scenarios")},
        {"versions": _versions(dataset="v1-l5-scenarios")},
    )

    assert failures == [
        "dataset version mismatch: l5-scenarios "
        "baseline=v1-l5-scenarios current=v2-l5-scenarios"
    ]


def test_missing_version_metadata_blocks_the_gate() -> None:
    failures = _version_failures({"versions": {}}, {"versions": {}})

    assert "baseline version metadata missing: dataset" in failures
    assert "baseline version metadata missing: model" in failures
    assert "baseline version metadata missing: prompt" in failures
    assert "baseline version metadata missing: digest" in failures


def test_missing_digest_metadata_blocks_the_gate() -> None:
    current = _versions()
    baseline = {key: value for key, value in current.items() if key != "digest"}

    failures = _version_failures({"versions": current}, {"versions": baseline})

    assert failures == ["baseline version metadata missing: digest"]


def test_empty_baseline_digest_blocks_the_gate() -> None:
    failures = _version_failures(
        {"versions": _versions()},
        {"versions": _versions(digest="")},
    )

    assert failures == ["baseline dataset digest missing: l5-scenarios"]


def test_load_baseline_rejects_non_integer_thresholds(tmp_path: Path) -> None:
    payload = json.loads(Path(DEFAULT_BASELINE).read_text(encoding="utf-8"))
    payload["thresholds"]["max_step_increase"] = True
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match="invalid L5 gate baseline"):
        load_baseline(path)


def test_dataset_digest_mismatch_blocks_the_gate() -> None:
    failures = _version_failures(
        {"versions": _versions(digest="b" * 64)},
        {"versions": _versions(digest="a" * 64)},
    )

    assert failures == [
        f"dataset digest mismatch: l5-scenarios baseline={'a' * 64} current={'b' * 64}"
    ]


@pytest.mark.asyncio
async def test_update_baseline_preserves_custom_thresholds(tmp_path: Path) -> None:
    baseline_payload = json.loads(Path(DEFAULT_BASELINE).read_text(encoding="utf-8"))
    baseline_payload["thresholds"]["max_step_increase"] = 1
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(baseline_payload), encoding="utf-8")

    report, _diff = await run_gate(
        ("evals/config/l5-contract-v2.yaml", "evals/config/l5-scenarios-v3.yaml"),
        baseline_path=baseline_path,
        report_path=tmp_path / "l5-gate.json",
        diff_path=tmp_path / "l5-gate-diff.json",
        update_baseline=True,
    )

    assert report["passed"] is True
    updated = json.loads(baseline_path.read_text(encoding="utf-8"))
    assert updated["thresholds"]["max_step_increase"] == 1


@pytest.mark.asyncio
async def test_update_baseline_recovers_from_invalid_baseline(tmp_path: Path) -> None:
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text("{not json", encoding="utf-8")
    report_path = tmp_path / "l5-gate.json"

    report, _diff = await run_gate(
        ("evals/config/l5-contract-v2.yaml", "evals/config/l5-scenarios-v3.yaml"),
        baseline_path=baseline_path,
        report_path=report_path,
        diff_path=tmp_path / "l5-gate-diff.json",
        update_baseline=True,
    )

    assert report["passed"] is True
    updated = load_baseline(baseline_path)
    assert updated is not None
    assert updated["thresholds"] == DEFAULT_THRESHOLDS
    assert report_path.is_file()


@pytest.mark.asyncio
async def test_gate_records_version_failures_in_the_diff(tmp_path: Path) -> None:
    baseline = json.loads(Path(DEFAULT_BASELINE).read_text(encoding="utf-8"))
    baseline["versions"]["dataset"]["l5-scenarios"] = "v1-l5-scenarios"
    baseline_path = tmp_path / "baseline.json"
    baseline_path.write_text(json.dumps(baseline), encoding="utf-8")

    report, diff = await run_gate(
        ("evals/config/l5-scenarios-v3.yaml",),
        baseline_path=baseline_path,
        report_path=tmp_path / "l5-gate.json",
        diff_path=tmp_path / "l5-gate-diff.json",
    )

    expected = (
        "dataset version mismatch: l5-scenarios "
        "baseline=v1-l5-scenarios current=v3-l5-scenarios"
    )
    assert report["passed"] is False
    assert expected in report["baseline_failures"]
    assert diff["version_failures"] == [expected]
    assert diff["changed"] is True


@pytest.mark.asyncio
async def test_run_gate_installs_offline_guard(monkeypatch) -> None:
    entered: list[bool] = []
    observed: list[Exception] = []
    real_offline = l5_gate.offline_network

    @contextmanager
    def tracking_offline():
        entered.append(True)
        with real_offline():
            yield

    async def fake_run_evaluation(*_args, **_kwargs):
        try:
            socket.getaddrinfo("example.com", 80)
        except Exception as exc:
            observed.append(exc)
            raise RuntimeError("offline probe complete") from exc
        raise AssertionError("offline guard did not block DNS")

    monkeypatch.setattr(l5_gate, "offline_network", tracking_offline)
    monkeypatch.setattr(l5_gate, "run_evaluation", fake_run_evaluation)

    with pytest.raises(RuntimeError, match="offline probe complete"):
        await run_gate(("evals/config/l5-scenarios-v3.yaml",))

    assert entered == [True]
    assert observed
    assert "network disabled" in str(observed[0])


@pytest.mark.asyncio
async def test_gate_blocks_missing_transcripts_without_changing_runtime_status(
    tmp_path, monkeypatch
):
    def fail_write(*args, **kwargs):
        raise OSError("synthetic export failure")

    monkeypatch.setattr("app.evaluation.entrypoint.write_transcript", fail_write)
    report, diff = await run_gate(
        l5_gate.DEFAULT_CONFIGS,
        report_path=tmp_path / "gate.json",
        diff_path=tmp_path / "diff.json",
    )
    assert report["passed"] is False
    assert len(report["failed_cases"]) == report["case_count"] == 7
    for case in report["cases"]:
        assert case["artifact_error"] == "transcript_export_failed"
        assert case["behavior"]["termination"] == "completed"
        assert case["task_success"] is True
        assert case["run_id"] == case["trace_id"] == f"eval-{case['case_id']}"
    assert len(diff["regressions"]) == 7
