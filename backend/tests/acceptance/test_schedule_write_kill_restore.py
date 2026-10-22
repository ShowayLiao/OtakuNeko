"""Real registered Schedule actions across forced process termination."""

from __future__ import annotations

import json
from pathlib import Path
import queue
import sqlite3
import subprocess
import sys
import threading

import pytest

from tests.acceptance.test_checkpoint_kill_restore import (
    _next_message,
    _wait_for_actual_lease_expiry,
    _worker_environment,
)

BACKEND = Path(__file__).resolve().parents[2]
WORKER = BACKEND / "tests/acceptance/fixtures/schedule_write_kill_worker.py"
ACTIONS = (
    "create_schedule",
    "update_schedule",
    "delete_schedule",
    "upsert_schedule",
    "bulk_upsert_schedules",
    "sync_bangumi_schedule",
)


def start(tmp_path, action, boundary, mode, run_id=""):
    command = [
        sys.executable,
        str(WORKER),
        "--mode",
        mode,
        "--action",
        action,
        "--boundary",
        boundary,
        "--app-db",
        str(tmp_path / "app.db"),
        "--checkpoint-db",
        str(tmp_path / "checkpoint.db"),
        "--audit-db",
        str(tmp_path / "audit.db"),
        "--thread-id",
        "schedule-kill-thread",
        "--run-id",
        run_id,
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
    captured = []

    def reader():
        assert process.stdout is not None
        for line in process.stdout:
            line = line.rstrip("\r\n")
            captured.append(line)
            lines.put(line)
        lines.put(None)

    threading.Thread(target=reader, daemon=True).start()
    return process, lines, captured


def business_snapshot(path):
    with sqlite3.connect(path) as db:
        return {
            table: sorted(db.execute(f"SELECT * FROM {table}").fetchall(), key=repr)
            for table in (
                "schedules",
                "subject",
                "collection",
                "anime_broadcast_metadata",
            )
        }


def audit_snapshot(path):
    with sqlite3.connect(path) as db:
        return db.execute("SELECT kind, action FROM audit ORDER BY rowid").fetchall()


@pytest.mark.parametrize("action", ACTIONS)
@pytest.mark.parametrize("boundary", ("confirmed", "unknown"))
def test_schedule_write_survives_process_kill(
    tmp_path, action, boundary, record_property
):
    process, lines, captured = start(tmp_path, action, boundary, "crash")
    try:
        reached = _next_message(
            process, lines, captured, expected_kind="boundary", timeout_seconds=50
        )
        assert reached["action"] == action and reached["boundary"] == boundary
        assert reached["service_calls"] == 1
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)
    assert process.returncode not in (None, 0)
    before = business_snapshot(tmp_path / "app.db")
    audit_before = audit_snapshot(tmp_path / "audit.db")
    assert audit_before.count(("service", action)) == 1
    # Prove the real action committed, rather than merely pausing before SQL.
    with sqlite3.connect(tmp_path / "app.db") as db:
        if action == "delete_schedule":
            assert (
                db.execute("SELECT count(*) FROM schedules WHERE id=71").fetchone()[0]
                == 0
            )
        elif action == "update_schedule":
            assert (
                db.execute("SELECT day_of_week FROM schedules WHERE id=71").fetchone()[
                    0
                ]
                == 4
            )
        elif action == "sync_bangumi_schedule":
            assert (
                db.execute(
                    "SELECT count(*) FROM subject WHERE source_id='799'"
                ).fetchone()[0]
                == 1
            )
            assert (
                db.execute(
                    "SELECT count(*) FROM anime_broadcast_metadata WHERE bangumi_id=799"
                ).fetchone()[0]
                == 1
            )
            assert audit_before.count(("external", action)) == 2
        else:
            assert (
                db.execute(
                    "SELECT count(*) FROM schedules WHERE user_id=7 AND source_id='702'"
                ).fetchone()[0]
                == 1
            )
        idem_events = db.execute(
            "SELECT count(*) FROM agent_run_event WHERE event_type='idempotency.result'"
        ).fetchone()[0]
        assert idem_events == (1 if boundary == "confirmed" else 0)
    _wait_for_actual_lease_expiry(
        tmp_path / "checkpoint.db",
        run_id=reached["run_id"],
        thread_id="user:7:thread:schedule-kill-thread",
        timeout_seconds=10,
    )
    recovery, replay_lines, replay_captured = start(
        tmp_path, action, boundary, "recover", reached["run_id"]
    )
    try:
        result = _next_message(
            recovery,
            replay_lines,
            replay_captured,
            expected_kind="recovery_result",
            timeout_seconds=50,
        )
        recovery.wait(timeout=10)
    finally:
        if recovery.poll() is None:
            recovery.kill()
            recovery.wait(timeout=10)
    evidence = (
        BACKEND.parent
        / "docs/harness-execution/A-L3-08/process-runs"
        / tmp_path.parent.name
    )
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / f"{boundary}-{action}.json").write_text(
        json.dumps(
            {
                "crash_output": captured,
                "recovery_output": replay_captured,
                "crash_exit_code": process.returncode,
                "recovery_exit_code": recovery.returncode,
                "result": result,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    assert recovery.returncode == 0, replay_captured
    assert (
        result["status_code"] == result["run_status"] == result["events_status"] == 200
    )
    assert result["foreign_resume_status"] == result["foreign_trace_status"] == 404
    assert result["trace_status"] == 200
    assert result["repeat_status"] == 409
    assert result["service_calls"] == result["external_calls"] == 0
    assert business_snapshot(tmp_path / "app.db") == before
    assert audit_snapshot(tmp_path / "audit.db") == audit_before
    status = "succeeded" if boundary == "confirmed" else "failed"
    assert result["run"]["status"] == status, result
    assert result["checkpoint_status"] == (
        "completed" if boundary == "confirmed" else "failed"
    )
    trace = result["trace"]
    assert trace["trace_id"] == trace["run_id"] == reached["run_id"]
    assert trace["user_id"] == 7 and trace["completed_at"] is not None
    assert trace["status"] == ("completed" if boundary == "confirmed" else "failed")
    trace_events = [event for step in trace["steps"] for event in step["events"]]
    assert trace_events and all(
        event["run_id"] == reached["run_id"] for event in trace_events
    )
    assert len({event["event_id"] for event in trace_events}) == len(trace_events)
    assert len({event["sequence"] for event in trace_events}) == len(trace_events)
    terminal_trace_type = "agent_result" if boundary == "confirmed" else "failure"
    assert any(event["event_type"] == terminal_trace_type for event in trace_events)
    ends = [event for event in trace_events if event["event_type"] == "tool_call_end"]
    assert ends and all(event["status"] != "running" for event in ends)
    for start_event in (
        event for event in trace_events if event["event_type"] == "tool_call_start"
    ):
        assert any(
            event["invocation_id"] == start_event["invocation_id"]
            and event["sequence"] > start_event["sequence"]
            for event in ends
        )
    if boundary == "unknown":
        assert "attention_required" in json.dumps(result)
    events = result["events"]["events"]
    terminal = [
        e
        for e in events
        if e["event_type"]
        in {"run.succeeded", "run.failed", "run.cancelled", "run.abandoned"}
    ]
    assert len(terminal) == 1 and terminal[0]["event_type"] == "run." + status
    assert [e["sequence"] for e in events] == sorted({e["sequence"] for e in events})
    assert len({e["event_id"] for e in events}) == len(events)
    with sqlite3.connect(tmp_path / "app.db") as db:
        invocations = db.execute(
            "SELECT status, error_code FROM agent_invocation WHERE run_id=?",
            (reached["run_id"],),
        ).fetchall()
        assert len(invocations) == 1 and invocations[0][0] == status, invocations
    record_property("action", action)
    record_property("boundary", boundary)
    record_property("crash_exit_code", process.returncode)
    record_property("recovery_exit_code", recovery.returncode)
    record_property("service_calls_before_kill", 1)
    record_property("service_calls_after_restore", 0)
    record_property("business_snapshot_equal_after_restore", True)
