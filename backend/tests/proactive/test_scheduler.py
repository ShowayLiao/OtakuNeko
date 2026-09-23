"""Tests for PROACTIVE-001: task models, scheduler, and execution."""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone

import pytest

from app.models.agent_task import AgentTaskDef, AgentTaskRun
from app.harness.scheduler import Scheduler
from app.harness.scheduler.repository import InMemoryTaskRepository
from app.harness.scheduler.time import next_slot
from app.harness.scheduler.execution import handle_task_def, build_agent_task
from app.harness.policy import ProactivePolicy
from app.harness.task import AgentTask


class TestTaskModels:
    def test_create_task_def(self, db_session):
        task = AgentTaskDef(
            user_id=1,
            task_type="weekly_recommendation",
            payload='{"genre": "科幻"}',
            schedule_expr="0 9 * * 1",
            timezone="Asia/Shanghai",
        )
        db_session.add(task)
        # Just verify the model can be created without error
        assert task.id is None  # not flushed yet

    def test_create_task_run(self, db_session):
        run = AgentTaskRun(
            task_def_id=1,
            user_id=1,
            scheduled_slot=datetime.now(timezone.utc),
            status="pending",
        )
        assert run.status == "pending"
        db_session.add(run)

    def test_invalid_schedule_timezone_and_credentials_are_rejected(self):
        with pytest.raises(ValueError):
            AgentTaskDef(user_id=1, task_type="x", schedule_expr="not cron")
        with pytest.raises(ValueError):
            AgentTaskDef(user_id=1, task_type="x", timezone="Mars/Base")
        with pytest.raises(ValueError):
            AgentTaskDef(user_id=1, task_type="x", payload='{"api_key": "secret"}')
        with pytest.raises(ValueError):
            AgentTaskDef(user_id=1, task_type="x", schedule_expr="*/0 * * * *")


class TestScheduler:
    @pytest.mark.asyncio
    async def test_start_stop(self):
        scheduler = Scheduler(
            claim_fn=lambda lease: [],
            handler=lambda task_def, run: None,
        )
        assert scheduler._running is False

        await scheduler.start(interval=1)
        assert scheduler._running is True

        await scheduler.stop()
        assert scheduler._running is False

    @pytest.mark.asyncio
    async def test_task_claim_and_execute(self):
        calls = []

        async def handler(task_def, run):
            calls.append((task_def, run))

        scheduler = Scheduler(
            claim_fn=lambda lease: [("def1", "run1")],
            handler=handler,
        )
        await scheduler.poll_once()
        await asyncio.gather(*scheduler._active)

        assert len(calls) >= 1

    @pytest.mark.asyncio
    async def test_poll_error_does_not_crash(self):
        """A failing claim_fn should not crash the scheduler loop."""
        scheduler = Scheduler(
            claim_fn=lambda lease: (_ for _ in ()).throw(RuntimeError("db down")),
            handler=lambda task_def, run: None,
        )
        await scheduler.poll_once()

    @pytest.mark.asyncio
    async def test_repository_claims_a_slot_once_and_recovers_expired_lease(self):
        now = datetime(2026, 1, 1, 9, tzinfo=timezone.utc)
        task_def = AgentTaskDef(
            id=1, user_id=1, task_type="weekly_recommendation",
            schedule_expr="0 9 * * 1", timezone="UTC", next_run=now,
        )
        repository = InMemoryTaskRepository([task_def])
        first = await repository.claim_due(now, lease_seconds=10)
        second = await repository.claim_due(now, lease_seconds=10)
        assert len(first) == 1
        assert second == []
        expired = now.replace(minute=11)
        recovered = await repository.claim_due(expired, lease_seconds=10)
        assert len(recovered) == 1
        await repository.finish(recovered[0].run, success=True)
        assert task_def.next_run > now

    @pytest.mark.asyncio
    async def test_expired_worker_cannot_fence_new_lease(self):
        now = datetime(2026, 1, 1, 9, tzinfo=timezone.utc)
        task_def = AgentTaskDef(id=2, user_id=1, task_type="x", schedule_expr="0 9 * * 1", timezone="UTC", next_run=now)
        repository = InMemoryTaskRepository([task_def])
        first = (await repository.claim_due(now, lease_seconds=1))[0]
        old_lease = first.run.lease_id
        second = (await repository.claim_due(now.replace(minute=10), lease_seconds=1))[0]
        assert second.run.lease_id != old_lease
        assert await repository.finish(second.run, success=True, lease_id=old_lease) is False
        assert second.run.status == "running"

    def test_next_slot_respects_timezone(self):
        slot = next_slot("0 9 * * 1", datetime(2026, 1, 5, 1, tzinfo=timezone.utc), "Asia/Shanghai")
        assert slot.hour == 1 and slot.weekday() == 0


class TestExecution:
    def test_build_agent_task(self):
        task_def = AgentTaskDef(
            id=7,
            user_id=3,
            task_type="weekly_recommendation",
            payload='{"genre": "action"}',
        )
        run = AgentTaskRun(id=42, task_def_id=7, user_id=3, scheduled_slot=datetime.now(timezone.utc))

        agent_task = build_agent_task(task_def, run)

        assert isinstance(agent_task, AgentTask)
        assert agent_task.user_id == 3
        assert agent_task.goal == "推荐动漫"
        assert agent_task.metadata["task_type"] == "weekly_recommendation"
        assert agent_task.metadata["task_def_id"] == 7
        assert agent_task.metadata["run_id"] == 42

    @pytest.mark.asyncio
    async def test_disabled_task_skipped(self):
        task_def = type("FakeDef", (), {"id": 1, "user_id": 1, "enabled": False,
                                        "task_type": "x", "payload": "{}"})()
        run = type("FakeRun", (), {"id": 1})()

        class FakeRuntime:
            async def execute(self, task):
                raise AssertionError("should not be called")

        await handle_task_def(task_def, run, FakeRuntime(), None)
        # no error = pass


class TestPolicy:
    def test_default_denies_all(self):
        policy = ProactivePolicy()
        assert policy.allowed_capabilities == ()
        assert policy.max_retries == 3

    def test_custom_allowed_capabilities(self):
        policy = ProactivePolicy(allowed_capabilities=("search", "get_detail"))
        assert "search" in policy.allowed_capabilities
