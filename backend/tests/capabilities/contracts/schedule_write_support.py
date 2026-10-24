"""Shared real-Runtime setup for the six public Schedule write actions."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, time, timezone
from typing import Any, Awaitable, Callable
from unittest.mock import create_autospec
from uuid import uuid4

import pytest

from app.capabilities import schedule as schedule_module
from app.capabilities.factory import build_capability_registry
from app.harness.budget import CancellationToken
from app.harness.contracts import AgentDecision, ExecutionContext
from app.harness.execution import build_runtime
from app.harness.model_gateway import ModelGateway
from app.harness.policy import Approval
from app.models import Schedule, User
from app.models.enums import WatchType
from app.schemas.schedule import (
    ScheduleCreate,
    ScheduleUpdate,
    ScheduleUpsert,
    ScheduleUpsertList,
)
from app.schemas.user import UserRead

FROZEN_ACTIONS = frozenset(
    {
        "create_schedule",
        "update_schedule",
        "delete_schedule",
        "upsert_schedule",
        "bulk_upsert_schedules",
        "sync_bangumi_schedule",
    }
)

SCENARIOS = (
    "schedule_write_error",
    "schedule_write_timeout",
    "schedule_write_isolation",
    "schedule_write_serialization",
    "schedule_write_authorization",
    "schedule_write_dispatcher",
    "schedule_write_approval",
    "schedule_write_idempotency",
    "schedule_write_recovery",
)

DEPENDENCIES = {
    "create_schedule": "create_schedule",
    "update_schedule": "update_schedule",
    "delete_schedule": "delete_schedule",
    "upsert_schedule": "upsert_schedule",
    "bulk_upsert_schedules": "bulk_upsert_schedules",
    "sync_bangumi_schedule": "sync_bangumi_calendar",
}

_MODEL_TIME = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)


def _schedule_id(schedule: Schedule) -> int:
    value = schedule.id
    assert value is not None
    return value


def schedule_write_parameters(scenario: str) -> list[Any]:
    """Freeze the production Registry's owner=schedule side-effect inventory."""
    registry = build_capability_registry()
    keys = set()
    descriptors = {}
    for descriptor in registry.list_actions():
        public_name = descriptor.public_name or descriptor.name
        owner = registry.find_action(public_name)
        if owner is None or owner[0].name != "schedule" or not owner[1].is_side_effect:
            continue
        key = (public_name, owner[1].version)
        keys.add(key)
        descriptors[key] = owner[1]

    expected = {(name, "v1") for name in FROZEN_ACTIONS}
    assert keys == expected
    assert all(descriptors[key].requires_auth for key in expected)
    assert all(descriptors[key].is_side_effect for key in expected)
    assert all(descriptors[key].approval_required for key in expected)
    assert all(descriptors[key].idempotency_mode == "required" for key in expected)
    assert all(descriptors[key].risk_level == "medium" for key in expected)
    assert all(descriptors[key].output_schema for key in expected)

    assert scenario in SCENARIOS
    return [
        pytest.param(
            key,
            id=f"{key[0]}@{key[1]}-{scenario}",
            marks=pytest.mark.capability_contract(*key, scenario),
        )
        for key in sorted(expected)
    ]


@dataclass
class ScheduleWriteEnvironment:
    db: Any
    user: UserRead
    foreign_user: UserRead
    schedule_id: int
    second_schedule_id: int
    foreign_schedule_id: int
    source_id: str


@dataclass
class ScheduleWriteExecution:
    key: tuple[str, str]
    registry: Any
    capability: Any
    descriptor: Any
    env: ScheduleWriteEnvironment
    model_gateway: Any
    dispatcher: Any
    context: ExecutionContext

    @property
    def db(self) -> Any:
        return self.env.db

    @property
    def user(self) -> UserRead:
        return self.env.user

    @property
    def foreign_user(self) -> UserRead:
        return self.env.foreign_user

    @property
    def source_id(self) -> str:
        return self.env.source_id

    def arguments(self) -> dict[str, Any]:
        action = self.key[0]
        if action == "update_schedule":
            return {"schedule_id": self.env.schedule_id, "day_of_week": 4}
        if action == "delete_schedule":
            return {"schedule_id": self.env.schedule_id}
        if action == "bulk_upsert_schedules":
            return {"items": [self._schedule_values("b")]}
        if action == "sync_bangumi_schedule":
            return {}
        values = self._schedule_values("w")
        if action == "upsert_schedule":
            values["id"] = None
        return values

    def _schedule_values(self, prefix: str) -> dict[str, Any]:
        return {
            "source": "bangumi",
            "source_id": f"{prefix}{self.source_id[1:]}",
            "day_of_week": 3,
            "start_time": "20:30:00",
            "watch_day": 5,
            "watch_time": "21:45:00",
            "duration": 7,
            "watch_type": int(WatchType.NEW),
        }

    async def dispatch(
        self,
        arguments: dict[str, Any] | None = None,
        *,
        action: str | None = None,
        context: ExecutionContext | None = None,
        dispatcher: Any | None = None,
        version: str | None = None,
        idempotency_key: str | None = None,
        include_key: bool = True,
        cancellation: CancellationToken | None = None,
    ):
        current = context or self.context
        target_action = action or self.key[0]
        owner = self.registry.find_action(target_action)
        assert owner is not None and owner[0].name == "schedule"
        public_arguments = deepcopy(
            self.arguments() if arguments is None else arguments
        )
        if include_key:
            public_arguments["idempotency_key"] = idempotency_key or uuid4().hex
        else:
            public_arguments.pop("idempotency_key", None)
        decision = AgentDecision(
            decision_id=uuid4().hex,
            run_id=current.run_id,
            action="invoke",
            capability=target_action,
            capability_version=version or owner[1].version,
            arguments=public_arguments,
        )
        return await (dispatcher or self.dispatcher).dispatch(
            decision, current, cancellation=cancellation
        )

    def make_dispatcher(
        self,
        *,
        db: Any | None = None,
        user: UserRead | None = None,
        authenticated: bool = True,
        durable: bool = True,
        allow_side_effects: bool = True,
        approval: Approval | None = None,
        use_default_approval: bool = True,
    ) -> Any:
        session = db or self.db
        principal = (user or self.user) if authenticated else None
        if use_default_approval:
            action_approval = (
                Approval(
                    approval_id=uuid4().hex,
                    principal_id=principal.id,
                    action=self.key[0],
                )
                if principal is not None
                else None
            )
        else:
            action_approval = approval
        runtime = build_runtime(
            session=session,
            user=principal,
            registry=self.registry,
            model_gateway=self.model_gateway,
            trace_store=None,
            durable=durable,
            allow_side_effects=allow_side_effects,
            approval=action_approval,
        )
        return runtime.dispatcher

    def context_for(self, user: UserRead, *, allowlist: frozenset[str] | None = None):
        return self.context.model_copy(
            update={
                "principal_id": user.id,
                "run_id": "schedule-write-contract-" + uuid4().hex,
                "trace_id": "schedule-write-trace-" + uuid4().hex,
                "capability_allowlist": allowlist
                if allowlist is not None
                else frozenset({self.key[0]}),
            }
        )


async def make_write_execution(key: tuple[str, str], db: Any) -> ScheduleWriteExecution:
    """Compose a real Registry, Runtime, Dispatcher, SQL store, and principals."""
    suffix = uuid4().hex[:10]
    owner_orm = User(username=f"schedule-write-owner-{suffix}")
    foreign_orm = User(username=f"schedule-write-foreign-{suffix}")
    db.add_all([owner_orm, foreign_orm])
    await db.flush()
    assert owner_orm.id is not None and foreign_orm.id is not None

    source_id = f"s{suffix}"
    schedules = [
        Schedule(
            user_id=owner_orm.id,
            source="bangumi",
            source_id=source_id,
            day_of_week=2,
            start_time=time(19, 30),
            watch_day=3,
            watch_time=time(21, 0),
            duration=7,
            watch_type=WatchType.NEW,
        ),
        Schedule(
            user_id=owner_orm.id,
            source="bangumi",
            source_id=f"t{suffix}",
            day_of_week=5,
            start_time=time(20, 0),
            watch_type=WatchType.LEISURE,
        ),
        Schedule(
            user_id=foreign_orm.id,
            source="bangumi",
            source_id=source_id,
            day_of_week=2,
            start_time=time(18, 30),
            watch_type=WatchType.MEAL,
        ),
    ]
    db.add_all(schedules)
    await db.flush()
    assert all(item.id is not None for item in schedules)
    await db.commit()

    created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    owner = UserRead(
        id=owner_orm.id,
        username=owner_orm.username,
        bangumi_name=owner_orm.bangumi_name,
        created_at=created_at,
    )
    foreign = UserRead(
        id=foreign_orm.id,
        username=foreign_orm.username,
        bangumi_name=foreign_orm.bangumi_name,
        created_at=created_at,
    )

    registry = build_capability_registry()
    owner_action = registry.find_action(key[0])
    assert owner_action is not None and owner_action[0].name == "schedule"
    capability, descriptor = owner_action
    assert descriptor.version == key[1]

    gateway = create_autospec(ModelGateway, instance=True)
    for name in ("infer", "stream_infer", "synthesize", "synthesize_result"):
        getattr(gateway, name).side_effect = AssertionError(
            "Schedule write handler contracts must not call a model"
        )

    env = ScheduleWriteEnvironment(
        db=db,
        user=owner,
        foreign_user=foreign,
        schedule_id=_schedule_id(schedules[0]),
        second_schedule_id=_schedule_id(schedules[1]),
        foreign_schedule_id=_schedule_id(schedules[2]),
        source_id=source_id,
    )
    context = ExecutionContext(
        principal_id=owner.id,
        run_id="schedule-write-contract-" + uuid4().hex,
        trace_id="schedule-write-trace-" + uuid4().hex,
        capability_allowlist=frozenset({key[0]}),
    )
    execution = ScheduleWriteExecution(
        key=key,
        registry=registry,
        capability=capability,
        descriptor=descriptor,
        env=env,
        model_gateway=gateway,
        dispatcher=None,
        context=context,
    )
    execution.dispatcher = execution.make_dispatcher()
    return execution


@dataclass
class ServiceBoundary:
    dependency: str
    original: Callable[..., Any]
    calls: list[tuple[tuple[Any, ...], dict[str, Any]]]
    unexpected_calls: list[str]


ServiceHandler = Callable[..., Any | Awaitable[Any]]


def install_schedule_service_boundary(
    execution: ScheduleWriteExecution,
    monkeypatch: Any,
    *,
    handler: ServiceHandler | None = None,
) -> ServiceBoundary:
    """Patch only the selected ScheduleService method; keep handler/Dispatcher real."""
    dependency = DEPENDENCIES[execution.key[0]]
    original = getattr(schedule_module.ScheduleService, dependency)
    boundary = ServiceBoundary(dependency, original, [], [])

    async def invoke(*args: Any, **kwargs: Any):
        assert_trusted_service_call(execution, args, kwargs)
        boundary.calls.append((args, kwargs))
        if handler is None:
            result = original(*args, **kwargs)
        else:
            result = handler(*args, **kwargs)
        if hasattr(result, "__await__"):
            return await result
        return result

    monkeypatch.setattr(schedule_module.ScheduleService, dependency, invoke)
    return boundary


def assert_trusted_service_call(
    execution: ScheduleWriteExecution,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
    *,
    allowed_user_ids: frozenset[int] | None = None,
) -> None:
    """Check that every registered write handler passes server-owned identity."""
    assert not kwargs
    assert args and args[0] is execution.db
    action = execution.key[0]
    users = allowed_user_ids or frozenset(
        {execution.user.id, execution.foreign_user.id}
    )

    if action == "create_schedule":
        assert len(args) == 3 and args[1] in users
        request = args[2]
        assert isinstance(request, ScheduleCreate)
        assert request.user_id == args[1]
        assert request.source == "bangumi"
        assert 0 < len(request.source_id) <= 20
        return
    if action == "update_schedule":
        assert len(args) == 4 and args[2] in users
        assert type(args[1]) is int
        assert isinstance(args[3], ScheduleUpdate)
        assert args[3].day_of_week in {None, 4}
        return
    if action == "delete_schedule":
        assert len(args) == 3 and type(args[1]) is int and args[2] in users
        return
    if action == "upsert_schedule":
        assert len(args) == 3 and args[1] in users
        request = args[2]
        assert isinstance(request, ScheduleUpsert)
        assert request.user_id == args[1]
        assert request.source == "bangumi"
        assert 0 < len(request.source_id) <= 20
        return
    if action == "bulk_upsert_schedules":
        assert len(args) == 3 and args[1] in users
        request = args[2]
        assert isinstance(request, ScheduleUpsertList)
        assert all(item.user_id == args[1] for item in request.items)
        assert all(item.source == "bangumi" for item in request.items)
        assert all(len(item.source_id) <= 20 for item in request.items)
        return
    if action == "sync_bangumi_schedule":
        assert len(args) == 2 and args[1] in users
        return
    raise AssertionError(f"Unexpected Schedule write action: {action}")
