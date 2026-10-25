"""PR gate contract for the L5 deterministic benchmark job."""

from __future__ import annotations

from pathlib import Path

import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/ci.yml"

_GATE_TESTS = (
    "tests/evaluation/test_scoring.py",
    "tests/evaluation/test_l5_scenarios.py",
    "tests/evaluation/test_l5_gate.py",
    "tests/test_l5_gate_workflow.py",
)


def test_l5_benchmark_gate_is_required_offline_and_uploads_evidence() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    gate = jobs["l5_benchmark_gate"]

    assert gate["name"] == "l5-pr-benchmark-gate"
    assert "l5_benchmark_gate" in jobs["repository-quality"]["needs"]

    steps = gate["steps"]
    scripts = "\n".join(str(step.get("run", "")) for step in steps)
    normalized = " ".join(scripts.replace("\\", " ").split())
    for path in _GATE_TESTS:
        assert path in scripts
    assert "app.evaluation.l5_gate" in normalized
    assert "--report .runtime/evaluation/l5-gate.json" in normalized
    assert "--diff .runtime/evaluation/l5-gate-diff.json" in normalized
    assert "OPENAI_API_KEY=" in scripts
    assert "ENABLE_QB_PROXY=false" in scripts
    assert "ENABLE_PROACTIVE_SCHEDULER=false" in scripts
    assert "secrets." not in yaml.safe_dump(gate)
    assert "--offline-agent-gate" in scripts

    uploads = [
        step for step in steps if step.get("uses") == "actions/upload-artifact@v4"
    ]
    assert len(uploads) == 1
    upload = uploads[0]
    assert upload["if"] == "always()"
    assert upload["with"]["name"] == "ci-l5-pr-benchmark-gate"
    uploaded = str(upload["with"]["path"])
    assert "backend/.runtime/junit/l5-benchmark.xml" in uploaded
    assert "backend/.runtime/evaluation/l5-gate.json" in uploaded
    assert "backend/.runtime/evaluation/l5-gate-diff.json" in uploaded
    assert "backend/.runtime/evaluation/transcripts/" in uploaded


def test_repository_quality_summarizes_the_l5_gate() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    summary = "\n".join(
        str(step.get("run", ""))
        for step in workflow["jobs"]["repository-quality"]["steps"]
    )

    assert "L5_BENCHMARK_RESULT" in summary
    assert "l5-pr-benchmark-gate" in summary
    assert '"$L5_BENCHMARK_RESULT"' in summary
