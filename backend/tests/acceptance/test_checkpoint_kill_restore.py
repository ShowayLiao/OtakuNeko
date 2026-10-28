"""Process-kill acceptance coverage for durable Runtime checkpoint recovery."""

from __future__ import annotations

import json
import os
import queue
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest


BACKEND = Path(__file__).resolve().parents[2]
WORKER = BACKEND / "tests" / "acceptance" / "fixtures" / "checkpoint_kill_worker.py"
_TERMINAL_EVENT_TYPES = {
    "run.succeeded",
    "run.failed",
    "run.cancelled",
    "run.abandoned",
}
_CANONICAL_TERMINAL_EVENT_TYPES = {
    "run.succeeded",
    "run.failed",
    "run.cancelled",
}


@pytest.mark.parametrize(
    ("boundary", "decision"),
    [
        pytest.param("before_dispatch", "approve", id="pre-dispatch"),
        pytest.param("confirmed", "approve", id="idempotency-confirmed"),
        pytest.param("unknown", "approve", id="sink-committed-result-unknown"),
        pytest.param("after_step", "continue", id="after-step-checkpoint"),
    ],
)
def test_subprocess_kill_recovery_preserves_one_synthetic_write(
    tmp_path: Path,
    record_property: Any,
    boundary: str,
    decision: str,
) -> None:
    app_db = tmp_path / "application.db"
    checkpoint_db = tmp_path / "checkpoints.db"
    sink_db = tmp_path / "synthetic-sink.db"
    thread_id = f"kill-thread-{boundary}"

    crash_worker, crash_lines, boundary_message = _wait_for_boundary(
        boundary=boundary,
        thread_id=thread_id,
        app_db=app_db,
        checkpoint_db=checkpoint_db,
        sink_db=sink_db,
    )
    try:
        crash_worker.kill()
        crash_worker.wait(timeout=10)
    finally:
        if crash_worker.poll() is None:
            crash_worker.kill()
            crash_worker.wait(timeout=10)
    record_property("crash_child_exit_code", crash_worker.returncode)
    record_property("crash_boundary", boundary)
    assert crash_worker.returncode not in (None, 0), (
        f"Crash worker did not exit from forced termination: {crash_lines}"
    )

    run_id = str(boundary_message["run_id"])
    assert run_id
    assert boundary_message["thread_id"] == thread_id
    if boundary == "confirmed":
        assert _sink_count(sink_db, run_id) == 1
    elif boundary in {"unknown", "after_step"}:
        assert _sink_count(sink_db, run_id) == 1
    else:
        assert _sink_count(sink_db, run_id) == 0

    lease_expiry = _wait_for_actual_lease_expiry(
        checkpoint_db,
        run_id=run_id,
        thread_id=f"user:7:thread:{thread_id}",
        timeout_seconds=20,
    )
    record_property("lease_expired_at", lease_expiry.isoformat())

    recovery_worker, recovery_lines, recovery = _run_recovery_worker(
        boundary=boundary,
        decision=decision,
        thread_id=thread_id,
        run_id=run_id,
        app_db=app_db,
        checkpoint_db=checkpoint_db,
        sink_db=sink_db,
    )
    record_property("recovery_child_exit_code", recovery_worker.returncode)
    record_property("recovery_event_types", ",".join(recovery["event_types"]))
    assert recovery_worker.returncode == 0, recovery_lines
    assert recovery["status_code"] == 200, recovery
    assert recovery["run_id"] == run_id
    if decision == "approve":
        assert recovery["probes"] == {
            "cross_owner": 404,
            "cross_thread": 404,
            "continue_pending_write": 409,
        }
    else:
        assert recovery["probes"] == {}

    events = recovery["events"]
    if boundary == "unknown":
        failure = next(event for event in events if event.get("type") == "run_failed")
        assert failure.get("termination_reason") == "attention_required", recovery
        assert _sink_count(sink_db, run_id) == 1
    else:
        assert any(event.get("type") == "run_completed" for event in events), recovery
        assert recovery["model_saw_tool_result"] is True, recovery
        assert _sink_count(sink_db, run_id) == 1

    assert recovery["replay_statuses"] == [200, 200]
    assert recovery["replay_sequences"] == recovery["replay_sequences_second"]
    assert recovery["terminal_resume_status"] == 409
    assert recovery["sink_count_after_replay"] == 1

    with sqlite3.connect(app_db) as connection:
        rows = connection.execute(
            "SELECT sequence, event_type FROM agent_run_event "
            "WHERE run_id = ? ORDER BY sequence",
            (run_id,),
        ).fetchall()
    sequences = [int(row[0]) for row in rows]
    event_types = [str(row[1]) for row in rows]
    assert sequences == sorted(sequences)
    assert len(sequences) == len(set(sequences))
    resume_sequences = recovery["event_sequences"]
    assert resume_sequences == sorted(resume_sequences)
    assert len(resume_sequences) == len(set(resume_sequences))
    assert set(resume_sequences).issubset(sequences)
    assert recovery["replay_sequences"] == sequences
    assert sum(event_type in _TERMINAL_EVENT_TYPES for event_type in event_types) == 1
    assert _sink_count(sink_db, run_id) == 1

    record_property("durable_event_count", len(rows))
    record_property("durable_terminal_count", 1)
    record_property("synthetic_sink_count", 1)
    record_property("model_saw_tool_result", recovery["model_saw_tool_result"])


@pytest.mark.parametrize(
    (
        "crash_boundary",
        "terminal_outcome",
        "expected_run_status",
        "expected_checkpoint_status",
        "expected_event_type",
        "expected_result_status",
        "expected_error_code",
        "expected_termination_reason",
        "expected_content",
        "two_stage",
    ),
    [
        pytest.param(
            "terminal_checkpoint",
            "completed",
            "succeeded",
            "completed",
            "run.succeeded",
            "completed",
            None,
            "respond",
            "The synthetic write completed.",
            False,
            id="completed-checkpoint-before-canonical-event",
        ),
        pytest.param(
            "terminal_checkpoint",
            "attention_required",
            "failed",
            "failed",
            "run.failed",
            "failed",
            "tool_error",
            "attention_required",
            None,
            True,
            id="attention-required-failure-checkpoint",
        ),
        pytest.param(
            "terminal_checkpoint",
            "cancelled",
            "cancelled",
            "cancelled",
            "run.cancelled",
            "cancelled",
            "cancelled",
            "cancelled",
            None,
            False,
            id="cancelled-checkpoint-before-canonical-event",
        ),
        pytest.param(
            "terminal_checkpoint",
            "timeout",
            "failed",
            "timeout",
            "run.failed",
            "timeout",
            "timeout",
            "timeout",
            None,
            False,
            id="timeout-checkpoint-before-canonical-event",
        ),
        pytest.param(
            "terminal_event_committed",
            "completed",
            "succeeded",
            "completed",
            "run.succeeded",
            "completed",
            None,
            "respond",
            "The synthetic write completed.",
            False,
            id="terminal-event-committed-before-run-transition",
        ),
    ],
)
def test_terminal_checkpoint_reconciles_after_process_kill(
    tmp_path: Path,
    record_property: Any,
    crash_boundary: str,
    terminal_outcome: str,
    expected_run_status: str,
    expected_checkpoint_status: str,
    expected_event_type: str,
    expected_result_status: str,
    expected_error_code: str | None,
    expected_termination_reason: str,
    expected_content: str | None,
    two_stage: bool,
) -> None:
    app_db = tmp_path / "application.db"
    checkpoint_db = tmp_path / "checkpoints.db"
    sink_db = tmp_path / "synthetic-sink.db"
    thread_id = f"terminal-thread-{terminal_outcome}-{crash_boundary}"

    if two_stage:
        # First commit the synthetic external effect, then kill the process
        # while its durable idempotency result is still unknown.
        crash_worker, crash_lines, boundary_message = _wait_for_boundary(
            boundary="unknown",
            thread_id=thread_id,
            app_db=app_db,
            checkpoint_db=checkpoint_db,
            sink_db=sink_db,
            terminal_outcome=terminal_outcome,
        )
        _kill_worker(crash_worker, crash_lines)
        run_id = str(boundary_message["run_id"])
        assert run_id
        assert boundary_message["thread_id"] == thread_id
        assert _sink_count(sink_db, run_id) == 1
        first_expiry = _wait_for_actual_lease_expiry(
            checkpoint_db,
            run_id=run_id,
            thread_id=f"user:7:thread:{thread_id}",
            timeout_seconds=20,
        )
        record_property("first_lease_expired_at", first_expiry.isoformat())

        terminal_worker, terminal_lines, terminal_message = _wait_for_boundary(
            boundary="terminal_checkpoint",
            mode="terminalize",
            thread_id=thread_id,
            run_id=run_id,
            app_db=app_db,
            checkpoint_db=checkpoint_db,
            sink_db=sink_db,
            terminal_outcome=terminal_outcome,
        )
        try:
            assert terminal_message["terminal_status"] == "failed", terminal_message
            assert terminal_message["terminal_result"]["termination_reason"] == (
                "attention_required"
            ), terminal_message
        finally:
            _kill_worker(terminal_worker, terminal_lines)
        assert _sink_count(sink_db, run_id) == 1
        terminal_expiry = _wait_for_actual_lease_expiry(
            checkpoint_db,
            run_id=run_id,
            thread_id=f"user:7:thread:{thread_id}",
            timeout_seconds=20,
        )
        record_property("terminal_lease_expired_at", terminal_expiry.isoformat())
    else:
        crash_worker, crash_lines, boundary_message = _wait_for_boundary(
            boundary=crash_boundary,
            thread_id=thread_id,
            app_db=app_db,
            checkpoint_db=checkpoint_db,
            sink_db=sink_db,
            terminal_outcome=terminal_outcome,
        )
        try:
            assert boundary_message["thread_id"] == thread_id
            if crash_boundary == "terminal_checkpoint":
                assert (
                    boundary_message["terminal_status"] == expected_checkpoint_status
                ), boundary_message
            else:
                assert boundary_message["terminal_event_type"] == expected_event_type, (
                    boundary_message
                )
        finally:
            _kill_worker(crash_worker, crash_lines)
        run_id = str(boundary_message["run_id"])
        assert run_id
        assert _sink_count(sink_db, run_id) == 1
        terminal_expiry = _wait_for_actual_lease_expiry(
            checkpoint_db,
            run_id=run_id,
            thread_id=f"user:7:thread:{thread_id}",
            timeout_seconds=20,
        )
        record_property("terminal_lease_expired_at", terminal_expiry.isoformat())

    recovery_worker, recovery_lines, recovery = _run_terminal_reconciliation_worker(
        thread_id=thread_id,
        run_id=run_id,
        app_db=app_db,
        checkpoint_db=checkpoint_db,
        sink_db=sink_db,
        terminal_outcome=terminal_outcome,
    )
    record_property("reconciliation_child_exit_code", recovery_worker.returncode)
    record_property("reconciled_run_status", recovery["runs"][0].get("status"))
    record_property("reconciled_event_type", expected_event_type)
    assert recovery_worker.returncode == 0, recovery_lines
    assert recovery["probes"] == {"cross_owner": 404, "cross_thread": 404}, recovery
    assert recovery["pre_reconcile_status"] == "running", recovery
    assert recovery["run_statuses"] == [200, 200], recovery
    assert recovery["event_statuses"] == [200, 200], recovery
    assert recovery["runs"][0] == recovery["runs"][1], recovery
    assert recovery["runs"][0]["status"] == expected_run_status, recovery
    assert recovery["event_projections"][0] == recovery["event_projections"][1], (
        recovery
    )
    assert recovery["terminal_resume_status"] == 409, recovery
    assert recovery["model_call_count"] == 0, recovery
    assert recovery["capability_call_count"] == 0, recovery
    assert recovery["sink_count"] == 1, recovery
    assert recovery["checkpoint_status"] == expected_checkpoint_status, recovery

    checkpoint_result = recovery["checkpoint_terminal_result"]
    assert checkpoint_result is not None, recovery
    assert checkpoint_result["run_id"] == run_id, recovery
    assert checkpoint_result["status"] == expected_result_status, recovery
    assert checkpoint_result.get("error_code") == expected_error_code, recovery
    assert checkpoint_result.get("termination_reason") == expected_termination_reason, (
        recovery
    )
    assert checkpoint_result.get("content") == expected_content, recovery

    projection_events = recovery["event_projections"][0]["events"]
    terminal_events = [
        event
        for event in projection_events
        if event["event_type"] in _CANONICAL_TERMINAL_EVENT_TYPES
    ]
    assert len(terminal_events) == 1, recovery
    terminal_event = terminal_events[0]
    assert terminal_event["event_type"] == expected_event_type, recovery
    expected_payload: dict[str, Any] = {
        "termination_reason": expected_termination_reason
    }
    if expected_content is not None:
        expected_payload["content"] = expected_content
    else:
        expected_payload["error_code"] = expected_error_code
    if expected_result_status == "timeout":
        expected_payload["status"] = "timeout"
    assert terminal_event["payload"] == expected_payload, recovery
    assert "run.abandoned" not in [
        event["event_type"] for event in projection_events
    ], recovery

    all_sequences = [int(event["sequence"]) for event in projection_events]
    all_event_ids = [str(event["event_id"]) for event in projection_events]
    assert all_sequences == sorted(all_sequences), recovery
    assert len(all_sequences) == len(set(all_sequences)), recovery
    assert len(all_event_ids) == len(set(all_event_ids)), recovery
    assert recovery["runs"][0]["last_sequence"] == max(all_sequences), recovery
    assert _sink_count(sink_db, run_id) == 1

    with sqlite3.connect(app_db) as connection:
        run_row = connection.execute(
            "SELECT status, error_code FROM agent_run WHERE run_id = ?",
            (run_id,),
        ).fetchone()
        durable_rows = connection.execute(
            "SELECT sequence, event_id, event_type, payload_json FROM agent_run_event "
            "WHERE run_id = ? ORDER BY sequence",
            (run_id,),
        ).fetchall()
    assert run_row is not None
    assert run_row[0] == expected_run_status
    assert run_row[1] == expected_error_code
    assert [int(row[0]) for row in durable_rows] == all_sequences
    assert [str(row[1]) for row in durable_rows] == all_event_ids
    assert (
        sum(str(row[2]) in _CANONICAL_TERMINAL_EVENT_TYPES for row in durable_rows) == 1
    )

    record_property("durable_event_count", len(durable_rows))
    record_property("durable_terminal_count", 1)
    record_property("synthetic_sink_count", 1)
    record_property("model_calls_during_reconciliation", 0)
    record_property("capability_calls_during_reconciliation", 0)


def _worker_environment() -> dict[str, str]:
    env = os.environ.copy()
    current_pythonpath = env.get("PYTHONPATH", "")
    env["PYTHONPATH"] = os.pathsep.join(
        value for value in (str(BACKEND), current_pythonpath) if value
    )
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def _start_worker(
    *,
    mode: str,
    boundary: str,
    decision: str,
    thread_id: str,
    run_id: str,
    app_db: Path,
    checkpoint_db: Path,
    sink_db: Path,
    terminal_outcome: str = "completed",
) -> tuple[subprocess.Popen[str], queue.Queue[str | None], list[str]]:
    command = [
        sys.executable,
        str(WORKER),
        "--mode",
        mode,
        "--boundary",
        boundary,
        "--decision",
        decision,
        "--thread-id",
        thread_id,
        "--run-id",
        run_id,
        "--app-db",
        str(app_db),
        "--checkpoint-db",
        str(checkpoint_db),
        "--sink-db",
        str(sink_db),
        "--terminal-outcome",
        terminal_outcome,
    ]
    process = subprocess.Popen(
        command,
        cwd=BACKEND,
        env=_worker_environment(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        bufsize=1,
    )
    lines: queue.Queue[str | None] = queue.Queue()
    captured: list[str] = []

    def read_output() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            normalized = line.rstrip("\r\n")
            captured.append(normalized)
            lines.put(normalized)
        lines.put(None)

    threading.Thread(target=read_output, daemon=True).start()
    return process, lines, captured


def _next_message(
    process: subprocess.Popen[str],
    lines: queue.Queue[str | None],
    captured: list[str],
    *,
    expected_kind: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise AssertionError(
                f"Timed out waiting for {expected_kind}; child output: {captured}"
            )
        try:
            line = lines.get(timeout=min(remaining, 0.25))
        except queue.Empty:
            if process.poll() is not None:
                raise AssertionError(
                    f"Child exited {process.returncode} before {expected_kind}; "
                    f"child output: {captured}"
                )
            continue
        if line is None:
            raise AssertionError(
                f"Child closed output before {expected_kind}; child output: {captured}"
            )
        try:
            message = json.loads(line)
        except json.JSONDecodeError:
            continue
        if message.get("kind") != expected_kind:
            raise AssertionError(
                f"Expected child message {expected_kind}, got {message}; "
                f"child output: {captured}"
            )
        return message


def _wait_for_boundary(
    *,
    boundary: str,
    thread_id: str,
    app_db: Path,
    checkpoint_db: Path,
    sink_db: Path,
    mode: str = "crash",
    run_id: str = "",
    decision: str = "approve",
    terminal_outcome: str = "completed",
) -> tuple[subprocess.Popen[str], list[str], dict[str, Any]]:
    process, lines, captured = _start_worker(
        mode=mode,
        boundary=boundary,
        decision=decision,
        thread_id=thread_id,
        run_id=run_id,
        app_db=app_db,
        checkpoint_db=checkpoint_db,
        sink_db=sink_db,
        terminal_outcome=terminal_outcome,
    )
    try:
        message = _next_message(
            process,
            lines,
            captured,
            expected_kind="boundary",
            timeout_seconds=45,
        )
    except Exception:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)
        raise
    return process, captured, message


def _kill_worker(process: subprocess.Popen[str], captured: list[str]) -> None:
    if process.poll() is None:
        process.kill()
    process.wait(timeout=10)
    assert process.returncode not in (None, 0), (
        f"Crash worker did not exit from forced termination: {captured}"
    )


def _wait_for_actual_lease_expiry(
    checkpoint_db: Path,
    *,
    run_id: str,
    thread_id: str,
    timeout_seconds: float,
) -> datetime:
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        with sqlite3.connect(checkpoint_db) as connection:
            row = connection.execute(
                "SELECT lease_expires_at FROM harness_checkpoint_leases "
                "WHERE run_id = ? AND thread_id = ?",
                (run_id, thread_id),
            ).fetchone()
        assert row is not None, "The killed resume worker left no durable lease"
        expiry = datetime.fromisoformat(str(row[0]))
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        remaining = (expiry - datetime.now(timezone.utc)).total_seconds()
        if remaining <= 0:
            return expiry
        time.sleep(min(remaining, 0.05))
    raise AssertionError("The recorded checkpoint lease did not expire in time")


def _run_recovery_worker(
    *,
    boundary: str,
    decision: str,
    thread_id: str,
    run_id: str,
    app_db: Path,
    checkpoint_db: Path,
    sink_db: Path,
) -> tuple[subprocess.Popen[str], list[str], dict[str, Any]]:
    process, lines, captured = _start_worker(
        mode="recover",
        boundary=boundary,
        decision=decision,
        thread_id=thread_id,
        run_id=run_id,
        app_db=app_db,
        checkpoint_db=checkpoint_db,
        sink_db=sink_db,
    )
    try:
        result = _next_message(
            process,
            lines,
            captured,
            expected_kind="recovery_result",
            timeout_seconds=45,
        )
        process.wait(timeout=10)
    except Exception:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)
        raise
    return process, captured, result


def _run_terminal_reconciliation_worker(
    *,
    thread_id: str,
    run_id: str,
    app_db: Path,
    checkpoint_db: Path,
    sink_db: Path,
    terminal_outcome: str,
) -> tuple[subprocess.Popen[str], list[str], dict[str, Any]]:
    process, lines, captured = _start_worker(
        mode="reconcile",
        boundary="",
        decision="approve",
        thread_id=thread_id,
        run_id=run_id,
        app_db=app_db,
        checkpoint_db=checkpoint_db,
        sink_db=sink_db,
        terminal_outcome=terminal_outcome,
    )
    try:
        result = _next_message(
            process,
            lines,
            captured,
            expected_kind="terminal_reconcile_result",
            timeout_seconds=45,
        )
        process.wait(timeout=10)
    except Exception:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)
        raise
    return process, captured, result


def _sink_count(sink_db: Path, run_id: str) -> int:
    with sqlite3.connect(sink_db) as connection:
        row = connection.execute(
            "SELECT COUNT(*) FROM synthetic_writes WHERE run_id = ?",
            (run_id,),
        ).fetchone()
    return int(row[0])
