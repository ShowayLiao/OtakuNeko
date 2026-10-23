"""Subprocess self-tests for the capability contract CI gate."""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import textwrap

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[3]
EVIDENCE_ROOT = BACKEND_ROOT / ".runtime" / "capability-contracts" / "probes"
CONTRACT_TEST = "tests/capabilities/contracts/test_contracts.py"
CORE_CONTRACT_TEST_PATHS = (CONTRACT_TEST,)
ANIME_CONTRACT_TESTS = (
    "tests/capabilities/contracts/test_anime_handlers.py",
    "tests/capabilities/contracts/test_anime_authorization.py",
)
SUBJECTS_CONTRACT_TEST = "tests/capabilities/contracts/test_subjects_handlers.py"
SUBJECTS_CONTRACT_TESTS = (SUBJECTS_CONTRACT_TEST,)
PROFILE_STATS_CONTRACT_TEST = (
    "tests/capabilities/contracts/test_profile_stats_handlers.py"
)
PROFILE_STATS_CONTRACT_TESTS = (PROFILE_STATS_CONTRACT_TEST,)
COLLECTIONS_READ_CONTRACT_TEST = (
    "tests/capabilities/contracts/test_collections_read_handlers.py"
)
COLLECTIONS_READ_CONTRACT_TESTS = (COLLECTIONS_READ_CONTRACT_TEST,)
SCHEDULE_READ_CONTRACT_TEST = (
    "tests/capabilities/contracts/test_schedule_read_handlers.py"
)
SCHEDULE_READ_CONTRACT_TESTS = (SCHEDULE_READ_CONTRACT_TEST,)
MEDIA_READ_CONTRACT_TEST = "tests/capabilities/contracts/test_media_read_handlers.py"
MEDIA_READ_CONTRACT_TESTS = (MEDIA_READ_CONTRACT_TEST,)
COLLECTIONS_WRITE_CONTRACT_TEST = (
    "tests/capabilities/contracts/test_collections_write_handlers.py"
)
COLLECTIONS_WRITE_CONTRACT_TESTS = (COLLECTIONS_WRITE_CONTRACT_TEST,)
SCHEDULE_WRITE_CONTRACT_TEST = (
    "tests/capabilities/contracts/test_schedule_write_handlers.py"
)
SCHEDULE_WRITE_CONTRACT_TESTS = (SCHEDULE_WRITE_CONTRACT_TEST,)
MEDIA_WRITE_CONTRACT_TEST = "tests/capabilities/contracts/test_media_write_handlers.py"
MEDIA_WRITE_CONTRACT_TESTS = (MEDIA_WRITE_CONTRACT_TEST,)
CONTRACT_TEST_PATHS = (
    *CORE_CONTRACT_TEST_PATHS,
    *ANIME_CONTRACT_TESTS,
    *SUBJECTS_CONTRACT_TESTS,
    *PROFILE_STATS_CONTRACT_TESTS,
    *COLLECTIONS_READ_CONTRACT_TESTS,
    *SCHEDULE_READ_CONTRACT_TESTS,
    *MEDIA_READ_CONTRACT_TESTS,
    *COLLECTIONS_WRITE_CONTRACT_TESTS,
    *SCHEDULE_WRITE_CONTRACT_TESTS,
    *MEDIA_WRITE_CONTRACT_TESTS,
)
GATE_PLUGIN = "tests.capabilities.contracts.plugin"


def _expected_observations():
    # Import in the isolated parent pytest process, after its conftest has set
    # test-only configuration. The count follows the live registry and fixtures.
    from tests.capabilities.contracts.catalog import (
        cases,
        census,
        expected_observations,
        fixture_errors,
    )

    actions, examples = census(), cases()
    assert fixture_errors(actions, examples) == []
    return expected_observations(actions, examples)


def test_subjects_actions_require_full_scenario_matrix():
    from tests.capabilities.contracts import catalog

    required = (
        "subjects_error",
        "subjects_timeout",
        "subjects_isolation",
        "subjects_serialization",
        "subjects_authorization",
        "subjects_dispatcher",
    )
    assert getattr(catalog, "SUBJECTS_SCENARIOS", None) == required

    registry = catalog.build_capability_registry()
    subjects = {
        (descriptor.public_name or descriptor.name, descriptor.version)
        for descriptor in registry.list_actions()
        if (owner := registry.find_action(descriptor.public_name or descriptor.name))
        and owner[0].name == "subjects"
    }
    expected = catalog.expected_observations(catalog.census(), catalog.cases())
    assert subjects
    assert {(*key, scenario) for key in subjects for scenario in required} <= expected


def test_collections_read_actions_require_full_scenario_matrix():
    from tests.capabilities.contracts import catalog

    required = (
        "collections_read_error",
        "collections_read_timeout",
        "collections_read_isolation",
        "collections_read_serialization",
        "collections_read_authorization",
        "collections_read_dispatcher",
    )
    assert getattr(catalog, "COLLECTIONS_READ_SCENARIOS", None) == required

    registry = catalog.build_capability_registry()
    actions = catalog.census()
    collection_reads = {
        key
        for key, descriptor in actions.items()
        if (owner := registry.find_action(key[0]))
        and owner[0].name == "collections"
        and not descriptor.is_side_effect
    }
    collection_writes = {
        key
        for key, descriptor in actions.items()
        if (owner := registry.find_action(key[0]))
        and owner[0].name == "collections"
        and descriptor.is_side_effect
    }
    expected = catalog.expected_observations(actions, catalog.cases())
    required_reads = {
        (*key, scenario) for key in collection_reads for scenario in required
    }
    required_writes = {
        (*key, scenario) for key in collection_writes for scenario in required
    }
    assert len(collection_reads) == 3
    assert required_reads <= expected
    assert not (required_writes & expected)


def test_schedule_read_actions_require_full_scenario_matrix():
    from tests.capabilities.contracts import catalog

    required = (
        "schedule_read_error",
        "schedule_read_timeout",
        "schedule_read_isolation",
        "schedule_read_serialization",
        "schedule_read_authorization",
        "schedule_read_dispatcher",
    )
    assert getattr(catalog, "SCHEDULE_READ_SCENARIOS", None) == required

    registry = catalog.build_capability_registry()
    actions = catalog.census()
    schedule_reads = {
        key
        for key, descriptor in actions.items()
        if (owner := registry.find_action(key[0]))
        and owner[0].name == "schedule"
        and not descriptor.is_side_effect
    }
    schedule_writes = {
        key
        for key, descriptor in actions.items()
        if (owner := registry.find_action(key[0]))
        and owner[0].name == "schedule"
        and descriptor.is_side_effect
    }
    frozen_reads = {
        ("list_schedules", "v1"),
        ("list_schedules_by_day", "v1"),
        ("list_unified_schedules", "v1"),
    }
    expected = catalog.expected_observations(actions, catalog.cases())
    required_reads = {
        (*key, scenario) for key in schedule_reads for scenario in required
    }
    required_writes = {
        (*key, scenario) for key in schedule_writes for scenario in required
    }
    write_labels_on_reads = {
        (*key, scenario)
        for key in schedule_reads
        for scenario in catalog.SCHEDULE_WRITE_SCENARIOS
    }

    assert schedule_reads == frozen_reads
    assert all(actions[key].requires_auth for key in frozen_reads)
    assert len(required_reads) == 18
    assert required_reads <= expected
    assert not (required_writes & expected)
    assert not (write_labels_on_reads & expected)


def test_media_read_actions_require_full_scenario_matrix():
    from tests.capabilities.contracts import catalog

    required = (
        "media_read_error",
        "media_read_timeout",
        "media_read_isolation",
        "media_read_serialization",
        "media_read_authorization",
        "media_read_dispatcher",
    )
    assert getattr(catalog, "MEDIA_READ_SCENARIOS", None) == required

    registry = catalog.build_capability_registry()
    actions = catalog.census()
    media_reads = {
        key
        for key, descriptor in actions.items()
        if (owner := registry.find_action(key[0]))
        and owner[0].name == "media"
        and not descriptor.is_side_effect
    }
    media_writes = {
        key
        for key, descriptor in actions.items()
        if (owner := registry.find_action(key[0]))
        and owner[0].name == "media"
        and descriptor.is_side_effect
    }
    frozen_reads = {
        ("library_status", "v1"),
        ("list_rss_feeds", "v1"),
        ("list_rss_rules", "v1"),
    }
    expected = catalog.expected_observations(actions, catalog.cases())
    required_reads = {(*key, scenario) for key in media_reads for scenario in required}
    read_labels_on_writes = {
        (*key, scenario) for key in media_writes for scenario in required
    }

    assert media_reads == frozen_reads
    assert len(media_writes) == 5
    assert len(required_reads) == 18
    assert required_reads <= expected
    assert not (read_labels_on_writes & expected)


def test_collections_write_actions_require_full_scenario_matrix():
    from tests.capabilities.contracts import catalog

    required = (
        "collections_write_error",
        "collections_write_timeout",
        "collections_write_isolation",
        "collections_write_serialization",
        "collections_write_authorization",
        "collections_write_dispatcher",
        "collections_write_approval",
        "collections_write_idempotency",
    )
    assert getattr(catalog, "COLLECTIONS_WRITE_SCENARIOS", None) == required

    registry = catalog.build_capability_registry()
    actions = catalog.census()
    collection_writes = {
        key
        for key, descriptor in actions.items()
        if (owner := registry.find_action(key[0]))
        and owner[0].name == "collections"
        and descriptor.is_side_effect
    }
    expected = catalog.expected_observations(actions, catalog.cases())
    required_writes = {
        (*key, scenario) for key in collection_writes for scenario in required
    }

    assert len(collection_writes) == 8
    assert len(required_writes) == 64
    assert required_writes <= expected


def test_schedule_write_actions_require_full_scenario_matrix():
    from tests.capabilities.contracts import catalog

    required = (
        "schedule_write_error",
        "schedule_write_timeout",
        "schedule_write_isolation",
        "schedule_write_serialization",
        "schedule_write_authorization",
        "schedule_write_dispatcher",
        "schedule_write_approval",
        "schedule_write_idempotency",
        "schedule_write_recovery",
    )
    assert getattr(catalog, "SCHEDULE_WRITE_SCENARIOS", None) == required

    registry = catalog.build_capability_registry()
    actions = catalog.census()
    schedule_writes = {
        key
        for key, descriptor in actions.items()
        if (owner := registry.find_action(key[0]))
        and owner[0].name == "schedule"
        and descriptor.is_side_effect
    }
    expected_names = {
        "create_schedule",
        "update_schedule",
        "delete_schedule",
        "upsert_schedule",
        "bulk_upsert_schedules",
        "sync_bangumi_schedule",
    }
    expected = catalog.expected_observations(actions, catalog.cases())
    required_writes = {
        (*key, scenario) for key in schedule_writes for scenario in required
    }

    assert {name for name, _version in schedule_writes} == expected_names
    assert len(schedule_writes) == 6
    assert len(required_writes) == 54
    assert required_writes <= expected


def test_media_write_actions_require_full_scenario_matrix():
    from tests.capabilities.contracts import catalog

    required = (
        "media_write_error",
        "media_write_timeout",
        "media_write_isolation",
        "media_write_serialization",
        "media_write_authorization",
        "media_write_dispatcher",
        "media_write_approval",
        "media_write_idempotency",
        "media_write_recovery",
    )
    assert getattr(catalog, "MEDIA_WRITE_SCENARIOS", None) == required

    registry = catalog.build_capability_registry()
    actions = catalog.census()
    media_writes = {
        key
        for key, descriptor in actions.items()
        if (owner := registry.find_action(key[0]))
        and owner[0].name == "media"
        and descriptor.is_side_effect
    }
    expected = catalog.expected_observations(actions, catalog.cases())
    required_writes = {
        (*key, scenario) for key in media_writes for scenario in required
    }

    assert len(media_writes) == 5
    assert len(required_writes) == 45
    assert required_writes <= expected


def test_recommendation_and_stats_actions_require_full_scenario_matrix():
    from tests.capabilities.contracts import catalog

    expected_scenarios = (
        "recommendation_error",
        "recommendation_timeout",
        "recommendation_isolation",
        "recommendation_serialization",
        "recommendation_authorization",
        "recommendation_dispatcher",
    )
    assert catalog.RECOMMENDATION_SCENARIOS == expected_scenarios
    expected_stats_scenarios = (
        "stats_error",
        "stats_timeout",
        "stats_isolation",
        "stats_serialization",
        "stats_authorization",
        "stats_dispatcher",
    )
    assert catalog.STATS_SCENARIOS == expected_stats_scenarios

    registry = catalog.build_capability_registry()
    expected = catalog.expected_observations(catalog.census(), catalog.cases())
    required_counts = {}
    for owner_name, scenarios in (
        ("recommendation", expected_scenarios),
        ("stats", expected_stats_scenarios),
    ):
        actions = {
            (descriptor.public_name or descriptor.name, descriptor.version)
            for descriptor in registry.list_actions()
            if (
                owner := registry.find_action(descriptor.public_name or descriptor.name)
            )
            and owner[0].name == owner_name
        }
        assert len(actions) == 2
        required = {(*key, scenario) for key in actions for scenario in scenarios}
        assert required <= expected
        required_counts[owner_name] = len(required)

    assert required_counts == {"recommendation": 12, "stats": 12}


def _write_probe_plugin(tmp_path: Path, source: str) -> Path:
    plugin = tmp_path / "capability_contract_probe.py"
    plugin.write_text(textwrap.dedent(source), encoding="utf-8")
    return plugin


def _decode_subprocess_output(value: object) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    return value if isinstance(value, str) else ""


def _run_gate_probe(
    name: str,
    tmp_path: Path,
    *,
    plugin_source: str | None = None,
    contract_test_paths: tuple[str, ...] = CONTRACT_TEST_PATHS,
    pytest_args: tuple[str, ...] = (),
) -> tuple[subprocess.CompletedProcess[bytes] | None, dict | None, str, Path]:
    evidence_dir = EVIDENCE_ROOT / name
    evidence_dir.mkdir(parents=True, exist_ok=True)
    output_path = evidence_dir / "output.txt"
    report_path = evidence_dir / "coverage.json"
    exitcode_path = evidence_dir / "exitcode.json"
    target_path = tmp_path / "probe-target.json"

    # A stale report could make a broken child appear to have exercised the
    # gate, so each subprocess starts with a clean result slot.
    report_path.unlink(missing_ok=True)
    target_path.unlink(missing_ok=True)

    command = [sys.executable, "-m", "pytest", "-p", GATE_PLUGIN]
    env = os.environ.copy()
    if plugin_source is not None:
        _write_probe_plugin(tmp_path, plugin_source)
        command.extend(("-p", "capability_contract_probe"))
        existing_pythonpath = env.get("PYTHONPATH")
        env["PYTHONPATH"] = os.pathsep.join(
            part for part in (str(tmp_path), existing_pythonpath) if part
        )
        env["CAPABILITY_GATE_PROBE_TARGET"] = str(target_path)

    command.extend(
        (
            *contract_test_paths,
            *pytest_args,
            "--capability-contract-gate",
            f"--capability-contract-report={report_path}",
            "-q",
            "--tb=short",
        )
    )

    completed = None
    exit_record: dict[str, object]
    timeout_output = ""
    try:
        completed = subprocess.run(
            command,
            cwd=BACKEND_ROOT,
            env=env,
            capture_output=True,
            timeout=120,
            check=False,
        )
        stdout = completed.stdout.decode("utf-8", errors="replace")
        stderr = completed.stderr.decode("utf-8", errors="replace")
        output = f"--- stdout ---\n{stdout}--- stderr ---\n{stderr}"
        exit_record = {"exitcode": completed.returncode, "timed_out": False}
    except subprocess.TimeoutExpired as exc:
        timeout_stdout = _decode_subprocess_output(exc.stdout)
        timeout_stderr = _decode_subprocess_output(exc.stderr)
        timeout_output = (
            f"--- stdout ---\n{timeout_stdout}--- stderr ---\n{timeout_stderr}"
        )
        output = timeout_output
        exit_record = {"exitcode": None, "timed_out": True, "timeout_seconds": 120}

    output_path.write_text(output, encoding="utf-8")
    exitcode_path.write_text(
        json.dumps(exit_record, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    coverage = None
    if report_path.is_file():
        coverage = json.loads(report_path.read_text(encoding="utf-8"))
    if target_path.is_file():
        (evidence_dir / "probe-target.json").write_text(
            target_path.read_text(encoding="utf-8"), encoding="utf-8"
        )
    return completed, coverage, output, evidence_dir


def _assert_gate_failure(
    completed: subprocess.CompletedProcess[bytes] | None,
    coverage: dict | None,
    output: str,
    expected_error: str,
) -> None:
    assert completed is not None, "gate subprocess exceeded its 120-second timeout"
    assert completed.returncode != 0, output
    assert coverage is not None, "gate subprocess did not write a coverage report"
    assert coverage["gate"] == "fail"
    assert any(
        error == expected_error or error.startswith(expected_error)
        for error in coverage["errors"]
    )
    assert "Capability contract gate FAILED" in output
    assert expected_error in output


def test_gate_rejects_new_registered_action_without_fixture(tmp_path):
    plugin_source = """
        import os
        from pathlib import Path

        import pytest


        def pytest_sessionstart(session):
            from tests.capabilities.contracts import catalog
            from app.capabilities.base import BaseCapability
            from app.capabilities.types import ActionDescriptor

            action_name = "gate_probe_unfixture_action"

            class ProbeCapability(BaseCapability):
                @property
                def name(self):
                    return "gate_probe_capability"

                @property
                def description(self):
                    return "Temporary gate self-test capability"

                def actions(self):
                    return [ActionDescriptor(
                        name=action_name,
                        public_name=action_name,
                        description="Temporary action without a fixture",
                        input_schema={"type": "object", "properties": {}},
                    )]

                async def execute(self, action, **kwargs):
                    return {"success": True}

            build_registry = catalog.build_capability_registry

            def build_with_unfixture_action():
                registry = build_registry()
                registry.register(ProbeCapability())
                return registry

            catalog.build_capability_registry = build_with_unfixture_action
            Path(os.environ["CAPABILITY_GATE_PROBE_TARGET"]).write_text(
                __import__("json").dumps([action_name, "v1"]), encoding="utf-8"
            )
    """
    completed, coverage, output, _ = _run_gate_probe(
        "new_action_without_fixture", tmp_path, plugin_source=plugin_source
    )
    _assert_gate_failure(
        completed,
        coverage,
        output,
        "Missing action fixtures: [('gate_probe_unfixture_action', 'v1')]",
    )


def test_gate_rejects_removed_existing_fixture(tmp_path):
    plugin_source = """
        import json
        import os
        from pathlib import Path


        def pytest_sessionstart(session):
            from tests.capabilities.contracts import catalog

            original_cases = catalog.cases
            removed_key = sorted(original_cases())[0]

            def cases_without_one_fixture():
                examples = original_cases()
                examples.pop(removed_key)
                return examples

            catalog.cases = cases_without_one_fixture
            Path(os.environ["CAPABILITY_GATE_PROBE_TARGET"]).write_text(
                json.dumps(removed_key), encoding="utf-8"
            )
    """
    completed, coverage, output, _ = _run_gate_probe(
        "removed_existing_fixture", tmp_path, plugin_source=plugin_source
    )
    assert completed is not None, "gate subprocess exceeded its 120-second timeout"
    target_path = tmp_path / "probe-target.json"
    assert target_path.is_file(), output
    removed_key = json.loads(target_path.read_text(encoding="utf-8"))
    expected_error = f"Missing action fixtures: {[tuple(removed_key)]}"
    _assert_gate_failure(completed, coverage, output, expected_error)


def test_gate_rejects_missing_timeout_scenario(tmp_path):
    completed, coverage, output, _ = _run_gate_probe(
        "missing_timeout_scenario",
        tmp_path,
        pytest_args=("-k", "not timeout"),
    )
    _assert_gate_failure(
        completed,
        coverage,
        output,
        "Missing executed contracts:",
    )
    expected = _expected_observations()
    missing = {tuple(row) for row in (coverage or {}).get("missing", [])}
    expected_timeouts = {row for row in expected if row[2].endswith("timeout")}
    assert expected_timeouts
    assert {row[2] for row in expected_timeouts} == {
        "timeout",
        "anime_timeout",
        "subjects_timeout",
        "recommendation_timeout",
        "stats_timeout",
        "collections_read_timeout",
        "schedule_read_timeout",
        "media_read_timeout",
        "media_write_timeout",
        "collections_write_timeout",
        "schedule_write_timeout",
    }
    assert missing == expected_timeouts
    assert (coverage or {}).get("passed") == len(expected) - len(expected_timeouts)


def test_gate_rejects_missing_schedule_write_recovery_scenario(tmp_path):
    completed, coverage, output, _ = _run_gate_probe(
        "missing_schedule_write_recovery_scenario",
        tmp_path,
        pytest_args=("-k", "not test_schedule_write_recovery"),
    )
    _assert_gate_failure(
        completed,
        coverage,
        output,
        "Missing executed contracts:",
    )

    from tests.capabilities.contracts.catalog import SCHEDULE_WRITE_SCENARIOS

    expected = _expected_observations()
    expected_recovery = {row for row in expected if row[2] == "schedule_write_recovery"}
    missing = {tuple(row) for row in (coverage or {}).get("missing", [])}
    assert len(expected_recovery) == 6
    assert expected_recovery == {
        row for row in expected if row[2] in SCHEDULE_WRITE_SCENARIOS[-1:]
    }
    assert missing == expected_recovery
    assert (coverage or {}).get("passed") == len(expected) - len(expected_recovery)


def test_gate_rejects_missing_anime_certification(tmp_path):
    ignored_anime_tests = tuple(f"--ignore={path}" for path in ANIME_CONTRACT_TESTS)
    completed, coverage, output, _ = _run_gate_probe(
        "missing_anime_certification",
        tmp_path,
        contract_test_paths=(
            *CORE_CONTRACT_TEST_PATHS,
            *SUBJECTS_CONTRACT_TESTS,
            *PROFILE_STATS_CONTRACT_TESTS,
            *COLLECTIONS_READ_CONTRACT_TESTS,
            *SCHEDULE_READ_CONTRACT_TESTS,
            *MEDIA_READ_CONTRACT_TESTS,
            *COLLECTIONS_WRITE_CONTRACT_TESTS,
            *SCHEDULE_WRITE_CONTRACT_TESTS,
            *MEDIA_WRITE_CONTRACT_TESTS,
        ),
        pytest_args=ignored_anime_tests,
    )
    _assert_gate_failure(
        completed,
        coverage,
        output,
        "Missing executed contracts:",
    )

    expected = _expected_observations()
    expected_anime = {row for row in expected if row[2].startswith("anime_")}
    missing = {tuple(row) for row in (coverage or {}).get("missing", [])}
    assert len(expected_anime) == 48
    assert missing == expected_anime
    assert (coverage or {}).get("expected") == len(expected)
    assert (coverage or {}).get("passed") == len(expected) - len(expected_anime)
    for name, version, scenario in sorted(expected_anime):
        assert f"{name}@{version}/{scenario}" in output


def test_gate_rejects_missing_subjects_certification(tmp_path):
    completed, coverage, output, _ = _run_gate_probe(
        "missing_subjects_certification",
        tmp_path,
        contract_test_paths=(
            *CORE_CONTRACT_TEST_PATHS,
            *ANIME_CONTRACT_TESTS,
            *PROFILE_STATS_CONTRACT_TESTS,
            *COLLECTIONS_READ_CONTRACT_TESTS,
            *SCHEDULE_READ_CONTRACT_TESTS,
            *MEDIA_READ_CONTRACT_TESTS,
            *COLLECTIONS_WRITE_CONTRACT_TESTS,
            *SCHEDULE_WRITE_CONTRACT_TESTS,
            *MEDIA_WRITE_CONTRACT_TESTS,
        ),
    )
    _assert_gate_failure(
        completed,
        coverage,
        output,
        "Missing executed contracts:",
    )

    from tests.capabilities.contracts.catalog import SUBJECTS_SCENARIOS

    expected = _expected_observations()
    expected_subjects = {row for row in expected if row[2] in SUBJECTS_SCENARIOS}
    missing = {tuple(row) for row in (coverage or {}).get("missing", [])}
    assert len(expected_subjects) == 30
    assert missing == expected_subjects
    assert (coverage or {}).get("expected") == len(expected)
    assert (coverage or {}).get("passed") == len(expected) - len(expected_subjects)
    for name, version, scenario in sorted(expected_subjects):
        assert f"{name}@{version}/{scenario}" in output


def test_gate_rejects_missing_recommendation_stats_certification(tmp_path):
    completed, coverage, output, _ = _run_gate_probe(
        "missing_recommendation_stats_certification",
        tmp_path,
        contract_test_paths=(
            *CORE_CONTRACT_TEST_PATHS,
            *ANIME_CONTRACT_TESTS,
            *SUBJECTS_CONTRACT_TESTS,
            *SCHEDULE_READ_CONTRACT_TESTS,
            *COLLECTIONS_READ_CONTRACT_TESTS,
            *MEDIA_READ_CONTRACT_TESTS,
            *COLLECTIONS_WRITE_CONTRACT_TESTS,
            *SCHEDULE_WRITE_CONTRACT_TESTS,
            *MEDIA_WRITE_CONTRACT_TESTS,
        ),
    )
    _assert_gate_failure(
        completed,
        coverage,
        output,
        "Missing executed contracts:",
    )

    expected = _expected_observations()
    expected_profile_stats = {
        row for row in expected if row[2].startswith(("recommendation_", "stats_"))
    }
    missing = {tuple(row) for row in (coverage or {}).get("missing", [])}
    assert len(expected_profile_stats) == 24
    assert missing == expected_profile_stats
    assert (coverage or {}).get("expected") == len(expected)
    assert (coverage or {}).get("passed") == len(expected) - len(expected_profile_stats)
    for name, version, scenario in sorted(expected_profile_stats):
        assert f"{name}@{version}/{scenario}" in output


def test_gate_rejects_missing_collections_read_certification(tmp_path):
    completed, coverage, output, _ = _run_gate_probe(
        "missing_collections_read_certification",
        tmp_path,
        contract_test_paths=(
            *CORE_CONTRACT_TEST_PATHS,
            *ANIME_CONTRACT_TESTS,
            *SUBJECTS_CONTRACT_TESTS,
            *PROFILE_STATS_CONTRACT_TESTS,
            *SCHEDULE_READ_CONTRACT_TESTS,
            *MEDIA_READ_CONTRACT_TESTS,
            *COLLECTIONS_WRITE_CONTRACT_TESTS,
            *SCHEDULE_WRITE_CONTRACT_TESTS,
            *MEDIA_WRITE_CONTRACT_TESTS,
        ),
    )
    _assert_gate_failure(
        completed,
        coverage,
        output,
        "Missing executed contracts:",
    )

    from tests.capabilities.contracts.catalog import COLLECTIONS_READ_SCENARIOS

    expected = _expected_observations()
    expected_collections_read = {
        row for row in expected if row[2] in COLLECTIONS_READ_SCENARIOS
    }
    missing = {tuple(row) for row in (coverage or {}).get("missing", [])}
    assert len(expected_collections_read) == 18
    assert missing == expected_collections_read
    assert (coverage or {}).get("expected") == len(expected)
    assert (coverage or {}).get("passed") == len(expected) - len(
        expected_collections_read
    )
    for name, version, scenario in sorted(expected_collections_read):
        assert f"{name}@{version}/{scenario}" in output


def test_gate_rejects_missing_schedule_read_certification(tmp_path):
    completed, coverage, output, _ = _run_gate_probe(
        "missing_schedule_read_certification",
        tmp_path,
        contract_test_paths=(
            *CORE_CONTRACT_TEST_PATHS,
            *ANIME_CONTRACT_TESTS,
            *SUBJECTS_CONTRACT_TESTS,
            *PROFILE_STATS_CONTRACT_TESTS,
            *COLLECTIONS_READ_CONTRACT_TESTS,
            *MEDIA_READ_CONTRACT_TESTS,
            *COLLECTIONS_WRITE_CONTRACT_TESTS,
            *SCHEDULE_WRITE_CONTRACT_TESTS,
            *MEDIA_WRITE_CONTRACT_TESTS,
        ),
    )
    _assert_gate_failure(
        completed,
        coverage,
        output,
        "Missing executed contracts:",
    )

    from tests.capabilities.contracts.catalog import SCHEDULE_READ_SCENARIOS

    expected = _expected_observations()
    expected_schedule_read = {
        row for row in expected if row[2] in SCHEDULE_READ_SCENARIOS
    }
    missing = {tuple(row) for row in (coverage or {}).get("missing", [])}
    assert len(expected_schedule_read) == 18
    assert missing == expected_schedule_read
    assert (coverage or {}).get("expected") == len(expected)
    assert (coverage or {}).get("passed") == len(expected) - len(expected_schedule_read)
    for name, version, scenario in sorted(expected_schedule_read):
        assert f"{name}@{version}/{scenario}" in output


def test_gate_rejects_missing_media_read_certification(tmp_path):
    contract_test_paths = tuple(
        path for path in CONTRACT_TEST_PATHS if path not in MEDIA_READ_CONTRACT_TESTS
    )
    completed, coverage, output, _ = _run_gate_probe(
        "missing_media_read_certification",
        tmp_path,
        contract_test_paths=contract_test_paths,
    )
    _assert_gate_failure(
        completed,
        coverage,
        output,
        "Missing executed contracts:",
    )

    from tests.capabilities.contracts.catalog import MEDIA_READ_SCENARIOS

    expected = _expected_observations()
    expected_media_read = {row for row in expected if row[2] in MEDIA_READ_SCENARIOS}
    missing = {tuple(row) for row in (coverage or {}).get("missing", [])}
    assert len(expected_media_read) == 18
    assert missing == expected_media_read
    assert (coverage or {}).get("expected") == len(expected)
    assert (coverage or {}).get("passed") == len(expected) - 18
    for name, version, scenario in sorted(expected_media_read):
        assert f"{name}@{version}/{scenario}" in output


def test_gate_rejects_missing_media_write_certification(tmp_path):
    contract_test_paths = tuple(
        path for path in CONTRACT_TEST_PATHS if path not in MEDIA_WRITE_CONTRACT_TESTS
    )
    completed, coverage, output, _ = _run_gate_probe(
        "missing_media_write_certification",
        tmp_path,
        contract_test_paths=contract_test_paths,
    )
    _assert_gate_failure(
        completed,
        coverage,
        output,
        "Missing executed contracts:",
    )

    from tests.capabilities.contracts.catalog import MEDIA_WRITE_SCENARIOS

    expected = _expected_observations()
    expected_media_write = {row for row in expected if row[2] in MEDIA_WRITE_SCENARIOS}
    missing = {tuple(row) for row in (coverage or {}).get("missing", [])}
    assert len(expected_media_write) == 45
    assert missing == expected_media_write
    assert (coverage or {}).get("expected") == len(expected)
    assert (coverage or {}).get("passed") == len(expected) - 45
    for name, version, scenario in sorted(expected_media_write):
        assert f"{name}@{version}/{scenario}" in output


def test_gate_rejects_missing_collections_write_certification(tmp_path):
    completed, coverage, output, _ = _run_gate_probe(
        "missing_collections_write_certification",
        tmp_path,
        contract_test_paths=(
            *CORE_CONTRACT_TEST_PATHS,
            *ANIME_CONTRACT_TESTS,
            *SUBJECTS_CONTRACT_TESTS,
            *PROFILE_STATS_CONTRACT_TESTS,
            *COLLECTIONS_READ_CONTRACT_TESTS,
            *SCHEDULE_READ_CONTRACT_TESTS,
            *MEDIA_READ_CONTRACT_TESTS,
            *SCHEDULE_WRITE_CONTRACT_TESTS,
            *MEDIA_WRITE_CONTRACT_TESTS,
        ),
    )
    _assert_gate_failure(
        completed,
        coverage,
        output,
        "Missing executed contracts:",
    )

    from tests.capabilities.contracts.catalog import COLLECTIONS_WRITE_SCENARIOS

    expected = _expected_observations()
    expected_collections_write = {
        row for row in expected if row[2] in COLLECTIONS_WRITE_SCENARIOS
    }
    missing = {tuple(row) for row in (coverage or {}).get("missing", [])}
    assert len(expected_collections_write) == 64
    assert missing == expected_collections_write
    assert (coverage or {}).get("expected") == len(expected)
    assert (coverage or {}).get("passed") == len(expected) - len(
        expected_collections_write
    )
    for name, version, scenario in sorted(expected_collections_write):
        assert f"{name}@{version}/{scenario}" in output


def test_gate_rejects_missing_schedule_write_certification(tmp_path):
    completed, coverage, output, _ = _run_gate_probe(
        "missing_schedule_write_certification",
        tmp_path,
        contract_test_paths=(
            *CORE_CONTRACT_TEST_PATHS,
            *ANIME_CONTRACT_TESTS,
            *SUBJECTS_CONTRACT_TESTS,
            *PROFILE_STATS_CONTRACT_TESTS,
            *COLLECTIONS_READ_CONTRACT_TESTS,
            *SCHEDULE_READ_CONTRACT_TESTS,
            *MEDIA_READ_CONTRACT_TESTS,
            *COLLECTIONS_WRITE_CONTRACT_TESTS,
            *MEDIA_WRITE_CONTRACT_TESTS,
        ),
    )
    _assert_gate_failure(
        completed,
        coverage,
        output,
        "Missing executed contracts:",
    )

    from tests.capabilities.contracts.catalog import SCHEDULE_WRITE_SCENARIOS

    expected = _expected_observations()
    expected_schedule_write = {
        row for row in expected if row[2] in SCHEDULE_WRITE_SCENARIOS
    }
    missing = {tuple(row) for row in (coverage or {}).get("missing", [])}
    assert len(expected_schedule_write) == 54
    assert missing == expected_schedule_write
    assert (coverage or {}).get("expected") == len(expected)
    assert (coverage or {}).get("passed") == len(expected) - 54
    for name, version, scenario in sorted(expected_schedule_write):
        assert f"{name}@{version}/{scenario}" in output


def test_gate_rejects_a_skipped_required_marked_scenario(tmp_path):
    plugin_source = """
        import json
        import os
        from pathlib import Path

        import pytest


        @pytest.hookimpl(tryfirst=True)
        def pytest_collection_modifyitems(items):
            for item in items:
                marker = item.get_closest_marker("capability_contract")
                if marker is not None and marker.args[2] == "success":
                    item.add_marker(pytest.mark.skip(reason="gate self-test skip"))
                    Path(os.environ["CAPABILITY_GATE_PROBE_TARGET"]).write_text(
                        json.dumps(list(marker.args)), encoding="utf-8"
                    )
                    return
    """
    completed, coverage, output, evidence_dir = _run_gate_probe(
        "skipped_required_marked_scenario",
        tmp_path,
        plugin_source=plugin_source,
    )
    assert completed is not None, "gate subprocess exceeded its 120-second timeout"
    target_path = tmp_path / "probe-target.json"
    assert target_path.is_file(), output
    skipped = tuple(json.loads(target_path.read_text(encoding="utf-8")))
    _assert_gate_failure(
        completed,
        coverage,
        output,
        "Missing executed contracts:",
    )
    missing = {tuple(row) for row in (coverage or {}).get("missing", [])}
    assert missing == {skipped}
    assert (coverage or {}).get("expected") == len(_expected_observations())
    assert (coverage or {}).get("passed") == len(_expected_observations()) - 1
    assert (evidence_dir / "probe-target.json").is_file()


def test_gate_rejects_a_skipped_schedule_read_observation(tmp_path):
    plugin_source = """
        import json
        import os
        from pathlib import Path

        import pytest


        @pytest.hookimpl(tryfirst=True)
        def pytest_collection_modifyitems(items):
            target = ("list_schedules", "v1", "schedule_read_error")
            for item in items:
                marker = item.get_closest_marker("capability_contract")
                if marker is not None and tuple(marker.args) == target:
                    item.add_marker(pytest.mark.skip(reason="gate self-test skip"))
                    Path(os.environ["CAPABILITY_GATE_PROBE_TARGET"]).write_text(
                        json.dumps(list(marker.args)), encoding="utf-8"
                    )
                    return
    """
    completed, coverage, output, evidence_dir = _run_gate_probe(
        "skipped_schedule_read_observation",
        tmp_path,
        plugin_source=plugin_source,
    )
    assert completed is not None, "gate subprocess exceeded its 120-second timeout"
    target_path = tmp_path / "probe-target.json"
    assert target_path.is_file(), output
    skipped = tuple(json.loads(target_path.read_text(encoding="utf-8")))
    assert skipped == ("list_schedules", "v1", "schedule_read_error")
    assert skipped in _expected_observations()
    _assert_gate_failure(
        completed,
        coverage,
        output,
        "Missing executed contracts:",
    )
    missing = {tuple(row) for row in (coverage or {}).get("missing", [])}
    assert missing == {skipped}
    assert (coverage or {}).get("expected") == len(_expected_observations())
    assert (coverage or {}).get("passed") == len(_expected_observations()) - 1
    assert (evidence_dir / "probe-target.json").is_file()


def test_gate_rejects_a_skipped_media_read_observation(tmp_path):
    plugin_source = """
        import json
        import os
        from pathlib import Path

        import pytest


        @pytest.hookimpl(tryfirst=True)
        def pytest_collection_modifyitems(items):
            target = ("library_status", "v1", "media_read_error")
            for item in items:
                marker = item.get_closest_marker("capability_contract")
                if marker is not None and tuple(marker.args) == target:
                    item.add_marker(pytest.mark.skip(reason="gate self-test skip"))
                    Path(os.environ["CAPABILITY_GATE_PROBE_TARGET"]).write_text(
                        json.dumps(list(marker.args)), encoding="utf-8"
                    )
                    return
    """
    completed, coverage, output, evidence_dir = _run_gate_probe(
        "skipped_media_read_observation",
        tmp_path,
        plugin_source=plugin_source,
    )
    assert completed is not None, "gate subprocess exceeded its 120-second timeout"
    target_path = tmp_path / "probe-target.json"
    assert target_path.is_file(), output
    skipped = tuple(json.loads(target_path.read_text(encoding="utf-8")))
    assert skipped == ("library_status", "v1", "media_read_error")
    assert skipped in _expected_observations()
    _assert_gate_failure(
        completed,
        coverage,
        output,
        "Missing executed contracts:",
    )
    missing = {tuple(row) for row in (coverage or {}).get("missing", [])}
    assert missing == {skipped}
    assert (coverage or {}).get("expected") == len(_expected_observations())
    assert (coverage or {}).get("passed") == len(_expected_observations()) - 1
    assert (evidence_dir / "probe-target.json").is_file()


def test_gate_rejects_a_skipped_media_write_observation(tmp_path):
    plugin_source = """
        import json
        import os
        from pathlib import Path

        import pytest


        @pytest.hookimpl(tryfirst=True)
        def pytest_collection_modifyitems(items):
            target = ("add_rss_feed", "v1", "media_write_error")
            for item in items:
                marker = item.get_closest_marker("capability_contract")
                if marker is not None and tuple(marker.args) == target:
                    item.add_marker(pytest.mark.skip(reason="gate self-test skip"))
                    Path(os.environ["CAPABILITY_GATE_PROBE_TARGET"]).write_text(
                        json.dumps(list(marker.args)), encoding="utf-8"
                    )
                    return
    """
    completed, coverage, output, evidence_dir = _run_gate_probe(
        "skipped_media_write_observation",
        tmp_path,
        plugin_source=plugin_source,
    )
    assert completed is not None, "gate subprocess exceeded its 120-second timeout"
    target_path = tmp_path / "probe-target.json"
    assert target_path.is_file(), output
    skipped = tuple(json.loads(target_path.read_text(encoding="utf-8")))
    assert skipped == ("add_rss_feed", "v1", "media_write_error")
    assert skipped in _expected_observations()
    _assert_gate_failure(
        completed,
        coverage,
        output,
        "Missing executed contracts:",
    )
    missing = {tuple(row) for row in (coverage or {}).get("missing", [])}
    assert missing == {skipped}
    assert (coverage or {}).get("expected") == len(_expected_observations())
    assert (coverage or {}).get("passed") == len(_expected_observations()) - 1
    assert (evidence_dir / "probe-target.json").is_file()


def test_gate_rejects_a_skipped_schedule_write_observation(tmp_path):
    plugin_source = """
        import json
        import os
        from pathlib import Path

        import pytest


        @pytest.hookimpl(tryfirst=True)
        def pytest_collection_modifyitems(items):
            target = ("create_schedule", "v1", "schedule_write_error")
            for item in items:
                marker = item.get_closest_marker("capability_contract")
                if marker is not None and tuple(marker.args) == target:
                    item.add_marker(pytest.mark.skip(reason="gate self-test skip"))
                    Path(os.environ["CAPABILITY_GATE_PROBE_TARGET"]).write_text(
                        json.dumps(list(marker.args)), encoding="utf-8"
                    )
                    return
    """
    completed, coverage, output, evidence_dir = _run_gate_probe(
        "skipped_schedule_write_observation",
        tmp_path,
        plugin_source=plugin_source,
    )
    assert completed is not None, "gate subprocess exceeded its 120-second timeout"
    target_path = tmp_path / "probe-target.json"
    assert target_path.is_file(), output
    skipped = tuple(json.loads(target_path.read_text(encoding="utf-8")))
    assert skipped == ("create_schedule", "v1", "schedule_write_error")
    assert skipped in _expected_observations()
    _assert_gate_failure(
        completed,
        coverage,
        output,
        "Missing executed contracts:",
    )
    missing = {tuple(row) for row in (coverage or {}).get("missing", [])}
    assert missing == {skipped}
    assert (coverage or {}).get("expected") == len(_expected_observations())
    assert (coverage or {}).get("passed") == len(_expected_observations()) - 1
    assert (evidence_dir / "probe-target.json").is_file()


def test_gate_rejects_an_empty_selected_matrix(tmp_path):
    completed, coverage, output, _ = _run_gate_probe(
        "no_action_matrix_selected",
        tmp_path,
        pytest_args=("-k", "gate_probe_no_matching_contract_item"),
    )
    _assert_gate_failure(
        completed,
        coverage,
        output,
        "Missing executed contracts:",
    )
    assert completed is not None, "gate subprocess exceeded its 120-second timeout"
    assert completed.returncode == 5
    assert (coverage or {}).get("passed") == 0
    assert (coverage or {}).get("expected") == len(_expected_observations())


def test_gate_accepts_the_complete_registry_matrix(tmp_path):
    completed, coverage, output, _ = _run_gate_probe(
        "complete_registry_matrix", tmp_path
    )
    expected = _expected_observations()
    assert completed is not None, "gate subprocess exceeded its 120-second timeout"
    assert completed.returncode == 0, output
    assert coverage is not None, "gate subprocess did not write a coverage report"
    assert coverage["gate"] == "pass"
    assert coverage["errors"] == []
    assert coverage["expected"] == len(expected)
    assert coverage["passed"] == len(expected)
    assert coverage["missing"] == []


@pytest.mark.parametrize("failure_kind", ["xfail", "teardown_failure", "unobserved"])
def test_gate_sessionfinish_excludes_nonpassing_required_observations(
    tmp_path, failure_kind
):
    """Synthetic hook rows isolate gate accounting, not action execution."""
    from tests.capabilities.contracts.plugin import pytest_sessionfinish
    from tests.capabilities.contracts.catalog import SCHEDULE_WRITE_SCENARIOS

    expected = _expected_observations()
    target = sorted(expected)[0]
    rows = {
        f"synthetic-item-{index}": {
            "key": observation,
            "stages": {"setup": "passed", "call": "passed", "teardown": "passed"},
            "observed": observation,
            "xfail": False,
        }
        for index, observation in enumerate(sorted(expected))
    }
    target_row = next(row for row in rows.values() if row["key"] == target)
    if failure_kind == "xfail":
        target_row["xfail"] = True
    elif failure_kind == "teardown_failure":
        target_row["stages"]["teardown"] = "failed"
    else:
        target_row["observed"] = None

    report_path = tmp_path / f"{failure_kind}-coverage.json"

    class _PluginManager:
        @staticmethod
        def getplugin(_name):
            return None

    class _Config:
        def __init__(self):
            self._capability_contract_reports = rows
            self.pluginmanager = _PluginManager()

        @staticmethod
        def getoption(name):
            if name == "--capability-contract-gate":
                return True
            if name == "--capability-contract-report":
                return str(report_path)
            raise AssertionError(f"Unexpected pytest option: {name}")

    class _Session:
        def __init__(self):
            self.config = _Config()
            self.exitstatus = 0

    session = _Session()
    pytest_sessionfinish(session, 0)
    coverage = json.loads(report_path.read_text(encoding="utf-8"))

    assert session.exitstatus == 1
    assert coverage["gate"] == "fail"
    assert coverage["expected"] == len(expected)
    assert coverage["passed"] == len(expected) - 1
    assert coverage["missing"] == [list(target)]
    assert all(
        coverage["dimensions"][scenario] == {"expected": 6, "passed": 6}
        for scenario in SCHEDULE_WRITE_SCENARIOS
    )
    assert coverage["errors"] == [
        "Missing executed contracts: "
        + ", ".join(
            f"{name}@{version}/{scenario}" for name, version, scenario in [target]
        )
    ]
