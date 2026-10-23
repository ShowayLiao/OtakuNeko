"""Full capability CI summary gate: inventory, mapping, and blocking checks."""

from __future__ import annotations

import json
from pathlib import Path
import textwrap
from typing import Any
import xml.etree.ElementTree as ET

import yaml  # type: ignore[import-untyped]
import pytest

from scripts.capability_ci_summary import (
    load_junit,
    main,
    render_markdown,
    summarize,
)

BACKEND_ROOT = Path(__file__).resolve().parents[3]


def _inventory(
    public_name: str = "alpha",
    version: str = "v1",
    *,
    owner: str = "demo",
    side_effect: bool = False,
) -> dict:
    return {
        "public_name": public_name,
        "name": public_name,
        "version": version,
        "owner": owner,
        "side_effect": side_effect,
        "requires_auth": side_effect,
        "approval_required": side_effect,
        "idempotency_mode": "required" if side_effect else "none",
        "timeout_seconds": 30.0,
        "retry_class": "none",
        "fingerprint": "a" * 64,
    }


def _mapping(
    scenario: str,
    *,
    nodeid: str | None = None,
    status: str = "passed",
    action: str = "alpha",
    version: str = "v1",
    failures: list[dict] | None = None,
) -> dict:
    return {
        "nodeid": nodeid or f"tests/demo.py::test_alpha_{scenario}",
        "action": action,
        "version": version,
        "scenario": scenario,
        "status": status,
        "stages": {
            "setup": "passed",
            "call": "passed" if status == "passed" else "failed",
            "teardown": "passed",
        },
        "observed": status == "passed",
        "failures": failures or [],
    }


def _report(**overrides) -> dict:
    report = {
        "version": "v2",
        "gate": "pass",
        "actions": 1,
        "expected": 2,
        "passed": 2,
        "missing": [],
        "errors": [],
        "inventory": [_inventory()],
        "test_mapping": [_mapping("schema"), _mapping("success")],
        "failure_reasons": [],
        "unregistered_calls": [],
        "invocation_audit": {"scanned_files": 1, "calls": [], "unregistered": []},
    }
    report.update(overrides)
    return report


def _write_junit(
    path: Path,
    *,
    tests: int = 2,
    failures: int = 0,
    errors: int = 0,
    skipped: int = 0,
    failing_case: str | None = None,
) -> Path:
    suite = ET.Element(
        "testsuite",
        {
            "name": "pytest",
            "tests": str(tests),
            "failures": str(failures),
            "errors": str(errors),
            "skipped": str(skipped),
        },
    )
    for index in range(tests - failures - errors - skipped):
        ET.SubElement(
            suite, "testcase", {"classname": "tests.demo", "name": f"pass_{index}"}
        )
    for index in range(skipped):
        case = ET.SubElement(
            suite, "testcase", {"classname": "tests.demo", "name": f"skip_{index}"}
        )
        ET.SubElement(case, "skipped")
    if failing_case is not None:
        case = ET.SubElement(
            suite, "testcase", {"classname": "tests.demo", "name": failing_case}
        )
        ET.SubElement(case, "failure", {"message": "assertion failed"})
    ET.ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)
    return path


def _junit(path: Path, **kwargs) -> dict:
    return load_junit(_write_junit(path, **kwargs))


def test_summary_passes_a_complete_gate_report(tmp_path):
    result = summarize(_report(), _junit(tmp_path / "junit.xml"))

    assert result["gate"] == "pass"
    assert result["exit_code"] == 0
    assert result["registry"] == {
        "actions": 1,
        "owners": 1,
        "side_effect_actions": 0,
        "read_actions": 1,
    }
    assert result["coverage"] == {
        "expected": 2,
        "passed": 2,
        "missing": 0,
        "ratio": 1.0,
    }
    assert result["tests"]["passed"] == 2
    assert all(not findings for findings in result["checks"].values())


def test_summary_blocks_missing_executed_tests(tmp_path):
    report = _report(
        gate="fail",
        passed=1,
        missing=[["alpha", "v1", "success"]],
        errors=["Missing executed contracts: alpha@v1/success"],
        test_mapping=[_mapping("schema")],
    )

    result = summarize(report, _junit(tmp_path / "junit.xml"))

    assert result["gate"] == "fail"
    assert result["exit_code"] == 1
    assert result["checks"]["missing_tests"] == [
        {
            "kind": "missing_observation",
            "action": "alpha",
            "version": "v1",
            "scenario": "success",
        }
    ]
    assert "alpha@v1/success" in render_markdown(result)


def test_summary_blocks_inventory_action_without_mapping(tmp_path):
    report = _report(expected=0, passed=0, test_mapping=[], missing=[])

    result = summarize(report, _junit(tmp_path / "junit.xml"))

    assert result["gate"] == "fail"
    assert result["checks"]["missing_tests"] == [
        {"kind": "unmapped_action", "action": "alpha", "version": "v1"}
    ]


def test_summary_blocks_unregistered_static_calls(tmp_path):
    call = {
        "file": "app/probe.py",
        "line": 12,
        "receiver": "capability",
        "method": "execute",
        "kind": "action",
        "action": "ghost",
        "registered": False,
    }
    report = _report(
        gate="fail",
        unregistered_calls=[call],
        invocation_audit={
            "scanned_files": 1,
            "calls": [call],
            "unregistered": [call],
        },
        errors=["Unregistered capability calls: app/probe.py:12 ghost"],
    )

    result = summarize(report, _junit(tmp_path / "junit.xml"))

    assert result["gate"] == "fail"
    assert result["checks"]["unregistered_calls"] == [
        {**call, "kind": "unregistered_call"}
    ]
    assert "app/probe.py:12" in render_markdown(result)


def test_summary_blocks_unknown_contract_markers(tmp_path):
    report = _report(
        gate="fail",
        test_mapping=[_mapping("schema"), _mapping("success", action="ghost")],
        errors=["Unexpected contracts: ghost@v1/success"],
    )

    result = summarize(report, _junit(tmp_path / "junit.xml"))

    assert result["gate"] == "fail"
    assert result["checks"]["unregistered_calls"] == [
        {
            "kind": "unexpected_contract",
            "action": "ghost",
            "version": "v1",
            "scenario": "success",
            "nodeid": "tests/demo.py::test_alpha_success",
        }
    ]


def test_summary_blocks_contract_failures_with_reasons(tmp_path):
    failure: dict[str, Any] = {
        "action": "alpha",
        "version": "v1",
        "scenario": "success",
        "nodeid": "tests/demo.py::test_alpha_success",
        "status": "failed",
        "failures": [
            {"stage": "call", "outcome": "failed", "exception_type": "AssertionError"}
        ],
    }
    report = _report(
        gate="fail",
        passed=1,
        missing=[],
        failure_reasons=[failure],
        test_mapping=[
            _mapping("schema"),
            _mapping(
                "success",
                status="failed",
                failures=failure["failures"],
            ),
        ],
        errors=[],
    )

    result = summarize(report, _junit(tmp_path / "junit.xml"))

    assert result["gate"] == "fail"
    assert result["checks"]["contract_failures"] == [
        {"kind": "contract_failure", **failure}
    ]
    markdown = render_markdown(result)
    assert "AssertionError" in markdown
    assert "call" in markdown


def test_summary_deduplicates_contract_failure_sources(tmp_path):
    failure: dict[str, Any] = {
        "action": "alpha",
        "version": "v1",
        "scenario": "success",
        "nodeid": "tests/demo.py::test_alpha_success",
        "status": "failed",
        "plugin_field": "preserved",
        "failures": [
            {"stage": "call", "outcome": "failed", "exception_type": "AssertionError"}
        ],
    }
    report = _report(
        gate="fail",
        passed=1,
        test_mapping=[
            _mapping("schema"),
            _mapping(
                "success",
                status="failed",
                failures=[
                    {
                        "stage": "call",
                        "outcome": "failed",
                        "exception_type": "AssertionError",
                    }
                ],
            ),
        ],
        failure_reasons=[failure],
        errors=[],
    )

    result = summarize(report, _junit(tmp_path / "junit.xml"))

    assert len(result["checks"]["contract_failures"]) == 1
    entry = result["checks"]["contract_failures"][0]
    assert entry["plugin_field"] == "preserved"
    assert entry["failures"][0]["exception_type"] == "AssertionError"


def test_summary_blocks_junit_failures_outside_contract_matrix(tmp_path):
    junit = _junit(
        tmp_path / "junit.xml", tests=3, failures=1, failing_case="test_other"
    )

    result = summarize(_report(), junit)

    assert result["gate"] == "fail"
    assert result["checks"]["test_failures"] == [
        {"kind": "test_failure", "case": "tests.demo::test_other", "status": "failure"}
    ]


def test_summary_blocks_empty_junit_evidence(tmp_path):
    junit = _junit(tmp_path / "junit.xml", tests=0)

    result = summarize(_report(), junit)

    assert result["gate"] == "fail"
    assert any(
        "no test cases" in error for error in result["checks"]["integrity_errors"]
    )


def test_summary_blocks_junit_smaller_than_contract_matrix(tmp_path):
    junit = _junit(tmp_path / "junit.xml", tests=1)

    result = summarize(_report(), junit)

    assert result["gate"] == "fail"
    assert any(
        "smaller than contract observations" in error
        for error in result["checks"]["integrity_errors"]
    )


def test_summary_blocks_junit_passed_smaller_than_contract_matrix(tmp_path):
    junit = _junit(tmp_path / "junit.xml", tests=2, skipped=1)

    result = summarize(_report(), junit)

    assert result["gate"] == "fail"
    assert any(
        "passed count is smaller" in error
        for error in result["checks"]["integrity_errors"]
    )


def test_summary_blocks_nonpassing_mapping_without_failure_reasons(tmp_path):
    report = _report(
        gate="pass",
        test_mapping=[_mapping("schema"), _mapping("success", status="skipped")],
    )

    result = summarize(report, _junit(tmp_path / "junit.xml"))

    assert result["gate"] == "fail"
    assert result["checks"]["contract_failures"] == [
        {
            "kind": "contract_failure",
            "action": "alpha",
            "version": "v1",
            "scenario": "success",
            "nodeid": "tests/demo.py::test_alpha_success",
            "status": "skipped",
            "failures": [],
        }
    ]


def test_summary_blocks_empty_static_audit_evidence(tmp_path):
    report = _report(
        invocation_audit={"scanned_files": 0, "calls": [], "unregistered": []}
    )

    result = summarize(report, _junit(tmp_path / "junit.xml"))

    assert result["gate"] == "fail"
    assert any(
        "scanned no source files" in error
        for error in result["checks"]["integrity_errors"]
    )


def test_summary_fails_closed_on_malformed_rows(tmp_path):
    report = _report(
        inventory=[_inventory(), "not-an-object"],
        test_mapping=[_mapping("schema"), "not-an-object", _mapping("success")],
    )

    result = summarize(report, _junit(tmp_path / "junit.xml"))

    assert result["gate"] == "fail"
    assert any(
        "non-object row" in error for error in result["checks"]["integrity_errors"]
    )
    assert "Registry inventory" in render_markdown(result)


def test_summary_blocks_gate_errors_without_structured_missing_evidence(tmp_path):
    report = _report(
        gate="pass",
        errors=["Missing executed contracts: alpha@v1/success"],
    )

    result = summarize(report, _junit(tmp_path / "junit.xml"))

    assert result["gate"] == "fail"
    assert result["checks"]["missing_tests"] == [
        {
            "kind": "gate_error",
            "reason": "Missing executed contracts: alpha@v1/success",
        }
    ]


def test_summary_blocks_gate_errors_without_structured_unregistered_evidence(
    tmp_path,
):
    report = _report(gate="pass", errors=["Unexpected contracts: ghost@v1/success"])

    result = summarize(report, _junit(tmp_path / "junit.xml"))

    assert result["gate"] == "fail"
    assert result["checks"]["unregistered_calls"] == [
        {
            "kind": "gate_error",
            "reason": "Unexpected contracts: ghost@v1/success",
        }
    ]


def test_summary_blocks_unexplained_gate_failure(tmp_path):
    report = _report(gate="fail")

    result = summarize(report, _junit(tmp_path / "junit.xml"))

    assert result["gate"] == "fail"
    assert result["checks"]["contract_failures"] == []
    assert any(
        "did not pass without structured evidence" in error
        for error in result["checks"]["integrity_errors"]
    )


def test_summary_fails_closed_on_missing_report_and_junit(tmp_path):
    output = tmp_path / "summary.json"
    markdown = tmp_path / "summary.md"

    code = main(
        [
            "--report",
            str(tmp_path / "missing.json"),
            "--junit",
            str(tmp_path / "missing.xml"),
            "--output",
            str(output),
            "--markdown",
            str(markdown),
        ]
    )

    saved = json.loads(output.read_text(encoding="utf-8"))
    assert code == 2
    assert saved["gate"] == "fail"
    assert saved["checks"]["integrity_errors"]
    assert "missing" in markdown.read_text(encoding="utf-8").lower()


def test_cli_writes_summary_and_step_summary(tmp_path):
    report = _report()
    report_path = tmp_path / "coverage.json"
    report_path.write_text(json.dumps(report), encoding="utf-8")
    junit_path = _write_junit(tmp_path / "junit.xml")
    output = tmp_path / "summary.json"
    markdown = tmp_path / "summary.md"
    step_summary = tmp_path / "step.md"

    code = main(
        [
            "--report",
            str(report_path),
            "--junit",
            str(junit_path),
            "--output",
            str(output),
            "--markdown",
            str(markdown),
            "--step-summary",
            str(step_summary),
        ]
    )

    assert code == 0
    assert json.loads(output.read_text(encoding="utf-8"))["gate"] == "pass"
    assert "Capability CI summary gate: PASS" in markdown.read_text(encoding="utf-8")
    assert "Capability CI summary gate: PASS" in step_summary.read_text(
        encoding="utf-8"
    )


def test_static_audit_flags_literal_unregistered_calls(tmp_path):
    from app.capabilities.factory import build_capability_registry
    from tests.capabilities.contracts.catalog import invocation_audit

    source = tmp_path / "app"
    source.mkdir()
    (source / "sample.py").write_text(
        textwrap.dedent(
            """
            async def demo(self, db, connection):
                await self._capability.execute("get_detail")
                await self._capability.execute("ghost")
                await self._anime.execute("ghost_anime")
                await self._capability.execute("get_anime_info")
                await db.execute("SELECT 1")
                await connection.execute("commit")
                await self._task_session.execute("ghost_task_session")
                await self._capability.execute(action="ghost_keyword")
                await self._execute_capability(
                    "get_detail", public_action="get_anime_info"
                )
                await self._execute_capability(
                    action="get_detail", public_action="get_detail"
                )
                await self._execute_capability(
                    "get_detail", public_action="ghost_public"
                )
            """
        ),
        encoding="utf-8",
    )

    audit = invocation_audit(
        source,
        registry=build_capability_registry(),
        display_root=tmp_path,
    )

    assert audit["scanned_files"] == 1
    assert [(call["action"], call["kind"]) for call in audit["calls"]] == [
        ("get_detail", "action"),
        ("ghost", "action"),
        ("ghost_anime", "action"),
        ("get_anime_info", "action"),
        ("ghost_task_session", "action"),
        ("ghost_keyword", "action"),
        ("get_detail", "action"),
        ("get_anime_info", "public_action"),
        ("get_detail", "action"),
        ("get_detail", "public_action"),
        ("get_detail", "action"),
        ("ghost_public", "public_action"),
    ]
    assert [(call["action"], call["kind"]) for call in audit["unregistered"]] == [
        ("ghost", "action"),
        ("ghost_anime", "action"),
        ("get_anime_info", "action"),
        ("ghost_task_session", "action"),
        ("ghost_keyword", "action"),
        ("get_detail", "public_action"),
        ("ghost_public", "public_action"),
    ]


def test_static_audit_reports_unparseable_relative_path(tmp_path):
    from tests.capabilities.contracts.catalog import invocation_audit

    source = tmp_path / "app"
    source.mkdir()
    (source / "broken.py").write_text("def broken(", encoding="utf-8")

    with pytest.raises(ValueError, match="app/broken.py"):
        invocation_audit(source, display_root=tmp_path)


def test_production_static_audit_covers_known_direct_calls():
    from app.capabilities.factory import build_capability_registry
    from tests.capabilities.contracts.catalog import invocation_audit

    audit = invocation_audit(registry=build_capability_registry())

    files = {call["file"] for call in audit["calls"]}
    actions = {call["action"] for call in audit["calls"]}
    assert {
        "app/agents/tools/anime.py",
        "app/agents/tools/profile.py",
        "app/agents/tools/search.py",
        "app/agents/recommendation_agent.py",
    } <= files
    assert {
        "get_detail",
        "get_reviews",
        "get_staff",
        "get_cast",
        "generate_profile",
        "search",
    } <= actions
    assert audit["unregistered"] == []


def test_production_inventory_covers_the_full_registry():
    from app.capabilities.factory import build_capability_registry
    from tests.capabilities.contracts.catalog import census, inventory

    registry = build_capability_registry()
    actions = census(registry)
    rows = inventory(actions, registry)

    assert len(rows) == len(actions)
    assert {(row["public_name"], row["version"]) for row in rows} == set(actions)
    assert sum(row["side_effect"] for row in rows) == sum(
        descriptor.is_side_effect for descriptor in actions.values()
    )
    assert {row["owner"] for row in rows} == set(registry.list_names())


def test_ci_workflow_runs_the_full_summary_gate():
    workflow = yaml.safe_load(
        (BACKEND_ROOT.parent / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    )
    cases = {
        "software": (
            "Run backend tests",
            ".runtime/capability-contracts/software-full.json",
            ".runtime/junit/software.xml",
            "backend-software-junit",
        ),
        "harness": (
            "Run deterministic Harness regression",
            ".runtime/capability-contracts/coverage.json",
            ".runtime/junit/harness.xml",
            "ci-harness-entrypoint-evidence",
        ),
    }
    for job_name, (pytest_name, report, junit, upload_name) in cases.items():
        steps = workflow["jobs"][job_name]["steps"]
        by_name = {step.get("name"): step for step in steps}
        pytest_run = by_name[pytest_name]["run"]
        assert "-p tests.capabilities.contracts.plugin" in pytest_run
        assert "--capability-contract-gate" in pytest_run
        assert f"--capability-contract-report={report}" in pytest_run
        assert f"--junitxml={junit}" in pytest_run
        summary = by_name["Summarize Capability CI gate"]
        assert summary["if"] == "always()"
        summary_run = summary["run"]
        assert f"--report {report}" in summary_run
        assert f"--junit {junit}" in summary_run
        assert "--output .runtime/capability-ci/" in summary_run
        assert "GITHUB_STEP_SUMMARY" in summary_run
        upload = next(
            step for step in steps if step.get("with", {}).get("name") == upload_name
        )
        assert "backend/.runtime/capability-ci/" in upload["with"]["path"]
