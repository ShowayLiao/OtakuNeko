"""Exercise the real configuration CLI on isolated copies and invalid inputs."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.check_configuration import CHECKED_PATHS

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "backend/scripts/check_configuration.py"


def test_shared_entrypoint_config_is_covered():
    assert "backend/evals/config/entrypoint.yaml" in CHECKED_PATHS


@pytest.fixture
def configuration_root(tmp_path: Path) -> Path:
    for relative in (
        *CHECKED_PATHS,
        "backend/evals/datasets/v1.jsonl",
        "backend/evals/datasets/v1-full.jsonl",
        "backend/evals/datasets/v1-observability.jsonl",
        "backend/evals/datasets/v1-entrypoint.jsonl",
        "backend/app/evaluation/adapter.py",
        "backend/app/evaluation/entrypoint.py",
        "backend/app/evaluation/judge.py",
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    (tmp_path / "backend/alembic").mkdir()
    return tmp_path


def run_checker(root: Path, env: dict[str, str] | None = None) -> tuple[int, dict, str]:
    report = root / "report.json"
    completed = subprocess.run(
        [sys.executable, str(SCRIPT), "--root", str(root), "--report", str(report)],
        cwd=root,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )
    return (
        completed.returncode,
        json.loads(report.read_text(encoding="utf-8")),
        completed.stdout + completed.stderr,
    )


def test_checker_accepts_repository_configuration(configuration_root: Path):
    code, report, _ = run_checker(configuration_root)
    assert code == 0
    assert report["failed_paths"] == 0
    assert report["checked_paths"] == len(CHECKED_PATHS)


@pytest.mark.parametrize(
    ("relative", "old", "new"),
    [
        (".env.example", None, "UNKNOWN_KEY=probe-secret"),
        (".env.example", "DEBUG=true", "DEBUG=probe-secret"),
        (".env.example", None, "DEBUG=false"),
        (".env.example", None, 'PROJECT_NAME="unterminated'),
        (".env.example", None, "PROJECT_NAME"),
        (".env.example", "DEPLOY_MODE=local", "DEPLOY_MODE=invalid"),
        (".env.example", None, "OTAKUNEKO_MCP_USER_ID=-1"),
        (".env.example", None, "INTERACTIVE_RUN_STORE_ENABLED=invalid"),
        ("backend/evals/config/fast.yaml", None, "unknown_field: true"),
        (
            "backend/evals/config/fast.yaml",
            "evals/datasets/v1.jsonl",
            "evals/datasets/missing.jsonl",
        ),
        (
            "backend/evals/config/fast.yaml",
            "evals/baselines/v1-fast.json",
            "evals/baselines/missing.json",
        ),
        ("backend/evals/config/fast.yaml", "tags: [fast]", "tags: [absent]"),
        ("backend/evals/config/fast.yaml", "tags: [fast]", "tags: []"),
        ("backend/evals/config/fast.yaml", "pass_rate:", "unknown_metric:"),
        ("backend/evals/config/fast.yaml", "value: 1.0", "value: .nan"),
        (
            "backend/evals/config/full.yaml",
            "create_production_target",
            "missing_factory",
        ),
        ("backend/alembic.ini", "formatter = generic", "formatter = absent"),
        ("backend/alembic.ini", "handlers = console", "handlers = absent"),
        ("backend/alembic.ini", "class = StreamHandler", "class = MissingHandler"),
        ("backend/alembic.ini", "level = WARNING", "level = INVALID"),
        (
            "backend/alembic.ini",
            "args = (sys.stderr,)",
            'args = (sys.stderr,)\nkwargs = {"unexpected": True}',
        ),
        (
            "backend/alembic.ini",
            "qualname = alembic",
            "qualname = alembic\npropagate = invalid",
        ),
        ("backend/pyproject.toml", None, "invalid = ["),
        ("backend/uv.lock", None, "invalid = ["),
    ],
)
def test_cli_rejects_invalid_configuration(configuration_root, relative, old, new):
    path = configuration_root / relative
    text = path.read_text(encoding="utf-8")
    path.write_text(
        text + "\n" + new + "\n" if old is None else text.replace(old, new),
        encoding="utf-8",
    )
    code, report, output = run_checker(configuration_root)
    assert code == 1
    assert (
        next(item for item in report["paths"] if item["path"] == relative)["status"]
        == "fail"
    )
    assert "probe-secret" not in json.dumps(report) + output


def test_environment_and_real_dotenv_do_not_affect_templates(configuration_root):
    (configuration_root / ".env").write_text("DEBUG=invalid", encoding="utf-8")
    (configuration_root / "backend/.env").write_text("DEBUG=invalid", encoding="utf-8")
    env = {
        **os.environ,
        "DEBUG": "invalid",
        "OTAKUNEKO_MCP_USER_ID": "invalid",
        "INTERACTIVE_RUN_STORE_ENABLED": "invalid",
    }
    code, report, _ = run_checker(configuration_root, env)
    assert code == 0
    assert report["failed_paths"] == 0


@pytest.mark.parametrize(
    "item",
    [
        {"path": "app/x.py"},
        {"path": "app/x.py", "code": "x", "message": "x", "count": -1},
        {"path": "app/x.py", "code": "x", "message": "x", "count": True},
    ],
)
def test_type_baseline_requires_complete_error_contract(configuration_root, item):
    path = configuration_root / "backend/typecheck-baseline.json"
    path.write_text(
        json.dumps({"checked_files": 1, "errors": [item]}), encoding="utf-8"
    )
    assert run_checker(configuration_root)[0] == 1


def test_baseline_version_must_match_dataset(configuration_root):
    path = configuration_root / "backend/evals/baselines/v1-fast.json"
    baseline = json.loads(path.read_text(encoding="utf-8"))
    baseline["dataset_version"] = "different-version"
    path.write_text(json.dumps(baseline), encoding="utf-8")
    assert run_checker(configuration_root)[0] == 1


def test_baseline_schema_must_be_valid(configuration_root):
    (configuration_root / "backend/evals/baselines/v1-fast.json").write_text(
        '{"unknown": true}', encoding="utf-8"
    )
    assert run_checker(configuration_root)[0] == 1


def test_nested_factory_symbol_is_not_a_module_callable(configuration_root):
    path = configuration_root / "backend/app/evaluation/adapter.py"
    path.write_text(
        "def outer():\n    def create_production_target():\n        pass\n",
        encoding="utf-8",
    )
    assert run_checker(configuration_root)[0] == 1


def test_toml_check_uses_uv_when_standard_library_parser_is_unavailable(
    configuration_root, monkeypatch
):
    import builtins
    from scripts.check_configuration import check_toml

    from scripts import check_configuration as checker

    monkeypatch.delattr(checker, "tomllib", raising=False)
    original_import = builtins.__import__

    def import_without_tomllib(name, *args, **kwargs):
        if name == "tomllib":
            raise ModuleNotFoundError(name)
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_tomllib)
    check_toml(configuration_root, "backend/pyproject.toml")
    (configuration_root / "backend/pyproject.toml").write_text(
        "invalid = [", encoding="utf-8"
    )
    with pytest.raises(ValueError):
        check_toml(configuration_root, "backend/pyproject.toml")
