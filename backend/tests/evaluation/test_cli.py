"""CLI exit codes and machine-readable report tests."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from app.evaluation.runner import main


def test_fast_cli_succeeds_and_writes_stable_json_report(tmp_path):
    report_path = tmp_path / "report.json"

    exit_code = main([
        "--config",
        "evals/config/fast.yaml",
        "--report",
        str(report_path),
    ])

    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert exit_code == 0
    assert report["schema_version"] == 1
    assert report["dataset_version"] == "v1"
    assert report["code_revision"]
    assert report["agent"]["name"]
    assert "cases" in report
    assert "gate_failures" in report
    assert "api_key" not in report_path.read_text(encoding="utf-8").lower()


def test_cli_returns_nonzero_when_threshold_regresses(tmp_path):
    config_path = tmp_path / "failing.yaml"
    config_path.write_text(
        "\n".join([
            "name: failing",
            "dataset: evals/datasets/v1.jsonl",
            "tags: [fast]",
            "thresholds:",
            "  impossible:",
            "    direction: min",
            "    value: 1.0",
            "    required: true",
        ]),
        encoding="utf-8",
    )

    assert main(["--config", str(config_path)]) == 1


def test_module_cli_starts_in_a_fresh_process(tmp_path):
    report_path = tmp_path / "subprocess-report.json"
    backend_dir = Path(__file__).parents[2]
    environment = os.environ.copy()
    environment["DEBUG"] = "false"

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "app.evaluation.runner",
            "--config",
            "evals/config/fast.yaml",
            "--report",
            str(report_path),
        ],
        cwd=backend_dir,
        env=environment,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert report_path.exists()
