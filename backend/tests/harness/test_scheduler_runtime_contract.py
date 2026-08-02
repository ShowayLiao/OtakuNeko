from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from app.harness.contracts import ErrorCode, RunResult
from app.harness.scheduler.execution import handle_task_def
from app.harness.state import AgentState


@pytest.mark.asyncio
async def test_scheduler_maps_runtime_terminal_result_instead_of_assuming_success() -> None:
    task_def = SimpleNamespace(
        id=1,
        user_id=7,
        task_type="weekly_recommendation",
        payload="{}",
        policy="{}",
        enabled=True,
    )
    run = SimpleNamespace(
        id=2,
        lease_id="lease-1",
        scheduled_slot=datetime.now(timezone.utc),
        trace_id=None,
        status="running",
    )

    class Runtime:
        async def execute(self, task):
            return AgentState(
                task=task,
                status="failed",
                terminal_result=RunResult(
                    run_id="2",
                    status="failed",
                    error_code=ErrorCode.TRANSIENT,
                ),
            )

    class Repository:
        def __init__(self):
            self.finished = []

        async def finish(self, run, **kwargs):
            self.finished.append(kwargs)
            return True

    repository = Repository()
    state = await handle_task_def(task_def, run, Runtime(), None, repository=repository)

    assert state.status == "failed"
    assert run.status == "failed"
    assert repository.finished == [
        {"success": False, "error_category": "transient", "lease_id": "lease-1"}
    ]


@pytest.mark.asyncio
async def test_scheduler_rejects_unknown_task_type_before_runtime_execution() -> None:
    task_def = SimpleNamespace(
        id=3,
        user_id=7,
        task_type="not_registered",
        payload="{}",
        policy="{}",
        enabled=True,
    )
    run = SimpleNamespace(
        id=4,
        lease_id="lease-unknown",
        scheduled_slot=datetime.now(timezone.utc),
        trace_id=None,
        status="running",
    )

    class Runtime:
        def __init__(self) -> None:
            self.calls = 0

        async def execute(self, task):
            self.calls += 1
            raise AssertionError("unknown scheduled task must not execute")

    class Repository:
        def __init__(self):
            self.finished = []

        async def finish(self, run, **kwargs):
            self.finished.append(kwargs)
            return True

    runtime = Runtime()
    repository = Repository()
    with pytest.raises(PermissionError, match="not registered"):
        await handle_task_def(
            task_def,
            run,
            runtime,
            None,
            repository=repository,
        )

    assert runtime.calls == 0
    assert run.status == "failed"
    assert run.error_category == "unsupported_task"
    assert repository.finished == [
        {
            "success": False,
            "error_category": "unsupported_task",
            "lease_id": "lease-unknown",
        }
    ]


@pytest.mark.asyncio
async def test_scheduler_fails_closed_without_dispatcher_backed_runtime() -> None:
    task_def = SimpleNamespace(
        id=5,
        user_id=7,
        task_type="weekly_recommendation",
        payload="{}",
        policy="{}",
        enabled=True,
    )
    run = SimpleNamespace(
        id=6,
        lease_id="lease-unavailable",
        scheduled_slot=datetime.now(timezone.utc),
        trace_id=None,
        status="running",
    )

    class Repository:
        def __init__(self):
            self.finished = []

        async def finish(self, run, **kwargs):
            self.finished.append(kwargs)
            return True

    repository = Repository()
    with pytest.raises(PermissionError, match="dispatcher-backed Runtime"):
        await handle_task_def(task_def, run, None, None, repository=repository)

    assert run.status == "failed"
    assert run.error_category == "scheduler_unavailable"
    assert repository.finished == [
        {
            "success": False,
            "error_category": "scheduler_unavailable",
            "lease_id": "lease-unavailable",
        }
    ]
