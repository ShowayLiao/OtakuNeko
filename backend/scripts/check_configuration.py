"""Offline validation for the repository's application configuration surface."""

from __future__ import annotations

import argparse
import ast
import configparser
import json
import inspect
import logging
import math
import os
import sys
import tempfile
import subprocess
from contextlib import contextmanager
from pathlib import Path
from typing import Literal, cast

from dotenv.parser import parse_stream


CHECKED_PATHS = (
    "backend/pyproject.toml",
    "backend/uv.lock",
    "backend/alembic.ini",
    ".env.example",
    "backend/.env.example",
    "backend/evals/config/fast.yaml",
    "backend/evals/config/observability.yaml",
    "backend/evals/config/full.yaml",
    "backend/evals/config/entrypoint.yaml",
    "backend/evals/config/real-model.yaml",
    "backend/evals/baselines/v1-fast.json",
    "backend/evals/baselines/v1-full.json",
    "backend/typecheck-baseline.json",
)
DIRECT_BOOL_KEYS = {"INTERACTIVE_RUN_STORE_ENABLED", "HARNESS_COORDINATOR_ENABLED"}
KNOWN_DIRECT_KEYS = DIRECT_BOOL_KEYS | {
    "OPENAI_BASE_URL",
    "MEMORY_TRUST_MODE",
    "OTAKUNEKO_MCP_USER_ID",
}


def safe_error(relative: str, exc: Exception) -> str:
    text = str(exc)
    categories = {
        "unknown dotenv key": "unknown-key",
        "duplicate dotenv key": "duplicate-key",
        "malformed dotenv": "malformed",
        "dotenv value missing": "missing-value",
        "invalid deploy mode": "invalid-deploy-mode",
        "invalid boolean": "invalid-boolean",
        "invalid positive integer": "invalid-positive-integer",
        "invalid logging reference": "invalid-logging-reference",
        "invalid settings": "invalid-settings",
        "unknown threshold metric": "unknown-metric",
        "baseline dataset version mismatch": "baseline-version",
        "baseline missing": "missing-baseline",
        "dataset tags select no cases": "empty-tag-selection",
        "empty dataset": "empty-dataset",
        "factory symbol missing": "missing-factory",
        "factory outside backend": "factory-outside-backend",
        "nonfinite threshold": "nonfinite-threshold",
        "invalid type baseline": "invalid-type-baseline",
    }
    category = categories.get(text, "invalid-configuration")
    return f"{relative}: {category}"


def _read(root: Path, relative: str) -> str:
    return (root / relative).read_text(encoding="utf-8")


def check_toml(root: Path, relative: str) -> None:
    try:
        import tomllib
    except ImportError:
        # Python 3.10 has no tomllib. The existing pinned project tool validates
        # pyproject.toml and uv.lock together without changing either file.
        result = subprocess.run(
            [
                "uv",
                "lock",
                "--check",
                "--offline",
                "--no-cache",
                "--no-python-downloads",
                "--python",
                sys.executable,
                "--directory",
                str(root / "backend"),
            ],
            capture_output=True,
            timeout=60,
            check=False,
        )
        if result.returncode:
            raise ValueError("invalid TOML or lockfile")
    else:
        tomllib.loads(_read(root, relative))


def check_alembic(root: Path) -> None:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    path = root / "backend/alembic.ini"
    config = Config(str(path))
    if not config.get_main_option("script_location"):
        raise ValueError("missing script location")
    ScriptDirectory.from_config(config)
    from sqlalchemy.engine import make_url

    make_url(config.get_main_option("sqlalchemy.url") or "")
    parser = configparser.ConfigParser(interpolation=None)
    parser.read(path, encoding="utf-8")
    groups = {
        name: {
            key.strip() for key in parser.get(name, "keys").split(",") if key.strip()
        }
        for name in ("loggers", "handlers", "formatters")
    }
    if "root" not in groups["loggers"]:
        raise ValueError("invalid logging reference")
    for group, prefix in (
        ("loggers", "logger"),
        ("handlers", "handler"),
        ("formatters", "formatter"),
    ):
        for key in groups[group]:
            if not parser.has_section(f"{prefix}_{key}"):
                raise ValueError("invalid logging reference")
    for key in groups["formatters"]:
        section = f"formatter_{key}"
        style = parser.get(section, "style", fallback="%")
        if style not in {"%", "{", "$"}:
            raise ValueError("invalid logging reference")
        logging.Formatter(
            parser.get(section, "format", fallback=None),
            parser.get(section, "datefmt", fallback=None),
            cast(Literal["%", "{", "$"], style),
        )
    for key in groups["loggers"]:
        section = f"logger_{key}"
        handlers = {
            item.strip()
            for item in parser.get(section, "handlers").split(",")
            if item.strip()
        }
        if not handlers <= groups["handlers"]:
            raise ValueError("invalid logging reference")
        if key != "root":
            parser.get(section, "qualname")
            parser.getint(section, "propagate", fallback=1)
    for key in groups["handlers"]:
        section = f"handler_{key}"
        formatter = parser.get(section, "formatter", fallback="")
        if formatter and formatter not in groups["formatters"]:
            raise ValueError("invalid logging reference")
        class_name = parser.get(section, "class")
        handler = getattr(logging, class_name.removeprefix("logging."), None)
        if not isinstance(handler, type) or not issubclass(handler, logging.Handler):
            raise ValueError("invalid logging reference")
        # Parse constructor arguments without eval, importing plugins or opening files.
        args_text = parser.get(section, "args", fallback="()")
        if args_text in {"(sys.stderr,)", "(sys.stdout,)"}:
            arguments = (None,)
        else:
            arguments = ast.literal_eval(args_text)
        if not isinstance(arguments, tuple):
            raise ValueError("invalid logging reference")
        keyword_arguments = ast.literal_eval(
            parser.get(section, "kwargs", fallback="{}")
        )
        if not isinstance(keyword_arguments, dict):
            raise ValueError("invalid logging reference")
        inspect.signature(handler).bind(*arguments, **keyword_arguments)
    for section in parser.sections():
        if section.startswith(("logger_", "handler_")) and parser.has_option(
            section, "level"
        ):
            level = parser.get(section, "level")
            if not isinstance(logging.getLevelName(level), int):
                raise ValueError("invalid logging reference")


def _dotenv_bindings(path: Path) -> dict[str, str | None]:
    bindings: dict[str, str | None] = {}
    with path.open(encoding="utf-8") as handle:
        for binding in parse_stream(handle):
            if binding.error:
                raise ValueError("malformed dotenv")
            if binding.key is None:
                continue
            if binding.value is None:
                raise ValueError("dotenv value missing")
            if binding.key in bindings:
                raise ValueError("duplicate dotenv key")
            bindings[binding.key] = binding.value
    return bindings


@contextmanager
def _isolated_environment():
    original = os.environ.copy()
    old_cwd = Path.cwd()
    with tempfile.TemporaryDirectory() as empty:
        os.chdir(empty)
        try:
            os.environ.clear()
            # Windows extension modules need SystemRoot; retain OS plumbing only.
            os.environ.update(
                {
                    key: value
                    for key, value in original.items()
                    if key.upper()
                    in {"SYSTEMROOT", "WINDIR", "PATH", "TEMP", "TMP", "SYSTEMDRIVE"}
                }
            )
            yield
        finally:
            os.chdir(old_cwd)
            os.environ.clear()
            os.environ.update(original)


def check_env(root: Path, relative: str) -> None:
    values = _dotenv_bindings(root / relative)
    with _isolated_environment():
        sys.path.insert(0, str(root / "backend"))
        try:
            from app.core.config import Settings

            settings_keys = set(Settings.model_fields)
        finally:
            sys.path.pop(0)
    unknown = set(values) - settings_keys - KNOWN_DIRECT_KEYS
    if unknown:
        raise ValueError("unknown dotenv key")
    if "DEPLOY_MODE" in values and values["DEPLOY_MODE"] not in {"local", "cloud"}:
        raise ValueError("invalid deploy mode")
    for key in DIRECT_BOOL_KEYS:
        raw = values.get(key)
        if raw is not None and str(raw).lower() not in {
            "true",
            "false",
            "1",
            "0",
            "yes",
            "no",
            "on",
            "off",
        }:
            raise ValueError("invalid boolean")
    user_id = values.get("OTAKUNEKO_MCP_USER_ID")
    if user_id is not None:
        try:
            if int(str(user_id)) <= 0:
                raise ValueError
        except (TypeError, ValueError):
            raise ValueError("invalid positive integer")
    with _isolated_environment():
        try:
            from app.core.config import Settings

            Settings.model_validate(values)
        except Exception as exc:
            # Deliberately avoid the exception text: Pydantic may include input values.
            raise ValueError("invalid settings") from exc


def _factory_exists(root: Path, reference: str) -> None:
    module_name, symbol = reference.split(":", 1)
    module_path = root / "backend" / Path(*module_name.split("."))
    module_path = module_path.with_suffix(".py")
    if root / "backend" not in module_path.resolve().parents:
        raise ValueError("factory outside backend")
    tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    names = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }
    if symbol not in names:
        raise ValueError("factory symbol missing")


def check_eval(root: Path, relative: str) -> None:
    sys.path.insert(0, str(root / "backend"))
    try:
        from app.evaluation.config import load_config
        from app.evaluation.dataset import load_dataset
        from app.evaluation.judge import load_baseline

        config = load_config(root / relative)
        dataset_path = root / "backend" / config.dataset
        if root / "backend" not in dataset_path.resolve().parents:
            raise ValueError("dataset outside backend")
        dataset = load_dataset(dataset_path)
        if not dataset.cases:
            raise ValueError("empty dataset")
        if config.tags is not None and not any(
            set(config.tags) & set(case.tags) for case in dataset.cases
        ):
            raise ValueError("dataset tags select no cases")
        if config.baseline:
            baseline_path = root / "backend" / config.baseline
            if root / "backend" not in baseline_path.resolve().parents:
                raise ValueError("baseline outside backend")
            baseline = load_baseline(baseline_path)
            if baseline is None:
                raise ValueError("baseline missing")
            if baseline.dataset_version != dataset.dataset_version:
                raise ValueError("baseline dataset version mismatch")
        from app.evaluation.metrics import (
            aggregate_metrics,
            aggregate_observability,
            compute_case_metrics,
        )
        from app.evaluation.types import ExecutionResult

        metrics = set(
            aggregate_metrics(
                [compute_case_metrics(dataset.cases[0], ExecutionResult(route=""))]
            )
        )
        metrics.update(aggregate_observability([]))
        metrics.add("safety_pass_rate")
        if config.judge.enabled:
            metrics.update({"judge_score", "judge_cost_usd"})
        if config.baseline and baseline is not None:
            if any(metric.metric not in metrics for metric in baseline.metrics):
                raise ValueError("unknown threshold metric")
        for name in config.thresholds:
            if name not in metrics:
                raise ValueError("unknown threshold metric")
            if not math.isfinite(config.thresholds[name].value):
                raise ValueError("nonfinite threshold")
        for factory in (config.target_factory, config.judge_factory):
            if factory:
                _factory_exists(root, factory)
    finally:
        if sys.path and sys.path[0] == str(root / "backend"):
            sys.path.pop(0)


def check_baseline(root: Path, relative: str) -> None:
    from app.evaluation.judge import load_baseline

    baseline = load_baseline(root / relative)
    if baseline is None or not baseline.dataset_version:
        raise ValueError("invalid baseline")
    if any(
        not math.isfinite(metric.expected_value) or not math.isfinite(metric.tolerance)
        for metric in baseline.metrics
    ):
        raise ValueError("invalid baseline")


def check_type_baseline(root: Path) -> None:
    data = json.loads(_read(root, "backend/typecheck-baseline.json"))
    if (
        not isinstance(data, dict)
        or type(data.get("checked_files")) is not int
        or data["checked_files"] < 0
    ):
        raise ValueError("invalid type baseline")
    if not isinstance(data.get("errors"), list):
        raise ValueError("invalid type baseline")
    for item in data["errors"]:
        if not isinstance(item, dict) or any(
            not isinstance(item.get(key), str) or not item[key]
            for key in ("path", "code", "message")
        ):
            raise ValueError("invalid type baseline")
        if type(item.get("count")) is not int or item["count"] < 0:
            raise ValueError("invalid type baseline")


def run(root: Path) -> dict:
    checks = {
        "backend/pyproject.toml": lambda: check_toml(root, "backend/pyproject.toml"),
        "backend/uv.lock": lambda: check_toml(root, "backend/uv.lock"),
        "backend/alembic.ini": lambda: check_alembic(root),
        ".env.example": lambda: check_env(root, ".env.example"),
        "backend/.env.example": lambda: check_env(root, "backend/.env.example"),
        "backend/evals/config/fast.yaml": lambda: check_eval(
            root, "backend/evals/config/fast.yaml"
        ),
        "backend/evals/config/observability.yaml": lambda: check_eval(
            root, "backend/evals/config/observability.yaml"
        ),
        "backend/evals/config/full.yaml": lambda: check_eval(
            root, "backend/evals/config/full.yaml"
        ),
        "backend/evals/config/entrypoint.yaml": lambda: check_eval(
            root, "backend/evals/config/entrypoint.yaml"
        ),
        "backend/evals/config/real-model.yaml": lambda: check_eval(
            root, "backend/evals/config/real-model.yaml"
        ),
        "backend/evals/baselines/v1-fast.json": lambda: check_baseline(
            root, "backend/evals/baselines/v1-fast.json"
        ),
        "backend/evals/baselines/v1-full.json": lambda: check_baseline(
            root, "backend/evals/baselines/v1-full.json"
        ),
        "backend/typecheck-baseline.json": lambda: check_type_baseline(root),
    }
    paths = []
    for relative in CHECKED_PATHS:
        try:
            checks[relative]()
            paths.append({"path": relative, "status": "pass"})
        except Exception as exc:
            paths.append(
                {"path": relative, "status": "fail", "error": safe_error(relative, exc)}
            )
    failed = sum(item["status"] == "fail" for item in paths)
    return {"paths": paths, "checked_paths": len(paths), "failed_paths": failed}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    root = (args.root or Path(__file__).resolve().parents[2]).resolve()
    report = args.report or root / "backend/.runtime/quality/configuration.json"
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    with _isolated_environment():
        payload = run(root)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return 0 if payload["failed_paths"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
