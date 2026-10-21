"""Shared trusted composition for the three read-only Collections actions."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from unittest.mock import create_autospec
from uuid import uuid4

import pytest

from app.capabilities.factory import build_capability_registry
from app.harness.contracts import AgentDecision, ExecutionContext
from app.harness.execution import build_runtime
from app.harness.model_gateway import ModelGateway
from app.models import Collection, CollectionStatus, Subject, SubjectType, User
from app.schemas.user import UserRead

FROZEN_ACTIONS = frozenset({"list_collections", "get_collection", "search_collections"})
DEPENDENCIES = {
    "list_collections": "get_user_collections",
    "get_collection": "get_collection",
    "search_collections": "search_collections",
}
OWNER_COMMENT = "collections-read-owner-private-comment"
FOREIGN_COMMENT = "collections-read-foreign-private-comment"


def collections_parameters(scenario: str) -> list[Any]:
    """Build the frozen read inventory from the production Registry."""
    registry = build_capability_registry()
    keys = set()
    descriptors = {}
    for descriptor in registry.list_actions():
        public_name = descriptor.public_name or descriptor.name
        owner = registry.find_action(public_name)
        if owner is None or owner[0].name != "collections" or owner[1].is_side_effect:
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
class CollectionsEnvironment:
    db: Any
    user: UserRead
    foreign_user: UserRead
    shared_source_id: str
    owner_only_source_id: str
    foreign_only_source_id: str


@dataclass
class CollectionsExecution:
    key: tuple[str, str]
    descriptor: Any
    capability: Any
    env: CollectionsEnvironment
    dispatcher: Any
    context: ExecutionContext

    def arguments(self) -> dict[str, Any]:
        if self.key[0] == "get_collection":
            return {"source": "bangumi", "source_id": self.env.shared_source_id}
        if self.key[0] == "search_collections":
            return {"keyword": "Synthetic", "type": int(SubjectType.ANIME)}
        return {"type": int(SubjectType.ANIME)}

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


async def _seed_collections(db: Any) -> CollectionsEnvironment:
    suffix = uuid4().hex[:16]
    owner = User(username=f"collections-read-owner-{suffix}")
    foreign = User(username=f"collections-read-foreign-{suffix}")
    db.add_all([owner, foreign])
    await db.flush()
    assert owner.id is not None and foreign.id is not None

    shared_source_id = f"shared-anime-{suffix}"
    owner_only_source_id = f"owner-only-anime-{suffix}"
    foreign_only_source_id = f"foreign-only-anime-{suffix}"
    subjects = [
        Subject(
            source="bangumi",
            source_id=shared_source_id,
            name="Shared Synthetic Anime",
            type=SubjectType.ANIME,
        ),
        Subject(
            source="bangumi",
            source_id=owner_only_source_id,
            name="Owner Only Synthetic Anime",
            type=SubjectType.ANIME,
        ),
        Subject(
            source="bangumi",
            source_id=foreign_only_source_id,
            name="Foreign Only Synthetic Anime",
            type=SubjectType.ANIME,
        ),
    ]
    db.add_all(subjects)
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
            ),
            Collection(
                user_id=owner.id,
                source="bangumi",
                source_id=owner_only_source_id,
                type=CollectionStatus.DO,
                subject_type=SubjectType.ANIME,
                rate=9,
                private=True,
                comment=OWNER_COMMENT,
            ),
            Collection(
                user_id=foreign.id,
                source="bangumi",
                source_id=foreign_only_source_id,
                type=CollectionStatus.DO,
                subject_type=SubjectType.ANIME,
                rate=6,
                private=True,
                comment=FOREIGN_COMMENT,
            ),
        ]
    )
    await db.commit()

    created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    return CollectionsEnvironment(
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
        owner_only_source_id=owner_only_source_id,
        foreign_only_source_id=foreign_only_source_id,
    )


async def make_execution(
    key: tuple[str, str], db: Any, monkeypatch: Any, *, authenticated: bool = True
) -> CollectionsExecution:
    """Use the production registry, Runtime, Dispatcher, and SQL read path."""
    registry = build_capability_registry()
    owner = registry.find_action(key[0])
    assert owner is not None and owner[0].name == "collections"
    capability, descriptor = owner
    assert descriptor.version == key[1]
    env = await _seed_collections(db)

    gateway = create_autospec(ModelGateway, instance=True)
    for name in ("infer", "stream_infer", "synthesize", "synthesize_result"):
        getattr(gateway, name).side_effect = AssertionError(
            "No model calls in Collections action contracts"
        )
    runtime = build_runtime(
        session=db,
        user=env.user if authenticated else None,
        registry=registry,
        model_gateway=gateway,
        trace_store=None,
        durable=authenticated,
    )
    run_id = "collections-read-cert-" + uuid4().hex
    context = ExecutionContext(
        principal_id=env.user.id if authenticated else None,
        run_id=run_id,
        trace_id=run_id,
        capability_allowlist=frozenset({key[0]}),
    )
    return CollectionsExecution(
        key, descriptor, capability, env, runtime.dispatcher, context
    )


def assert_trusted_dependency_call(
    execution: CollectionsExecution, args: tuple[Any, ...], kwargs: dict[str, Any]
) -> None:
    assert not kwargs
    assert len(args) == 2
    assert args[0] is execution.env.db
    assert args[1].user_id == execution.env.user.id
