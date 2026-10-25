"""Run authoritative configuration checks and account for every in-scope path."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
WORKFLOWS = (
    ".github/workflows/ci.yml",
    ".github/workflows/evaluation.yml",
    ".github/workflows/frontend-qa.yml",
    ".github/workflows/l6-trend.yml",
)
COMPOSE = "docker-compose.yml"


def discover_paths(root: Path, tracked: list[str] | None = None) -> list[str]:
    if tracked is None:
        result = subprocess.run(
            ["git", "ls-files", "-z"], cwd=root, capture_output=True, check=True
        )
        tracked = result.stdout.decode("utf-8").split("\0")
    paths = {
        path
        for path in tracked
        if (
            path.startswith("backend/")
            and (
                Path(path).suffix
                in {".toml", ".ini", ".lock", ".yaml", ".yml", ".json"}
                or path.endswith(".env.example")
            )
        )
        or path in {".env.example", COMPOSE}
        or (
            path.startswith(".github/workflows/")
            and Path(path).suffix in {".yaml", ".yml"}
        )
    }
    for directory in (".github/workflows", "backend/evals/config"):
        for pattern in ("*.yaml", "*.yml"):
            paths.update(
                path.relative_to(root).as_posix()
                for path in (root / directory).glob(pattern)
            )
    return sorted(paths)


def summarize(
    paths: list[str], records: list[dict[str, Any]], exit_codes: dict[str, int]
) -> dict[str, Any]:
    indexed: dict[str, str] = {}
    invalid = False
    for record in records:
        path, status = record.get("path"), record.get("status")
        if (
            not isinstance(path, str)
            or status not in {"pass", "fail"}
            or path in indexed
        ):
            invalid = True
            continue
        indexed[path] = status
    uncovered = sorted(set(paths) - indexed.keys())
    unexpected = sorted(indexed.keys() - set(paths))
    failed = sorted(path for path, status in indexed.items() if status == "fail")
    code = int(
        invalid
        or bool(uncovered or unexpected or failed)
        or not exit_codes
        or any(value != 0 for value in exit_codes.values())
    )
    return {
        "schema_version": 1,
        "configuration_count": len(paths),
        "covered_count": len(set(paths) & indexed.keys()),
        "uncovered_count": len(uncovered),
        "uncovered_paths": uncovered,
        "unexpected_paths": unexpected,
        "failed_count": len(failed),
        "failed_paths": failed,
        "invalid_records": invalid,
        "validator_exit_codes": exit_codes,
        "paths": records,
        "exit_code": code,
    }


def execute(command: list[str], root: Path) -> int:
    try:
        result = subprocess.run(
            command, cwd=root, capture_output=True, timeout=120, check=False
        )
        return result.returncode
    except (OSError, subprocess.TimeoutExpired):
        return 127


def run_checks(
    root: Path, actionlint: str, compose: str | None, probe_tools: bool
) -> dict[str, Any]:
    records: list[dict[str, Any]] = []
    codes: dict[str, int] = {}
    workflow_command = [actionlint, "-shellcheck=", "-pyflakes="]
    compose_command = [compose] if compose else ["docker", "compose"]
    with tempfile.TemporaryDirectory(prefix="otakuneko-config-") as temporary:
        directory = Path(temporary)
        application_report = directory / "application.json"
        codes["application"] = execute(
            [
                sys.executable,
                str(ROOT / "backend/scripts/check_configuration.py"),
                "--root",
                str(root),
                "--report",
                str(application_report),
            ],
            root,
        )
        try:
            application = json.loads(application_report.read_text(encoding="utf-8"))
            if not isinstance(application, dict) or not isinstance(
                application.get("paths"), list
            ):
                raise ValueError("invalid application report")
            records.extend(application["paths"])
        except (OSError, ValueError, TypeError):
            codes["application_report"] = 1
        codes["actionlint"] = execute(workflow_command + list(WORKFLOWS), root)
        records.extend(
            {"path": path, "status": "pass" if codes["actionlint"] == 0 else "fail"}
            for path in WORKFLOWS
        )
        codes["compose"] = execute(
            compose_command
            + ["--env-file", ".env.example", "-f", COMPOSE, "config", "--quiet"],
            root,
        )
        records.append(
            {"path": COMPOSE, "status": "pass" if codes["compose"] == 0 else "fail"}
        )
        probes: dict[str, int] = {}
        if probe_tools:
            workflow_probe = directory / "invalid-workflow.yaml"
            workflow_probe.write_text(
                "name: invalid\non: push\njobs:\n  test:\n    runs-of: ubuntu-latest\n    steps:\n      - run: echo test\n",
                encoding="utf-8",
            )
            compose_probe = directory / "invalid-compose.yaml"
            compose_probe.write_text(
                "services:\n  backend:\n    image: python:3.11-slim\n    invalid_configuration_field: true\n",
                encoding="utf-8",
            )
            probes["actionlint_invalid_workflow"] = execute(
                workflow_command + [str(workflow_probe)], root
            )
            probes["compose_invalid_field"] = execute(
                compose_command
                + [
                    "--env-file",
                    ".env.example",
                    "-f",
                    str(compose_probe),
                    "config",
                    "--quiet",
                ],
                root,
            )
            # Reject command-not-found, timeout and success: neither proves rejection.
            codes["negative_probes"] = int(any(code != 1 for code in probes.values()))
        try:
            result = summarize(discover_paths(root), records, codes)
        except (OSError, subprocess.CalledProcessError, UnicodeError):
            result = summarize([], records, {**codes, "discovery": 1})
        result["negative_probe_exit_codes"] = probes
        return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--actionlint", default="actionlint")
    parser.add_argument(
        "--compose", help="Standalone Compose plugin; default: docker compose"
    )
    parser.add_argument("--probe-tools", action="store_true")
    args = parser.parse_args()
    root = args.root.resolve()
    report_path = (
        args.report or root / "backend/.runtime/quality/configuration-coverage.json"
    )
    result = run_checks(root, args.actionlint, args.compose, args.probe_tools)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    print(
        f"Configurations: {result['configuration_count']}; "
        f"failed: {result['failed_count']}; uncovered: {result['uncovered_count']}"
    )
    for name, code in result["validator_exit_codes"].items():
        print(f"{name}: exit {code}")
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
