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
    if report.when in {"setup", "call", "teardown"} and report.outcome != "passed":
        excinfo = getattr(call, "excinfo", None)
        row.setdefault("failures", []).append(
            {
                "stage": report.when,
                "outcome": report.outcome,
                "exception_type": getattr(
                    getattr(excinfo, "type", None), "__name__", None
                ),
            }
        )
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
        build_capability_registry,
        cases,
        census,
        coverage_errors,
        expected_observations,
        fixture_errors,
        inventory,
        invocation_audit,
    )

    errors = []
    raw_rows = config._capability_contract_reports
    rows: dict[str, dict[str, Any]] = {}
    malformed = []
    for nodeid, row in raw_rows.items():
        key = row.get("key")
        if (
            not isinstance(key, tuple)
            or len(key) != 3
            or not all(isinstance(value, str) for value in key)
        ):
            malformed.append(nodeid)
            continue
        rows[nodeid] = row
    if malformed:
        errors.append(
            "Malformed capability_contract markers: " + ", ".join(sorted(malformed))
        )
    passed_rows = {
        nodeid
        for nodeid, row in rows.items()
        if row["observed"] == row["key"]
        and not row.get("xfail")
        and row["stages"] == {"setup": "passed", "call": "passed", "teardown": "passed"}
    }
    passed = {rows[nodeid]["key"] for nodeid in passed_rows}
    actions: dict = {}
    examples: dict = {}
    expected: set = set()
    inventory_rows: list[dict[str, Any]] = []
    audit: dict[str, Any] = {
        "source_root": "app",
        "scanned_files": 0,
        "calls": [],
        "unregistered": [],
    }
    try:
        registry = build_capability_registry()
        actions, examples = census(registry), cases()
        errors.extend(fixture_errors(actions, examples))
        expected = expected_observations(actions, examples)
        errors.extend(coverage_errors(expected, passed))
        inventory_rows = inventory(actions, registry)
        audit = invocation_audit(registry=registry)
        if audit["unregistered"]:
            errors.append(
                "Unregistered capability calls: "
                + ", ".join(
                    f"{call['file']}:{call['line']} {call['action']}"
                    for call in audit["unregistered"]
                )
            )
    except Exception as exc:
        # Avoid leaking fixture/dependency exception messages into public evidence.
        message = str(exc)
        if message.startswith("Capability invocation source is not parseable: "):
            errors.append(message)
        else:
            errors.append(
                f"Contract inventory could not be evaluated: {type(exc).__name__}"
            )
    duplicate_counts = Counter(row["key"] for row in rows.values())
    if any(count > 1 for count in duplicate_counts.values()):
        errors.append("Duplicate action/scenario execution markers")

    def row_status(nodeid: str, row: dict[str, Any]) -> str:
        if nodeid in passed_rows:
            return "passed"
        stages = row.get("stages", {})
        if any(outcome == "failed" for outcome in stages.values()):
            return "failed"
        if row.get("xfail"):
            return "xfail"
        if any(outcome == "skipped" for outcome in stages.values()):
            return "skipped"
        return "not_observed"

    test_mapping = []
    failure_reasons = []
    for nodeid, row in sorted(rows.items()):
        key = row["key"]
        status = row_status(nodeid, row)
        test_mapping.append(
            {
                "nodeid": nodeid,
                "action": key[0],
                "version": key[1],
                "scenario": key[2],
                "status": status,
                "observed": row.get("observed") == key,
                "stages": dict(row["stages"]),
                "failures": list(row.get("failures", [])),
            }
        )
        if status != "passed":
            failure_reasons.append(
                {
                    "action": key[0],
                    "version": key[1],
                    "scenario": key[2],
                    "nodeid": nodeid,
                    "status": status,
                    "failures": list(row.get("failures", [])),
                }
            )
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
        "version": "v2",
        "gate": "fail" if errors or exitstatus else "pass",
        "actions": len(actions),
        "side_effect_actions": sum(d.is_side_effect for d in actions.values()),
        "read_actions": sum(not d.is_side_effect for d in actions.values()),
        "fixtures": len(examples),
        "inventory": inventory_rows,
        "test_mapping": test_mapping,
        "failure_reasons": failure_reasons,
        "unregistered_calls": audit["unregistered"],
        "invocation_audit": audit,
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
            "media_read_certification": (
                "Real registered non-side-effect Media handlers through the "
                "shared Runtime Dispatcher with only the external qB SDK/client "
                "boundary isolated. Six media_read_* scenarios apply to the "
                "three frozen Media read actions; the local library status "
                "check does not probe qB connectivity and Media writes are "
                "outside this evidence. HTTP/API and service behavior are "
                "outside this handler gate's evidence boundary."
            ),
            "media_write_certification": (
                "Real registered side-effect Media handlers through the shared "
                "Runtime Dispatcher with external qB SDK/client calls isolated. "
                "Nine media_write_* scenarios apply to each of the five current "
                "Media write actions. REST/JWT and service/SQL behavior are "
                "certified separately by tests/api/test_media_write_certification.py, "
                "tests/capabilities/test_media_write_semantics.py, and "
                "tests/services/test_qb_service.py."
            ),
            "system_certification": (
                "Real registered System handler through the shared Runtime "
                "Dispatcher. Six system_* scenarios apply to get_current_time@v1. "
                "The local clock is replaced for deterministic success and "
                "clock-failure injection; the registered execute method is "
                "wrapped for argument observation in the authorization and "
                "dispatcher scenarios, replaced by an infinite blocker for the "
                "timeout probe, replaced by a raiser for the isolation failure "
                "half, and replaced with unsafe output for the serialization "
                "boundary probe. Dispatcher._run_with_controls is armed only for "
                "the timeout probe. HTTP/JWT identity boundaries, error envelopes, "
                "and exception containment are certified separately in "
                "tests/api/test_system_certification.py. The System action is "
                "public, identity-free, and not exposed over MCP."
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
            "schedule_write_certification": (
                "Real registered side-effect Schedule handlers through the "
                "shared Runtime Dispatcher with only imported handler "
                "dependencies isolated. Nine schedule_write_* scenarios apply "
                "to each of the six frozen Schedule write actions. The recovery "
                "scenario rebuilds Runtime/Adapter/Session from durable state; "
                "process kill/restore, HTTP/JWT, and SQL behavior are certified "
                "separately in tests/acceptance/test_schedule_write_kill_restore.py, "
                "tests/api/test_schedule_write_certification.py, and "
                "tests/capabilities/test_schedule_write_semantics.py."
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
