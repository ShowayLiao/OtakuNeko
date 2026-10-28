"""Shared trusted composition for the three read-only Schedule actions."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, time, timezone
from typing import Any
from unittest.mock import create_autospec
from uuid import uuid4

import pytest

from app.capabilities.factory import build_capability_registry
from app.harness.contracts import AgentDecision, ExecutionContext
from app.harness.execution import build_runtime
from app.harness.model_gateway import ModelGateway
from app.models import (
    Collection,
    CollectionStatus,
    Schedule,
    Subject,
    SubjectType,
    User,
)
from app.models.enums import WatchType
from app.schemas.user import UserRead

FROZEN_ACTIONS = frozenset(
    {"list_schedules", "list_schedules_by_day", "list_unified_schedules"}
)
DEPENDENCIES = {
    "list_schedules": "get_user_schedules",
    "list_schedules_by_day": "get_schedules_by_day",
    "list_unified_schedules": "get_unified_user_schedules",
}
OWNER_COMMENT = "schedule-read-owner-private-comment"
FOREIGN_COMMENT = "schedule-read-foreign-private-comment"


def schedule_parameters(scenario: str) -> list[Any]:
    """Build the frozen read inventory from the production Registry."""
    registry = build_capability_registry()
    keys = set()
    descriptors = {}
    for descriptor in registry.list_actions():
        public_name = descriptor.public_name or descriptor.name
        owner = registry.find_action(public_name)
        if owner is None or owner[0].name != "schedule" or owner[1].is_side_effect:
            continue
        key = (public_name, owner[1].version)
        keys.add(key)
        descriptors[key] = owner[1]

    expected = {(name, "v1") for name in FROZEN_ACTIONS}
    assert keys == expected
    assert all(descriptors[key].requires_auth for key in expected)
    assert all(not descriptors[key].is_side_effect for key in expected)

    return [
        pytest.param(
            key,
            id=f"{key[0]}@{key[1]}-{scenario}",
            marks=pytest.mark.capability_contract(*key, scenario),
        )
        for key in sorted(expected)
    ]


@dataclass
class ScheduleEnvironment:
    db: Any
    user: UserRead
    foreign_user: UserRead
    shared_source_id: str
    subject_only_source_id: str
    collection_only_source_id: str
    owner_schedule_ids: frozenset[int]
    by_day_schedule_ids: frozenset[int]


@dataclass
class ScheduleExecution:
    key: tuple[str, str]
    descriptor: Any
    capability: Any
    env: ScheduleEnvironment
    dispatcher: Any
    context: ExecutionContext

    def arguments(self) -> dict[str, Any]:
        if self.key[0] == "list_schedules_by_day":
            return {"day_of_week": 2}
        return {}

    async def dispatch(
        self,
        arguments: dict[str, Any] | None = None,
        *,
        context: ExecutionContext | None = None,
        version: str | None = None,
        forged: bool = False,
    ):
        current = context or self.context
        values: dict[str, Any] = {
            "decision_id": uuid4().hex,
            "run_id": current.run_id,
            "action": "invoke",
            "capability": self.key[0],
            "capability_version": version or self.key[1],
            "arguments": deepcopy(self.arguments() if arguments is None else arguments),
        }
        decision = (
            AgentDecision.model_construct(**values)
            if forged
            else AgentDecision(**values)
        )
        return await self.dispatcher.dispatch(decision, current)


async def _seed_schedules(db: Any) -> ScheduleEnvironment:
    # ScheduleRead caps source_id at 20 characters. Keep the test IDs within
    # that real schema while retaining enough random entropy across runs.
    suffix = uuid4().hex[:18]
    owner = User(username=f"schedule-read-owner-{suffix}")
    foreign = User(username=f"schedule-read-foreign-{suffix}")
    db.add_all([owner, foreign])
    await db.flush()
    assert owner.id is not None and foreign.id is not None

    shared_source_id = f"s{suffix}"
    subject_only_source_id = f"u{suffix}"
    collection_only_source_id = f"c{suffix}"
    db.add_all(
        [
            Subject(
                source="bangumi",
                source_id=shared_source_id,
                name="Shared Schedule Subject",
                type=SubjectType.ANIME,
            ),
            Subject(
                source="bangumi",
                source_id=subject_only_source_id,
                name="Schedule Subject Without Collection",
                type=SubjectType.ANIME,
            ),
        ]
    )
    schedules = [
        Schedule(
            user_id=owner.id,
            source="bangumi",
            source_id=shared_source_id,
            day_of_week=2,
            start_time=time(19, 30),
            watch_day=3,
            watch_time=time(21, 45),
            duration=24,
            watch_type=WatchType.NEW,
        ),
        Schedule(
            user_id=owner.id,
            source="bangumi",
            source_id=subject_only_source_id,
            day_of_week=2,
            start_time=time(20, 10),
            watch_day=None,
            watch_time=None,
            duration=None,
            watch_type=WatchType.LEISURE,
        ),
        Schedule(
            user_id=owner.id,
            source="bangumi",
            source_id=collection_only_source_id,
            day_of_week=6,
            start_time=time(22, 15),
            watch_day=0,
            watch_time=time(23, 0),
            duration=7,
            watch_type=None,
        ),
        Schedule(
            user_id=foreign.id,
            source="bangumi",
            source_id=shared_source_id,
            day_of_week=2,
            start_time=time(18, 0),
            watch_type=WatchType.MEAL,
        ),
    ]
    db.add_all(schedules)
    await db.flush()
    owner_schedule_ids = frozenset(
        int(item.id) for item in schedules[:3] if item.id is not None
    )
    by_day_schedule_ids = frozenset(
        int(item.id) for item in schedules[:2] if item.id is not None
    )
    db.add_all(
        [
            Collection(
                user_id=owner.id,
                source="bangumi",
                source_id=shared_source_id,
                type=CollectionStatus.DO,
                subject_type=SubjectType.ANIME,
                rate=8,
                private=True,
                comment=OWNER_COMMENT,
                tags=["schedule-owner-private-tag"],
            ),
            Collection(
                user_id=foreign.id,
                source="bangumi",
                source_id=shared_source_id,
                type=CollectionStatus.DO,
                subject_type=SubjectType.ANIME,
                rate=3,
                private=True,
                comment=FOREIGN_COMMENT,
                tags=["schedule-foreign-private-tag"],
            ),
            Collection(
                user_id=owner.id,
                source="bangumi",
                source_id=collection_only_source_id,
                type=CollectionStatus.WISH,
                subject_type=SubjectType.ANIME,
                rate=6,
                private=True,
                comment=OWNER_COMMENT,
            ),
        ]
    )
    await db.commit()

    created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return ScheduleEnvironment(
        db=db,
        user=UserRead(
            id=owner.id,
            username=owner.username,
            bangumi_name=owner.bangumi_name,
            created_at=created_at,
        ),
        foreign_user=UserRead(
            id=foreign.id,
            username=foreign.username,
            bangumi_name=foreign.bangumi_name,
            created_at=created_at,
        ),
        shared_source_id=shared_source_id,
        subject_only_source_id=subject_only_source_id,
        collection_only_source_id=collection_only_source_id,
        owner_schedule_ids=owner_schedule_ids,
        by_day_schedule_ids=by_day_schedule_ids,
    )


async def make_execution(
    key: tuple[str, str], db: Any, *, authenticated: bool = True
) -> ScheduleExecution:
    """Use the production Registry, Runtime, Dispatcher, and SQL read path."""
    registry = build_capability_registry()
    owner = registry.find_action(key[0])
    assert owner is not None and owner[0].name == "schedule"
    capability, descriptor = owner
    assert descriptor.version == key[1]
    env = await _seed_schedules(db)

    gateway = create_autospec(ModelGateway, instance=True)
    for name in ("infer", "stream_infer", "synthesize", "synthesize_result"):
        getattr(gateway, name).side_effect = AssertionError(
            "No model calls in Schedule action contracts"
        )
    runtime = build_runtime(
        session=db,
        user=env.user if authenticated else None,
        registry=registry,
        model_gateway=gateway,
        trace_store=None,
        durable=authenticated,
    )
    run_id = "schedule-read-cert-" + uuid4().hex
    context = ExecutionContext(
        principal_id=env.user.id if authenticated else None,
        run_id=run_id,
        trace_id=run_id,
        capability_allowlist=frozenset({key[0]}),
    )
    return ScheduleExecution(
        key, descriptor, capability, env, runtime.dispatcher, context
    )


def assert_trusted_service_call(
    execution: ScheduleExecution, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> None:
    assert not kwargs
    assert args[0] is execution.env.db
    assert args[1] == execution.env.user.id
    if execution.key[0] == "list_schedules_by_day":
        assert len(args) == 3
        assert args[2] == 2
    else:
        assert len(args) == 2
