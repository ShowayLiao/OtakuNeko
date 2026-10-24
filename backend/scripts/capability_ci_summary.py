"""Summarize the full capability Registry, test mapping, failures, and coverage.

The pytest capability-contract plugin produces the authoritative report. This
script turns that report plus the JUnit evidence into one CI summary and exits
non-zero when required tests, unregistered calls, contract failures, test
failures, or report-integrity checks fail closed.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
from typing import Any

SCHEMA_VERSION = 1
REPORT_VERSION = "v2"
MISSING_PREFIXES = (
    "Missing executed contracts:",
    "Missing action fixtures:",
    "Expected contract coverage is empty",
)
UNREGISTERED_PREFIXES = (
    "Unexpected contracts:",
    "Stale action fixtures:",
    "Unregistered capability calls:",
)
CHECK_TITLES = (
    ("missing_tests", "Missing tests"),
    ("unregistered_calls", "Unregistered calls"),
    ("contract_failures", "Contract failures"),
    ("test_failures", "Test failures"),
    ("integrity_errors", "Report integrity"),
)


def load_report(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Capability gate report must be a JSON object")
    return data


def load_junit(path: Path) -> dict[str, Any]:
    root = ET.parse(path).getroot()
    failed_cases = []
    failures = errors = skipped = 0
    cases = list(root.iter("testcase"))
    for case in cases:
        if case.find("failure") is not None:
            status = "failure"
            failures += 1
        elif case.find("error") is not None:
            status = "error"
            errors += 1
        elif case.find("skipped") is not None:
            skipped += 1
            continue
        else:
            continue
        failed_cases.append(
            {
                "kind": "test_failure",
                "case": f"{case.get('classname', '')}::{case.get('name', '')}",
                "status": status,
            }
        )
    return {
        "tests": len(cases),
        "failures": failures,
        "errors": errors,
        "skipped": skipped,
        "passed": len(cases) - failures - errors - skipped,
        "failed_cases": failed_cases,
    }


def _append_unique(items: list[Any], item: dict[str, Any]) -> None:
    if item not in items:
        items.append(item)


def _dedupe_contract_failures(items: list[Any]) -> list[Any]:
    seen: dict[tuple[Any, Any, Any, Any], int] = {}
    result: list[Any] = []
    for item in items:
        if isinstance(item, dict) and item.get("nodeid"):
            key = (
                item.get("action"),
                item.get("version"),
                item.get("scenario"),
                item.get("nodeid"),
            )
            if key in seen:
                existing = result[seen[key]]
                if isinstance(existing, dict):
                    result[seen[key]] = {**existing, **item}
                continue
            seen[key] = len(result)
        result.append(item)
    return result


def _check_inventory(
    report: dict[str, Any], integrity: list[Any]
) -> tuple[list[dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
    inventory = report.get("inventory")
    if not isinstance(inventory, list) or not inventory:
        integrity.append("Registry inventory is missing or empty")
        return [], {}
    indexed: dict[tuple[str, str], dict[str, Any]] = {}
    valid_rows: list[dict[str, Any]] = []
    for row in inventory:
        if not isinstance(row, dict):
            integrity.append("Registry inventory contains a non-object row")
            continue
        public_name = row.get("public_name")
        version = row.get("version")
        if not isinstance(public_name, str) or not isinstance(version, str):
            integrity.append("Registry inventory row lacks a public name or version")
            continue
        if not isinstance(row.get("owner"), str):
            integrity.append(f"Registry inventory row lacks an owner: {public_name}")
        key = (public_name, version)
        if key in indexed:
            integrity.append(f"Registry inventory has a duplicate action: {key}")
            continue
        indexed[key] = row
        valid_rows.append(row)
    declared = report.get("actions")
    if declared != len(indexed):
        integrity.append(
            f"Registry action count differs: report={declared} inventory={len(indexed)}"
        )
    return valid_rows, indexed


def _check_mapping(
    report: dict[str, Any],
    inventory: dict[tuple[str, str], dict[str, Any]],
    checks: dict[str, list[Any]],
    integrity: list[Any],
) -> list[dict[str, Any]]:
    mapping = report.get("test_mapping")
    if not isinstance(mapping, list):
        integrity.append("Contract test mapping is missing")
        return []
    seen_nodeids: set[str] = set()
    valid_rows: list[dict[str, Any]] = []
    for row in mapping:
        if not isinstance(row, dict):
            integrity.append("Contract test mapping contains a non-object row")
            continue
        action = row.get("action")
        version = row.get("version")
        scenario = row.get("scenario")
        nodeid = row.get("nodeid")
        if not (
            isinstance(action, str)
            and isinstance(version, str)
            and isinstance(scenario, str)
        ):
            integrity.append(
                "Contract test mapping row lacks an action, version, or scenario"
            )
            continue
        if not isinstance(nodeid, str):
            integrity.append(
                f"Contract test mapping row lacks a nodeid: {action}@{version}/{scenario}"
            )
            continue
        if nodeid in seen_nodeids:
            integrity.append(f"Contract test mapping has a duplicate nodeid: {nodeid}")
        seen_nodeids.add(nodeid)
        valid_rows.append(row)
        key = (action, version)
        if key not in inventory:
            _append_unique(
                checks["unregistered_calls"],
                {
                    "kind": "unexpected_contract",
                    "action": action,
                    "version": version,
                    "scenario": scenario,
                    "nodeid": nodeid,
                },
            )
        status = row.get("status")
        if status != "passed":
            failure = {
                "kind": "contract_failure",
                "action": action,
                "version": version,
                "scenario": scenario,
                "nodeid": nodeid,
                "status": status,
                "failures": list(row.get("failures", [])),
            }
            _append_unique(checks["contract_failures"], failure)
    return valid_rows


def _classify_report_errors(
    report: dict[str, Any], checks: dict[str, list[Any]]
) -> None:
    errors = report.get("errors")
    if not isinstance(errors, list):
        checks["integrity_errors"].append("Gate report errors are missing")
        return
    for error in errors:
        if not isinstance(error, str):
            checks["integrity_errors"].append("Gate report contains a non-string error")
            continue
        if error.startswith(MISSING_PREFIXES):
            if error.startswith("Missing action fixtures:"):
                checks["missing_tests"].append(
                    {"kind": "missing_fixture", "reason": error}
                )
            elif error.startswith("Expected contract coverage is empty"):
                checks["missing_tests"].append(
                    {"kind": "missing_coverage", "reason": error}
                )
            elif not report.get("missing") and not checks["missing_tests"]:
                checks["missing_tests"].append({"kind": "gate_error", "reason": error})
            continue
        if error.startswith(UNREGISTERED_PREFIXES):
            if error.startswith("Stale action fixtures:"):
                checks["unregistered_calls"].append(
                    {"kind": "gate_error", "reason": error}
                )
                continue
            audit = report.get("invocation_audit")
            audit_unregistered = (
                audit.get("unregistered") if isinstance(audit, dict) else None
            )
            if (
                not checks["unregistered_calls"]
                and not report.get("unregistered_calls")
                and not audit_unregistered
            ):
                checks["unregistered_calls"].append(
                    {"kind": "gate_error", "reason": error}
                )
            continue
        checks["contract_failures"].append({"kind": "gate_error", "reason": error})


def _collect_failures(report: dict[str, Any], checks: dict[str, list[Any]]) -> None:
    reasons = report.get("failure_reasons")
    if not isinstance(reasons, list):
        checks["integrity_errors"].append("Contract failure reasons are missing")
        return
    for reason in reasons:
        if not isinstance(reason, dict):
            checks["integrity_errors"].append(
                "Contract failure reasons contain a non-object row"
            )
            continue
        _append_unique(
            checks["contract_failures"],
            {"kind": "contract_failure", **reason},
        )


def _collect_unregistered_calls(
    report: dict[str, Any], checks: dict[str, list[Any]]
) -> None:
    calls = report.get("unregistered_calls")
    if not isinstance(calls, list):
        checks["integrity_errors"].append("Unregistered-call evidence is missing")
        calls = []
    for call in calls:
        if not isinstance(call, dict):
            checks["integrity_errors"].append(
                "Unregistered-call evidence contains a non-object row"
            )
            continue
        _append_unique(
            checks["unregistered_calls"], {**call, "kind": "unregistered_call"}
        )
    audit = report.get("invocation_audit")
    if not isinstance(audit, dict):
        checks["integrity_errors"].append("Static invocation audit evidence is missing")
        return
    scanned = audit.get("scanned_files")
    if not isinstance(scanned, int) or scanned <= 0:
        checks["integrity_errors"].append(
            "Static invocation audit scanned no source files"
        )
    if not isinstance(audit.get("calls"), list):
        checks["integrity_errors"].append("Static invocation audit lacks call evidence")
    if not isinstance(audit.get("unregistered"), list):
        checks["integrity_errors"].append(
            "Static invocation audit lacks unregistered results"
        )
        return
    for call in audit["unregistered"]:
        if isinstance(call, dict):
            _append_unique(
                checks["unregistered_calls"],
                {**call, "kind": "unregistered_call"},
            )


def _missing_and_coverage(
    report: dict[str, Any],
    inventory: dict[tuple[str, str], dict[str, Any]],
    mapping: list[dict[str, Any]],
    checks: dict[str, list[Any]],
    integrity: list[Any],
) -> tuple[int, int]:
    expected = report.get("expected")
    passed = report.get("passed")
    missing = report.get("missing")
    if not isinstance(expected, int) or not isinstance(passed, int):
        integrity.append("Coverage counts are missing")
        return 0, 0
    if not isinstance(missing, list):
        integrity.append("Missing-contract list is missing")
        missing = []
    for row in missing:
        if not isinstance(row, list) or len(row) != 3:
            integrity.append(
                "Missing-contract row must contain name, version, scenario"
            )
            continue
        _append_unique(
            checks["missing_tests"],
            {
                "kind": "missing_observation",
                "action": row[0],
                "version": row[1],
                "scenario": row[2],
            },
        )
    if expected != passed + len(missing):
        integrity.append(
            f"Coverage counts are inconsistent: expected={expected} passed={passed} missing={len(missing)}"
        )
    represented: set[tuple[str, str]] = set()
    for row in mapping:
        action, version = row.get("action"), row.get("version")
        if isinstance(action, str) and isinstance(version, str):
            represented.add((action, version))
    for row in missing:
        if isinstance(row, list) and len(row) == 3:
            action, version = row[0], row[1]
            if isinstance(action, str) and isinstance(version, str):
                represented.add((action, version))
    for key in sorted(set(inventory) - represented):
        checks["missing_tests"].append(
            {"kind": "unmapped_action", "action": key[0], "version": key[1]}
        )
    return expected, passed


def summarize(
    report: dict[str, Any],
    junit: dict[str, Any] | None,
    *,
    report_error: str | None = None,
    junit_error: str | None = None,
) -> dict[str, Any]:
    checks: dict[str, list[Any]] = {
        "missing_tests": [],
        "unregistered_calls": [],
        "contract_failures": [],
        "test_failures": [],
        "integrity_errors": [],
    }
    integrity = checks["integrity_errors"]
    if report_error is not None:
        integrity.append(report_error)
        report = {}
    if junit_error is not None:
        integrity.append(junit_error)
        junit = None
    if report.get("version") != REPORT_VERSION:
        integrity.append(
            f"Unsupported capability gate report version: {report.get('version')!r}"
        )
    inventory_rows, inventory = _check_inventory(report, integrity)
    mapping = _check_mapping(report, inventory, checks, integrity)
    _classify_report_errors(report, checks)
    _collect_failures(report, checks)
    _collect_unregistered_calls(report, checks)
    expected, passed = _missing_and_coverage(
        report, inventory, mapping, checks, integrity
    )
    if junit is None:
        integrity.append("JUnit report is missing or invalid")
    else:
        checks["test_failures"].extend(junit.get("failed_cases", []))
        test_count = junit.get("tests", 0)
        junit_passed = junit.get("passed", 0)
        if not isinstance(test_count, int) or test_count <= 0:
            integrity.append("JUnit report contains no test cases")
        elif expected and test_count < expected:
            integrity.append(
                "JUnit test count is smaller than contract observations: "
                f"{test_count} < {expected}"
            )
        if isinstance(junit_passed, int) and passed and junit_passed < passed:
            integrity.append(
                "JUnit passed count is smaller than contract observations: "
                f"{junit_passed} < {passed}"
            )
    checks["contract_failures"] = _dedupe_contract_failures(checks["contract_failures"])
    if report and report.get("gate") != "pass" and not any(checks.values()):
        integrity.append(
            "Capability contract gate did not pass without structured evidence"
        )
    blocking = any(checks.values())
    gate = (
        "pass"
        if report.get("gate") == "pass" and junit is not None and not blocking
        else "fail"
    )
    exit_code = 2 if (report_error or junit_error) else (0 if gate == "pass" else 1)
    side_effects = sum(bool(row.get("side_effect")) for row in inventory_rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "gate": gate,
        "exit_code": exit_code,
        "report_version": report.get("version"),
        "registry": {
            "actions": len(inventory_rows),
            "owners": len(
                {
                    row.get("owner")
                    for row in inventory_rows
                    if isinstance(row.get("owner"), str)
                }
            ),
            "side_effect_actions": side_effects,
            "read_actions": len(inventory_rows) - side_effects,
        },
        "coverage": {
            "expected": expected,
            "passed": passed,
            "missing": len(report.get("missing", []))
            if isinstance(report.get("missing"), list)
            else 0,
            "ratio": round(passed / expected, 6) if expected else 0.0,
        },
        "tests": junit or {},
        "checks": checks,
        "inventory": inventory_rows,
        "test_mapping": mapping,
        "failure_reasons": report.get("failure_reasons", [])
        if isinstance(report.get("failure_reasons"), list)
        else [],
        "invocation_audit": report.get("invocation_audit", {}),
    }


def _format_check(item: dict[str, Any]) -> str:
    if isinstance(item, str):
        return item
    kind = item.get("kind")
    if kind in {"missing_observation", "unmapped_action", "unexpected_contract"}:
        label = f"{item.get('action')}@{item.get('version')}"
        if item.get("scenario") is not None:
            label += f"/{item['scenario']}"
        if item.get("nodeid"):
            label += f" at {item['nodeid']}"
        return label
    if kind == "unregistered_call":
        return (
            f"{item.get('file', '?')}:{item.get('line', '?')} "
            f"action={item.get('action', '?')}"
        )
    if kind == "contract_failure":
        label = (
            f"{item.get('action')}@{item.get('version')}/{item.get('scenario')} "
            f"at {item.get('nodeid')}"
        )
        failures = item.get("failures") or []
        details = ", ".join(
            f"{failure.get('stage')}: {failure.get('exception_type') or failure.get('outcome')}"
            for failure in failures
            if isinstance(failure, dict)
        )
        return f"{label} ({details})" if details else label
    if kind == "test_failure":
        return f"{item.get('case')} ({item.get('status')})"
    if kind in {"missing_fixture", "missing_coverage", "gate_error", "gate_status"}:
        return str(item.get("reason", kind))
    return json.dumps(item, ensure_ascii=False, sort_keys=True)


def render_markdown(summary: dict[str, Any]) -> str:
    registry = summary.get("registry", {})
    coverage = summary.get("coverage", {})
    tests = summary.get("tests") or {}
    lines = [
        f"# Capability CI summary gate: {str(summary.get('gate', 'fail')).upper()}",
        "",
        f"- Registry actions: {registry.get('actions', 0)} "
        f"({registry.get('read_actions', 0)} read, "
        f"{registry.get('side_effect_actions', 0)} side effect) across "
        f"{registry.get('owners', 0)} owners",
        f"- Contract coverage: {coverage.get('passed', 0)}/{coverage.get('expected', 0)} "
        f"observations executed, {coverage.get('missing', 0)} missing",
    ]
    if tests:
        lines.append(
            f"- Tests: {tests.get('passed', 0)} passed, {tests.get('failures', 0)} failed, "
            f"{tests.get('errors', 0)} errors, {tests.get('skipped', 0)} skipped"
        )
    else:
        lines.append("- Tests: JUnit evidence unavailable")
    mapping_counts: dict[tuple[str, str], int] = {}
    for row in summary.get("test_mapping", []):
        key = (row.get("action"), row.get("version"))
        mapping_counts[key] = mapping_counts.get(key, 0) + 1
    for check_name, title in CHECK_TITLES:
        items = summary.get("checks", {}).get(check_name, [])
        lines.extend(["", f"## {title} ({len(items)})", ""])
        if not items:
            lines.append("- none")
            continue
        remain = items[:50]
        lines.extend(f"- {_format_check(item)}" for item in remain)
        if len(items) > len(remain):
            lines.append(f"- ... {len(items) - len(remain)} more (see JSON report)")
    audit = summary.get("invocation_audit", {})
    calls = audit.get("calls", []) if isinstance(audit, dict) else []
    lines.extend(
        [
            "",
            "## Direct literal capability calls",
            "",
            f"- Scanned files: {audit.get('scanned_files', 0) if isinstance(audit, dict) else 0}; "
            f"literal calls: {len(calls)}; unregistered: "
            f"{len(audit.get('unregistered', [])) if isinstance(audit, dict) else 0}",
        ]
    )
    for call in calls:
        if not isinstance(call, dict):
            continue
        lines.append(
            f"- {call.get('file')}:{call.get('line')} "
            f"{call.get('action')} ({'registered' if call.get('registered') else 'UNREGISTERED'})"
        )
    lines.extend(
        [
            "",
            "## Registry inventory",
            "",
            "| Action | Version | Owner | Side effect | Mapped tests |",
            "| --- | --- | --- | --- | --- |",
        ]
    )
    for row in summary.get("inventory", []):
        key = (row.get("public_name"), row.get("version"))
        lines.append(
            f"| `{row.get('public_name')}` | {row.get('version')} | "
            f"{row.get('owner')} | {'yes' if row.get('side_effect') else 'no'} | "
            f"{mapping_counts.get(key, 0)} |"
        )
    lines.append("")
    return "\n".join(lines)


def write_outputs(
    summary: dict[str, Any],
    output: Path,
    *,
    markdown: Path | None = None,
    step_summary: str | None = None,
) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    rendered = render_markdown(summary) + "\n"
    if markdown is not None:
        markdown.parent.mkdir(parents=True, exist_ok=True)
        markdown.write_text(rendered, encoding="utf-8")
    if step_summary:
        path = Path(step_summary)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as stream:
            stream.write(rendered)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", required=True, help="Capability gate JSON report")
    parser.add_argument("--junit", required=True, help="Pytest JUnit XML report")
    parser.add_argument("--output", required=True, help="JSON summary output path")
    parser.add_argument("--markdown", default=None, help="Optional Markdown summary")
    parser.add_argument(
        "--step-summary",
        default=None,
        help="Optional GitHub step summary path; empty values are ignored",
    )
    args = parser.parse_args(argv)

    report: dict[str, Any] = {}
    junit: dict[str, Any] | None = None
    report_error = None
    junit_error = None
    try:
        report = load_report(Path(args.report))
    except (OSError, ValueError, UnicodeError) as exc:
        report_error = f"Gate report is missing or invalid: {type(exc).__name__}"
    try:
        junit = load_junit(Path(args.junit))
    except (OSError, ValueError, UnicodeError, ET.ParseError) as exc:
        junit_error = f"JUnit report is missing or invalid: {type(exc).__name__}"
    summary = summarize(
        report, junit, report_error=report_error, junit_error=junit_error
    )
    write_outputs(
        summary,
        Path(args.output),
        markdown=Path(args.markdown) if args.markdown else None,
        step_summary=args.step_summary,
    )
    print(
        render_markdown(summary),
        file=sys.stderr if summary["exit_code"] else sys.stdout,
    )
    return int(summary["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
