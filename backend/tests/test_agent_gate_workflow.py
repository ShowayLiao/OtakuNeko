"""PR gate contract for the offline Fake-LLM Agent CI job."""

from __future__ import annotations

from pathlib import Path

import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/ci.yml"

_GATE_TESTS = (
    "tests/harness/test_scripted_llm.py",
    "tests/evaluation/test_entrypoint.py",
    "tests/acceptance/test_scripted_llm_observation_path.py",
    "tests/acceptance/test_runtime_multi_step_replay.py",
    "tests/acceptance/test_runtime_failure_paths.py",
    "tests/acceptance/test_persistence_event_trace_replay.py",
    "tests/test_agent_gate_workflow.py",
    "tests/harness/test_recovery_policy.py",
    "tests/evaluation/test_offline.py",
    "tests/evaluation/test_loop_gate.py",
    "tests/api/test_chat_recovery.py",
)


def test_agent_gate_is_required_offline_and_uploads_failures() -> None:
    workflow = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
    jobs = workflow["jobs"]
    gate = jobs["agent_gate"]

    assert gate["name"] == "agent-fake-llm-gate"
    assert "agent_gate" in jobs["repository-quality"]["needs"]

    steps = gate["steps"]
    scripts = "\n".join(str(step.get("run", "")) for step in steps)
    normalized = " ".join(scripts.replace("\\", " ").split())
    for path in _GATE_TESTS:
        assert path in scripts
    assert "app.evaluation.runner --config evals/config/entrypoint.yaml" in normalized
    assert "OPENAI_API_KEY=" in scripts
    assert "ENABLE_QB_PROXY=false" in scripts
    assert "ENABLE_PROACTIVE_SCHEDULER=false" in scripts
    assert "secrets." not in yaml.safe_dump(gate)
    assert "--offline-agent-gate" in scripts
    assert "app.evaluation.loop_gate --output .runtime/agent-gate" in normalized
    certification = [
        step
        for step in steps
        if "app.evaluation.loop_gate --output" in str(step.get("run", ""))
    ]
    assert len(certification) == 1 and certification[0]["if"] == "always()"

    uploads = [
        step for step in steps if step.get("uses") == "actions/upload-artifact@v4"
    ]
    assert len(uploads) == 1
    upload = uploads[0]
    assert upload["if"] == "always()"
    uploaded = str(upload["with"]["path"])
    assert "backend/.runtime/junit/agent-gate.xml" in uploaded
    assert "backend/.runtime/evaluation/agent-gate-entrypoint.json" in uploaded
    assert "backend/.runtime/agent-gate/" in uploaded
