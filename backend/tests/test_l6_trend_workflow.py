"""Manual/scheduled L6 live trend workflow contract."""

from __future__ import annotations

from pathlib import Path

import yaml  # type: ignore[import-untyped]

ROOT = Path(__file__).resolve().parents[2]
TREND = ROOT / ".github/workflows/l6-trend.yml"
CI = ROOT / ".github/workflows/ci.yml"


def _triggers(workflow: dict) -> dict:
    # PyYAML parses the unquoted YAML 1.1 key `on` as boolean True.
    return workflow.get("on") or workflow.get(True) or {}


def test_live_trend_is_manual_or_scheduled_and_not_pr_required() -> None:
    workflow = yaml.safe_load(TREND.read_text(encoding="utf-8"))
    triggers = _triggers(workflow)

    assert set(triggers) == {"workflow_dispatch", "schedule"}
    assert "pull_request" not in triggers
    assert "push" not in triggers
    assert triggers["schedule"][0]["cron"] == "0 3 * * 1"

    jobs = workflow["jobs"]
    assert "l6_trend" in jobs
    ci = yaml.safe_load(CI.read_text(encoding="utf-8"))
    assert "l6_trend" not in ci["jobs"]["repository-quality"]["needs"]
    assert "l6-live-trend" not in yaml.safe_dump(ci["jobs"]["repository-quality"])


def test_live_trend_uploads_evidence_and_uses_secret_only_in_env() -> None:
    workflow = yaml.safe_load(TREND.read_text(encoding="utf-8"))
    job = workflow["jobs"]["l6_trend"]
    steps = job["steps"]
    scripts = "\n".join(str(step.get("run", "")) for step in steps)
    normalized = " ".join(scripts.replace("\\", " ").split())

    assert "app.evaluation.trend" in normalized
    assert "--config evals/config/real-model-quality.yaml" in normalized
    assert "--repeats" in normalized
    assert "--history .runtime/evaluation/l6-trend/history.jsonl" in normalized
    assert "--update-baseline" in normalized
    assert 'test -n "${OPENAI_API_KEY:-}"' in scripts
    assert "secrets.OPENAI_API_KEY" in yaml.safe_dump(
        [step.get("env", {}) for step in steps]
    )
    assert "secrets." not in scripts

    uploads = [
        step for step in steps if step.get("uses") == "actions/upload-artifact@v4"
    ]
    assert len(uploads) == 1
    upload = uploads[0]
    assert upload["if"] == "always()"
    assert upload["with"]["name"] == "ci-l6-live-trend"
    uploaded = str(upload["with"]["path"])
    assert "backend/.runtime/evaluation/l6-trend/" in uploaded
    assert "backend/evals/baselines/l6-trend-deepseek-flash.json" in uploaded
