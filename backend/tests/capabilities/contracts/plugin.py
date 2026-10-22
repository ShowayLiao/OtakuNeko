"""Opt-in CI gate: only assertions followed by successful teardown count."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import Any

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--capability-contract-gate",
        action="store_true",
        help="Require complete executed public action contracts",
    )
    parser.addoption(
        "--capability-contract-report",
        default=".runtime/capability-contracts/coverage.json",
        help="Safe JSON coverage report path",
    )


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "capability_contract(name, version, scenario): required contract observation",
    )
    config._capability_contract_reports = {}


def record(request, key: tuple[str, str], scenario: str) -> None:
    """Call only after all scenario assertions; collection/skip cannot count."""
    request.node._capability_contract_observed = (*key, scenario)


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    marker = item.get_closest_marker("capability_contract")
    if marker is None:
        return
    reports = item.config._capability_contract_reports
    row = reports.setdefault(
        item.nodeid, {"key": tuple(marker.args), "stages": {}, "observed": None}
    )
    row["stages"][report.when] = report.outcome
    row["xfail"] = row.get("xfail", False) or hasattr(report, "wasxfail")
    if report.when == "call":
        row["observed"] = getattr(item, "_capability_contract_observed", None)
        row["duration_seconds"] = report.duration


def pytest_sessionfinish(session, exitstatus):
    config = session.config
    if not config.getoption("--capability-contract-gate"):
        return
    # -p loads before tests/conftest establishes isolated settings. Application
    # imports must remain lazy or the plugin could capture developer .env state.
    from tests.capabilities.contracts.catalog import (
        cases,
        census,
        coverage_errors,
        expected_observations,
        fixture_errors,
    )

    rows = config._capability_contract_reports
    passed = {
        row["key"]
        for row in rows.values()
        if row["observed"] == row["key"]
        and not row.get("xfail")
        and row["stages"] == {"setup": "passed", "call": "passed", "teardown": "passed"}
    }
    errors = []
    actions: dict = {}
    examples: dict = {}
    expected: set = set()
    try:
        actions, examples = census(), cases()
        errors.extend(fixture_errors(actions, examples))
        expected = expected_observations(actions, examples)
        errors.extend(coverage_errors(expected, passed))
    except Exception as exc:
        # Avoid leaking fixture/dependency exception messages into public evidence.
        errors.append(
            f"Contract inventory could not be evaluated: {type(exc).__name__}"
        )
    duplicate_counts = Counter(row["key"] for row in rows.values())
    if any(count > 1 for count in duplicate_counts.values()):
        errors.append("Duplicate action/scenario execution markers")
    dimensions: dict[str, Any] = {}
    for scenario in sorted({key[2].split(":")[0] for key in expected}):
        dimension_expected = {
            key for key in expected if key[2].split(":")[0] == scenario
        }
        dimensions[scenario] = {
            "expected": len(dimension_expected),
            "passed": len(dimension_expected & passed),
        }
    payload = {
        "version": "v1",
        "gate": "fail" if errors or exitstatus else "pass",
        "actions": len(actions),
        "side_effect_actions": sum(d.is_side_effect for d in actions.values()),
        "read_actions": sum(not d.is_side_effect for d in actions.values()),
        "fixtures": len(examples),
        "expected": len(expected),
        "passed": len(expected & passed),
        "missing": [list(key) for key in sorted(expected - passed)],
        "open_output_schemas": sum(
            d.output_schema == {"type": "object", "additionalProperties": True}
            for d in actions.values()
        ),
        "dimensions": dimensions,
        "scenario_elapsed_seconds": round(
            sum(row.get("duration_seconds", 0) for row in rows.values()), 6
        ),
        "skipped_scenarios": sum(
            "skipped" in row["stages"].values() for row in rows.values()
        ),
        "failed_scenarios": sum(
            "failed" in row["stages"].values() for row in rows.values()
        ),
        "xfail_scenarios": sum(bool(row.get("xfail")) for row in rows.values()),
        "actions_without_required_input": [
            list(key)
            for key in sorted(actions)
            if key in examples
            and not any(
                item[:2] == key and item[2].startswith("required:") for item in expected
            )
        ],
        "declared_output_required_actions": [
            list(key)
            for key, descriptor in sorted(actions.items())
            if descriptor.output_schema.get("required")
        ],
        "errors": errors,
        "evidence_scope": {
            "success": "real registered Capability.execute through shared Runtime Dispatcher",
            "error_timeout_isolation_unsafe_output": "Dispatcher boundary fault injection; not domain implementation failure coverage",
            "anime_certification": "Real registered Anime handlers; only imported Bangumi dependencies are isolated. Six anime_* scenarios are mandatory per action.",
            "subjects_certification": "Real registered Subjects handlers; imported domain dependencies are isolated for six subjects_* scenarios per action. Additional service and HTTP/JWT tests use real SQL views with fake external I/O.",
            "recommendation_certification": "Real registered Recommendation handlers through the shared Runtime Dispatcher with imported service/computation dependencies injected at their boundaries. Six recommendation_* scenarios per action; HTTP/JWT and SQL behavior are certified separately.",
            "stats_certification": "Real registered Stats handlers through the shared Runtime Dispatcher with imported service/repository dependencies injected at their boundaries. Six stats_* scenarios per action; HTTP/JWT and SQL behavior are certified separately.",
            "collections_read_certification": (
                "Real registered non-side-effect Collection handlers through the "
                "shared Runtime Dispatcher with imported handler dependencies "
                "isolated. Six collections_read_* scenarios apply to each of the "
                "three current read actions; collection writes are outside this "
                "evidence. HTTP/API, service, and SQL behavior are certified "
                "separately in tests/api/test_collections_read_certification.py "
                "and tests/capabilities/test_collections_read_semantics.py."
            ),
            "schedule_read_certification": (
                "Real registered non-side-effect Schedule handlers through the "
                "shared Runtime Dispatcher with imported handler dependencies "
                "isolated. Six schedule_read_* scenarios apply to the three "
                "frozen Schedule read actions; Schedule writes are outside this "
                "evidence. Runtime/JWT, REST regressions, and SQL behavior are "
                "certified separately in "
                "tests/api/test_schedule_read_certification.py, "
                "tests/api/test_schedule_contract.py, and "
                "tests/capabilities/test_schedule_read_semantics.py."
            ),
            "collections_write_certification": (
                "Real registered side-effect Collection handlers through the "
                "shared Runtime Dispatcher with only imported handler dependencies "
                "isolated. Eight collections_write_* scenarios apply to each of "
                "the eight current write actions. Actual HTTP/JWT and SQL behavior "
                "are certified separately in "
                "tests/api/test_collections_write_certification.py and "
                "tests/capabilities/test_collections_write_semantics.py."
            ),
        },
    }
    target = Path(config.getoption("--capability-contract-report"))
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if errors:
        reporter = config.pluginmanager.getplugin("terminalreporter")
        if reporter:
            reporter.write_sep("=", "Capability contract gate FAILED", red=True)
            for error in errors:
                reporter.write_line(error, red=True)
        if session.exitstatus == 0:
            session.exitstatus = pytest.ExitCode.TESTS_FAILED
