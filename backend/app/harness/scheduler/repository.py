"""Atomic task claiming primitives used by the reference scheduler."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable


@dataclass
class Claim:
    task_def: Any
    run: Any


class InMemoryTaskRepository:
    """Deterministic repository with database-like claim semantics.

    Production deployments can replace this object with a SQL implementation;
    the lock and unique-slot rules are deliberately part of this interface.
    """

    def __init__(self, task_defs: Iterable[Any] = ()) -> None:
        self.task_defs = list(task_defs)
        self.runs: dict[tuple[int, datetime], Any] = {}
        self._lock = asyncio.Lock()
        self._run_id = 0

    async def add(self, task_def: Any) -> Any:
        async with self._lock:
            if getattr(task_def, "id", None) is None:
                task_def.id = len(self.task_defs) + 1
            self.task_defs.append(task_def)
            return task_def

    async def list_for_user(self, user_id: int) -> list[Any]:
        return [item for item in self.task_defs if item.user_id == user_id and item.deleted_at is None]

    async def set_enabled(self, task_id: int, user_id: int, enabled: bool) -> Any | None:
        for item in self.task_defs:
            if item.id == task_id and item.user_id == user_id and item.deleted_at is None:
                item.enabled = enabled
                return item
        return None

    async def update(self, task_id: int, user_id: int, values: dict[str, Any]) -> Any | None:
        for item in self.task_defs:
            if item.id == task_id and item.user_id == user_id and item.deleted_at is None:
                for key, value in values.items():
                    setattr(item, key, value)
                if "policy" in values:
                    from app.harness.policy import ProactivePolicy

                    ProactivePolicy.from_json(item.policy)
                item.validate_definition()
                if "schedule_expr" in values or "timezone" in values:
                    from app.harness.scheduler.time import next_slot

                    item.next_run = next_slot(item.schedule_expr, datetime.now(timezone.utc), item.timezone)
                return item
        return None

    async def delete(self, task_id: int, user_id: int) -> bool:
        for item in self.task_defs:
            if item.id == task_id and item.user_id == user_id:
                item.enabled = False
                item.deleted_at = datetime.now(timezone.utc)
                return True
        return False

    async def runs_for(self, task_id: int, user_id: int) -> list[Any] | None:
        task = next((item for item in self.task_defs if item.id == task_id and item.user_id == user_id), None)
        return None if task is None else [run for run in self.runs.values() if run.task_def_id == task_id]

    async def claim_due(
        self,
        now: datetime,
        lease_seconds: int,
        limit: int = 100,
    ) -> list[Claim]:
        now = _aware(now)
        claimed: list[Claim] = []
        async with self._lock:
            for task_def in self.task_defs:
                if not getattr(task_def, "enabled", False) or getattr(task_def, "deleted_at", None) is not None:
                    continue
                next_run = getattr(task_def, "next_run", None)
                if next_run is None or _aware(next_run) > now or len(claimed) >= limit:
                    continue
                slot = _aware(next_run)
                if getattr(task_def, "catch_up", "latest") == "skip" and slot < now:
                    from app.harness.scheduler.time import next_slot

                    while slot < now:
                        slot = next_slot(task_def.schedule_expr, slot, task_def.timezone)
                    task_def.next_run = slot
                    continue
                if getattr(task_def, "catch_up", "latest") == "latest" and slot < now:
                    from app.harness.scheduler.time import next_slot

                    latest = slot
                    while True:
                        candidate = next_slot(task_def.schedule_expr, latest, task_def.timezone)
                        if candidate > now:
                            break
                        latest = candidate
                    slot = latest
                key = (int(task_def.id), slot)
                existing = self.runs.get(key)
                if existing is not None and existing.status == "running" and _aware(existing.lease_expires_at) > now:
                    continue
                if existing is None:
                    self._run_id += 1
                    existing = _new_run(task_def, self._run_id, slot)
                    self.runs[key] = existing
                existing.status = "running"
                existing.attempt += 1
                existing.lease_id = uuid.uuid4().hex
                existing.lease_expires_at = now + timedelta(seconds=lease_seconds)
                claimed.append(Claim(task_def, existing))
        return claimed

    async def finish(self, run: Any, *, success: bool, error_category: str | None = None, lease_id: str | None = None) -> bool:
        async with self._lock:
            if lease_id is not None and run.lease_id != lease_id:
                return False
            run.status = "success" if success else ("cancelled" if error_category == "cancelled" else "failed")
            run.error_category = error_category
            run.finished_at = datetime.now(timezone.utc)
            run.lease_id = None
            run.lease_expires_at = None
            task_def = next((item for item in self.task_defs if item.id == run.task_def_id), None)
            if task_def is not None:
                from app.harness.scheduler.time import next_slot

                task_def.next_run = next_slot(
                    task_def.schedule_expr, run.scheduled_slot, task_def.timezone
                )
            return True


def _aware(value: datetime | None) -> datetime:
    if value is None:
        return datetime.min.replace(tzinfo=timezone.utc)
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _new_run(task_def: Any, run_id: int, slot: datetime) -> Any:
    from app.models.agent_task import AgentTaskRun

    return AgentTaskRun(
        id=run_id,
        task_def_id=task_def.id,
        user_id=task_def.user_id,
        scheduled_slot=slot,
        status="pending",
    )


class SqlTaskRepository:
    """Async SQLModel repository for production claim/lease persistence."""

    def __init__(self, session_factory: Any) -> None:
        self._session_factory = session_factory

    async def add(self, task_def: Any) -> Any:
        async with self._session_factory() as session:
            session.add(task_def)
            await session.commit()
            await session.refresh(task_def)
            return task_def

    async def list_for_user(self, user_id: int) -> list[Any]:
        from sqlalchemy import select
        from app.models.agent_task import AgentTaskDef

        async with self._session_factory() as session:
            result = await session.execute(select(AgentTaskDef).where(AgentTaskDef.user_id == user_id, AgentTaskDef.deleted_at.is_(None)))
            return list(result.scalars())

    async def set_enabled(self, task_id: int, user_id: int, enabled: bool) -> Any | None:
        from app.models.agent_task import AgentTaskDef

        async with self._session_factory() as session:
            task = await session.get(AgentTaskDef, task_id)
            if task is None or task.user_id != user_id or task.deleted_at is not None:
                return None
            task.enabled = enabled
            await session.commit()
            return task

    async def update(self, task_id: int, user_id: int, values: dict[str, Any]) -> Any | None:
        from app.models.agent_task import AgentTaskDef

        async with self._session_factory() as session:
            task = await session.get(AgentTaskDef, task_id)
            if task is None or task.user_id != user_id or task.deleted_at is not None:
                return None
            for key, value in values.items():
                setattr(task, key, value)
            if "policy" in values:
                from app.harness.policy import ProactivePolicy

                ProactivePolicy.from_json(task.policy)
            task.validate_definition()
            if "schedule_expr" in values or "timezone" in values:
                from app.harness.scheduler.time import next_slot

                task.next_run = next_slot(task.schedule_expr, datetime.now(timezone.utc), task.timezone)
            await session.commit()
            return task

    async def delete(self, task_id: int, user_id: int) -> bool:
        from app.models.agent_task import AgentTaskDef

        async with self._session_factory() as session:
            task = await session.get(AgentTaskDef, task_id)
            if task is None or task.user_id != user_id:
                return False
            task.enabled = False
            task.deleted_at = datetime.now(timezone.utc)
            await session.commit()
            return True

    async def runs_for(self, task_id: int, user_id: int) -> list[Any] | None:
        from sqlalchemy import select
        from app.models.agent_task import AgentTaskDef, AgentTaskRun

        async with self._session_factory() as session:
            task = await session.get(AgentTaskDef, task_id)
            if task is None or task.user_id != user_id:
                return None
            result = await session.execute(select(AgentTaskRun).where(AgentTaskRun.task_def_id == task_id))
            return list(result.scalars())

    async def claim_due(self, now: datetime, lease_seconds: int, limit: int = 100) -> list[Claim]:
        from sqlalchemy import select
        from app.models.agent_task import AgentTaskDef, AgentTaskRun
        now = _aware(now)
        claimed: list[Claim] = []
        async with self._session_factory() as session:
            result = await session.execute(
                select(AgentTaskDef)
                .where(AgentTaskDef.enabled.is_(True), AgentTaskDef.deleted_at.is_(None), AgentTaskDef.next_run <= now)
                .with_for_update(skip_locked=True)
                .limit(limit)
            )
            for task_def in result.scalars():
                slot = _aware(task_def.next_run)
                if getattr(task_def, "catch_up", "latest") == "skip" and slot < now:
                    from app.harness.scheduler.time import next_slot

                    while slot < now:
                        slot = next_slot(task_def.schedule_expr, slot, task_def.timezone)
                    task_def.next_run = slot
                    continue
                if getattr(task_def, "catch_up", "latest") == "latest" and slot < now:
                    from app.harness.scheduler.time import next_slot

                    latest = slot
                    while True:
                        candidate = next_slot(task_def.schedule_expr, latest, task_def.timezone)
                        if candidate > now:
                            break
                        latest = candidate
                    slot = latest
                existing_result = await session.execute(
                    select(AgentTaskRun)
                    .where(
                        AgentTaskRun.task_def_id == task_def.id,
                        AgentTaskRun.scheduled_slot == slot,
                    )
                    .with_for_update()
                )
                run = existing_result.scalar_one_or_none()
                if run is None:
                    run = AgentTaskRun(
                        task_def_id=task_def.id,
                        user_id=task_def.user_id,
                        scheduled_slot=slot,
                    )
                    session.add(run)
                    await session.flush()
                elif run.status == "running" and _aware(run.lease_expires_at) > now:
                    continue
                run.status = "running"
                run.attempt += 1
                run.lease_id = uuid.uuid4().hex
                run.lease_expires_at = now + timedelta(seconds=lease_seconds)
                claimed.append(Claim(task_def, run))
            await session.commit()
        return claimed

    async def finish(self, run: Any, *, success: bool, error_category: str | None = None, lease_id: str | None = None) -> bool:
        from app.models.agent_task import AgentTaskDef

        async with self._session_factory() as session:
            stored = await session.get(type(run), run.id)
            if stored is not None and lease_id is not None and stored.lease_id != lease_id:
                return False
            if stored is not None:
                stored.status = "success" if success else ("cancelled" if error_category == "cancelled" else "failed")
                stored.error_category = error_category
                stored.trace_id = run.trace_id
                stored.finished_at = datetime.now(timezone.utc)
                stored.lease_id = None
                stored.lease_expires_at = None
                task_def = await session.get(AgentTaskDef, stored.task_def_id)
                if task_def is not None:
                    from app.harness.scheduler.time import next_slot

                    task_def.next_run = next_slot(
                        task_def.schedule_expr, stored.scheduled_slot, task_def.timezone
                    )
                await session.commit()
                return True
            return False
