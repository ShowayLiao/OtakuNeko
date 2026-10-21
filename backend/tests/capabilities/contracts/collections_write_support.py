"""Shared real-Runtime setup for the eight public Collections write actions."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable
from unittest.mock import create_autospec
from uuid import uuid4

import pytest

from app.capabilities import collections as collections_module
from app.capabilities.factory import build_capability_registry
from app.harness.contracts import AgentDecision, ExecutionContext
from app.harness.execution import build_runtime
from app.harness.model_gateway import ModelGateway
from app.harness.policy import Approval
from app.models import CollectionStatus, SubjectType, User
from app.schemas.adaptersV2 import UnifiedCollectionSubject
from app.schemas.collection import (
    CollectionCreate,
    CollectionSearchByID,
    CollectionSyncRequest,
    CollectionUpdate,
    CollectionUpsertList,
)
from app.schemas.subject import SubjectRead
from app.schemas.user import UserRead


FROZEN_ACTIONS = frozenset(
    {
        "create_collection",
        "update_collection",
        "delete_collection",
        "upsert_collection",
        "batch_upsert_collections",
        "import_json_collections",
        "sync_bangumi_collections",
        "sync_douban_collections",
    }
)

SCENARIOS = (
    "collections_write_error",
    "collections_write_timeout",
    "collections_write_isolation",
    "collections_write_serialization",
    "collections_write_authorization",
    "collections_write_dispatcher",
    "collections_write_approval",
    "collections_write_idempotency",
)

DEPENDENCIES = {
    "create_collection": "create_collection",
    "update_collection": "update_collection",
    "delete_collection": "delete_collection",
    "upsert_collection": "upsert_collection",
    "batch_upsert_collections": "batch_upsert_collections",
    "import_json_collections": "import_json_collections",
    "sync_bangumi_collections": "sync_user_collections",
    "sync_douban_collections": "sync_user_collections_douban",
}

_ALL_IMPORTED_DEPENDENCIES = frozenset(
    {
        *DEPENDENCIES.values(),
        "get_user_collections",
        "get_collection",
        "search_collections",
    }
)
_MODEL_TIME = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)


def collections_write_parameters(scenario: str | None = None) -> list[Any]:
    """Freeze the current owner=collections, side-effect Registry inventory."""
    registry = build_capability_registry()
    keys = set()
    descriptors = {}
    for descriptor in registry.list_actions():
        public_name = descriptor.public_name or descriptor.name
        owner = registry.find_action(public_name)
        if (
            owner is None
            or owner[0].name != "collections"
            or not owner[1].is_side_effect
        ):
            continue
        key = (public_name, owner[1].version)
        keys.add(key)
        descriptors[key] = owner[1]

    expected = {(name, "v1") for name in FROZEN_ACTIONS}
    assert keys == expected
    assert all(descriptors[key].requires_auth for key in expected)
    assert all(descriptors[key].is_side_effect for key in expected)

    labels = (scenario,) if scenario is not None else SCENARIOS
    assert set(labels) <= set(SCENARIOS)
    return [
        pytest.param(
            key,
            label,
            id=f"{key[0]}@{key[1]}-{label}",
            marks=pytest.mark.capability_contract(*key, label),
        )
        for key in sorted(expected)
        for label in labels
    ]


@dataclass
class CollectionsWriteExecution:
    key: tuple[str, str]
    registry: Any
    capability: Any
    descriptor: Any
    db: Any
    user: UserRead
    model_gateway: Any
    dispatcher: Any
    context: ExecutionContext
    source_id: str

    def arguments(self) -> dict[str, Any]:
        action = self.key[0]
        common = {
            "source": "bangumi",
            "source_id": self.source_id,
            "type": 2,
            "rate": 8,
            "comment": "synthetic-collections-write-comment",
            "private": True,
            "tags": ["synthetic"],
        }
        if action in {"create_collection", "update_collection", "upsert_collection"}:
            return common
        if action == "delete_collection":
            return {"source": "bangumi", "source_id": self.source_id}
        if action == "batch_upsert_collections":
            return {
                "items": [
                    {**common, "source_id": f"{self.source_id}-a"},
                    {**common, "source_id": f"{self.source_id}-b"},
                ]
            }
        if action == "import_json_collections":
            return {
                "data": {
                    "data": [
                        {
                            "subject_id": f"{self.source_id}-a",
                            "type": 2,
                            "subject": {"id": 801, "name": "Synthetic A", "type": 2},
                        },
                        {
                            "subject_id": f"{self.source_id}-b",
                            "type": 3,
                            "subject": {"id": 802, "name": "Synthetic B", "type": 2},
                        },
                    ]
                }
            }
        if action == "sync_bangumi_collections":
            return {"subject_type": 2, "limit": 2, "offset": 0}
        if action == "sync_douban_collections":
            return {
                "data": [
                    {
                        "interest": {
                            "status": "done",
                            "subject": {"id": "douban-write-a", "type": "tv"},
                            "rating": {"value": 4.5},
                        }
                    },
                    {
                        "interest": {
                            "status": "doing",
                            "subject": {"id": "douban-write-b", "type": "movie"},
                            "rating": {"value": 4.0},
                        }
                    },
                ]
            }
        raise AssertionError(f"Unexpected Collections action: {action}")

    async def dispatch(
        self,
        arguments: dict[str, Any] | None = None,
        *,
        context: ExecutionContext | None = None,
        dispatcher: Any | None = None,
        version: str | None = None,
        idempotency_key: str | None = None,
        include_key: bool = True,
    ):
        current = context or self.context
        values = self.arguments() if arguments is None else arguments
        public_arguments = dict(values)
        if include_key:
            public_arguments["idempotency_key"] = idempotency_key or uuid4().hex
        else:
            public_arguments.pop("idempotency_key", None)
        decision = AgentDecision(
            decision_id=uuid4().hex,
            run_id=current.run_id,
            action="invoke",
            capability=self.key[0],
            capability_version=version or self.key[1],
            arguments=public_arguments,
        )
        target = dispatcher or self.dispatcher
        return await target.dispatch(decision, current)

    def make_dispatcher(
        self,
        *,
        db: Any | None = None,
        authenticated: bool = True,
        durable: bool = True,
        allow_side_effects: bool = True,
        approval: Approval | None = None,
        use_default_approval: bool = True,
    ) -> Any:
        runtime_user = self.user if authenticated else None
        if use_default_approval:
            action_approval = (
                Approval(
                    approval_id=uuid4().hex,
                    principal_id=self.user.id,
                    action=self.key[0],
                )
                if authenticated
                else None
            )
        else:
            action_approval = approval
        runtime = build_runtime(
            session=db or self.db,
            user=runtime_user,
            registry=self.registry,
            model_gateway=self.model_gateway,
            trace_store=None,
            durable=durable,
            allow_side_effects=allow_side_effects,
            approval=action_approval,
        )
        return runtime.dispatcher


async def make_collections_write_execution(
    key: tuple[str, str], db: Any
) -> CollectionsWriteExecution:
    """Compose a real Registry, Runtime, Dispatcher, SQL store, and principal."""
    suffix = uuid4().hex[:12]
    orm_user = User(username=f"collections-write-{suffix}")
    db.add(orm_user)
    await db.flush()
    assert orm_user.id is not None
    user = UserRead(
        id=orm_user.id,
        username=orm_user.username,
        bangumi_name=f"collections-write-bangumi-{suffix}",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    await db.commit()

    registry = build_capability_registry()
    owner = registry.find_action(key[0])
    assert owner is not None and owner[0].name == "collections"
    capability, descriptor = owner
    assert descriptor.version == key[1]

    model_gateway = create_autospec(ModelGateway, instance=True)
    for name in ("infer", "stream_infer", "synthesize", "synthesize_result"):
        getattr(model_gateway, name).side_effect = AssertionError(
            "Collections write contract tests must not call a model"
        )

    context = ExecutionContext(
        principal_id=user.id,
        run_id="collections-write-contract-" + uuid4().hex,
        trace_id="collections-write-trace-" + uuid4().hex,
        capability_allowlist=frozenset({key[0]}),
    )
    execution = CollectionsWriteExecution(
        key=key,
        registry=registry,
        capability=capability,
        descriptor=descriptor,
        db=db,
        user=user,
        model_gateway=model_gateway,
        dispatcher=None,
        context=context,
        source_id=f"write-{suffix}-{key[0]}",
    )
    execution.dispatcher = execution.make_dispatcher()
    return execution


def collection_read(execution: CollectionsWriteExecution, source_id: str | None = None):
    from app.schemas.collection import CollectionRead

    return CollectionRead(
        type=CollectionStatus.DO,
        source="bangumi",
        source_id=source_id or execution.source_id,
        user_id=execution.user.id,
        rate=8,
        comment="synthetic-collections-write-comment",
        tags=["synthetic"],
        private=True,
        updated_at=_MODEL_TIME,
    )


def unified_collection(
    execution: CollectionsWriteExecution,
) -> UnifiedCollectionSubject:
    return UnifiedCollectionSubject(
        collection=collection_read(execution),
        subject=SubjectRead(
            id=901,
            name="Synthetic Write Subject",
            name_cn="合成条目",
            type=SubjectType.ANIME,
            source="bangumi",
            source_id=execution.source_id,
            summary="Synthetic collections write contract subject",
            air_time=_MODEL_TIME,
            air_weekday=2,
        ),
    )


def successful_service_result(execution: CollectionsWriteExecution) -> Any:
    action = execution.key[0]
    if action in {"create_collection", "update_collection"}:
        return collection_read(execution)
    if action == "upsert_collection":
        return unified_collection(execution)
    if action == "delete_collection":
        return True
    return 2


@dataclass
class ServiceBoundary:
    calls: list[str]
    unexpected_calls: list[str]


ServiceHandler = Callable[..., Any | Awaitable[Any]]


def install_collections_service_boundary(
    execution: CollectionsWriteExecution,
    monkeypatch: Any,
    *,
    handler: ServiceHandler | None = None,
) -> ServiceBoundary:
    """Patch only imported service functions; the registered handler stays real."""
    boundary = ServiceBoundary(calls=[], unexpected_calls=[])
    target_name = DEPENDENCIES[execution.key[0]]

    for dependency in _ALL_IMPORTED_DEPENDENCIES:

        async def unexpected(*args: Any, _name: str = dependency, **kwargs: Any):
            boundary.unexpected_calls.append(_name)
            raise AssertionError(f"Unexpected Collections service call: {_name}")

        monkeypatch.setattr(collections_module, dependency, unexpected)

    async def invoke(*args: Any, **kwargs: Any):
        assert_trusted_dependency_call(execution, args, kwargs)
        boundary.calls.append(target_name)
        if handler is None:
            return successful_service_result(execution)
        result = handler(*args, **kwargs)
        if hasattr(result, "__await__"):
            return await result
        return result

    monkeypatch.setattr(collections_module, target_name, invoke)
    return boundary


def assert_trusted_dependency_call(
    execution: CollectionsWriteExecution,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> None:
    """Assert each real handler sent identity and request data to its service."""
    action = execution.key[0]
    if action in {"create_collection", "update_collection"}:
        assert not kwargs and len(args) == 2
        assert args[0] is execution.db
        request = args[1]
        assert isinstance(
            request,
            CollectionCreate if action == "create_collection" else CollectionUpdate,
        )
        assert request.user_id == execution.user.id
        assert request.source == "bangumi" and request.source_id == execution.source_id
        return

    if action == "delete_collection":
        assert not kwargs and len(args) == 2
        assert args[0] is execution.db
        request = args[1]
        assert isinstance(request, CollectionSearchByID)
        assert request.user_id == execution.user.id
        assert request.source == "bangumi" and request.source_id == execution.source_id
        return

    if action == "upsert_collection":
        assert len(args) == 2 and args[0] is execution.db
        assert args[1] == execution.user.id
        assert set(kwargs) == {"data"}
        payload = kwargs["data"]
        assert isinstance(payload, dict) and isinstance(payload.get("collection"), dict)
        assert payload["collection"]["source"] == "bangumi"
        assert payload["collection"]["source_id"] == execution.source_id
        return

    if action == "batch_upsert_collections":
        assert not kwargs and len(args) == 3
        assert args[0] is execution.db and args[2] == execution.user.id
        request = args[1]
        assert isinstance(request, CollectionUpsertList)
        assert request.total == 2 and len(request.collections) == 2
        assert all(item.user_id == execution.user.id for item in request.collections)
        assert all(item.source == "bangumi" for item in request.collections)
        return

    if action == "import_json_collections":
        assert not kwargs and len(args) == 3
        assert args[0] is execution.db and args[2] == execution.user.id
        assert isinstance(args[1], dict) and len(args[1].get("data", [])) == 2
        return

    if action == "sync_bangumi_collections":
        assert not args and set(kwargs) == {"db", "user", "request_data"}
        assert kwargs["db"] is execution.db
        assert kwargs["user"].id == execution.user.id
        assert isinstance(kwargs["request_data"], CollectionSyncRequest)
        return

    if action == "sync_douban_collections":
        assert not kwargs and len(args) == 3
        assert args[0] == execution.user.id and args[1] is execution.db
        assert isinstance(args[2], list) and len(args[2]) == 2
        return

    raise AssertionError(f"Unexpected Collections action: {action}")


def assert_no_public_user_id(value: Any) -> None:
    if isinstance(value, dict):
        assert "user_id" not in value
        for child in value.values():
            assert_no_public_user_id(child)
    elif isinstance(value, list):
        for child in value:
            assert_no_public_user_id(child)
