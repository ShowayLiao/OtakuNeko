"""Real owned SQL filtering and safe read-only collection boundaries."""

from __future__ import annotations

import json
import logging

import pytest
from sqlalchemy.exc import SQLAlchemyError

from app.capabilities import collections as capability_module
from app.capabilities.collections import CollectionCapability
from app.models import Collection, CollectionStatus, Subject, SubjectType, User
from app.harness.normalizer import ResultNormalizer, SchemaContractError, validate_input
from app.services import collection_service
from app.repositories import collection_repo

READ_ACTIONS = {"list_collections", "get_collection", "search_collections"}
ARGUMENTS = {
    "list_collections": {},
    "get_collection": {"source": "bangumi", "source_id": "shared-anime"},
    "search_collections": {"keyword": "Shared"},
}


async def _seed(db):
    users = [User(username="collections-read-a"), User(username="collections-read-b")]
    db.add_all(users)
    await db.commit()
    ids = [user.id for user in users if user.id is not None]
    assert len(ids) == 2
    for source_id, kind, title in (
        ("shared-anime", SubjectType.ANIME, "Shared synthetic anime"),
        ("shared-book", SubjectType.BOOK, "Shared synthetic book"),
        ("foreign-only", SubjectType.ANIME, "Foreign synthetic anime"),
    ):
        db.add(
            Subject(
                source_id=source_id, name=title, type=kind, tags=[{"name": "Synthetic"}]
            )
        )
    for index, (user_id, source_id, subject_type, rate) in enumerate(
        (
            (ids[0], "shared-anime", 2, 8),
            (ids[0], "shared-book", 1, 9),
            (ids[1], "shared-anime", 2, 3),
            (ids[1], "foreign-only", 2, 6),
        )
    ):
        db.add(
            Collection(
                user_id=user_id,
                source_id=source_id,
                type=CollectionStatus.DO,
                subject_type=subject_type,
                rate=rate,
                private=True,
                comment=f"owned-comment-{index}",
            )
        )
    await db.commit()
    return ids


async def _verify_owned_queries(db):
    ids = await _seed(db)
    capability = CollectionCapability()
    for action in ("list_collections", "search_collections"):
        arguments = {**ARGUMENTS[action], "sort_by": "rate"}
        page = await capability.execute(action, db=db, user_id=ids[0], **arguments)
        assert page["success"] is True
        assert page["total"] == len(page["collections"]) == 2
        assert [item["collection"]["rate"] for item in page["collections"]] == [9, 8]
        assert "user_id" not in json.dumps(page)
        assert "owned-comment-2" not in json.dumps(page)
        second = await capability.execute(
            action, db=db, user_id=ids[0], **arguments, skip=1, limit=1
        )
        assert second["total"] == len(second["collections"]) == 1
        assert second["collections"][0]["collection"]["source_id"] == "shared-anime"
        empty = await capability.execute(
            action, db=db, user_id=ids[0], **arguments, skip=20
        )
        assert empty["total"] == 0 and empty["collections"] == []
        filtered = await capability.execute(
            action, db=db, user_id=ids[0], **arguments, type=2, status=3
        )
        assert filtered["total"] == 1
        assert filtered["collections"][0]["subject"]["type"] == 2
        wrong_status = await capability.execute(
            action, db=db, user_id=ids[0], **arguments, status=1
        )
        assert wrong_status["total"] == 0
    for owner, comment in zip(ids, ("owned-comment-0", "owned-comment-2"), strict=True):
        owned = await capability.execute(
            "get_collection", db=db, user_id=owner, **ARGUMENTS["get_collection"]
        )
        assert owned["success"] is True
        assert owned["collection"]["collection"]["comment"] == comment
        assert "user_id" not in json.dumps(owned)
    foreign = await capability.execute(
        "get_collection",
        db=db,
        user_id=ids[0],
        source="bangumi",
        source_id="foreign-only",
    )
    assert foreign["success"] is False and foreign["error_type"] == "not_found"
    no_match = await capability.execute(
        "search_collections",
        db=db,
        user_id=ids[0],
        keyword="unmatched-synthetic-keyword",
    )
    assert no_match["total"] == 0 and no_match["collections"] == []


@pytest.mark.asyncio
async def test_owned_filters_sort_paging_and_private_records_sqlite(db_session):
    await _verify_owned_queries(db_session)


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_owned_filters_sort_paging_and_private_records_postgres(postgres_session):
    await _verify_owned_queries(postgres_session)


@pytest.mark.asyncio
async def test_search_applies_declared_subject_type_to_real_sql(db_session):
    ids = await _seed(db_session)
    result = await CollectionCapability().execute(
        "search_collections", db=db_session, user_id=ids[0], keyword="Shared", type=2
    )
    assert result["success"] is True
    assert [item["subject"]["type"] for item in result["collections"]] == [2]


@pytest.mark.parametrize("action", sorted(READ_ACTIONS))
def test_readonly_schema_rejects_unknown_write_parameters(action):
    descriptor = next(
        item for item in CollectionCapability().actions() if item.name == action
    )
    with pytest.raises(SchemaContractError):
        validate_input({**ARGUMENTS[action], "save": True}, descriptor)


@pytest.mark.parametrize("action", ["list_collections", "search_collections"])
@pytest.mark.parametrize(
    "parameter,value", [("type", 99), ("sort_by", "arbitrary-sql")]
)
def test_filter_and_sort_schema_rejects_unsupported_values(action, parameter, value):
    descriptor = next(
        item for item in CollectionCapability().actions() if item.name == action
    )
    with pytest.raises(SchemaContractError):
        validate_input({**ARGUMENTS[action], parameter: value}, descriptor)


@pytest.mark.asyncio
@pytest.mark.parametrize("action", sorted(READ_ACTIONS))
async def test_read_value_error_diagnostic_is_not_public(action, monkeypatch):
    dependency = {
        "list_collections": "get_user_collections",
        "get_collection": "get_collection",
        "search_collections": "search_collections",
    }[action]

    async def fail(*args):
        raise ValueError("synthetic-private-validation-diagnostic")

    monkeypatch.setattr(capability_module, dependency, fail)
    result = await CollectionCapability().execute(
        action, db=object(), user_id=7, **ARGUMENTS[action]
    )
    assert result["success"] is False and result["error_type"] == "invalid_args"
    assert "synthetic-private" not in json.dumps(result)


@pytest.mark.asyncio
@pytest.mark.parametrize("action", sorted(READ_ACTIONS))
async def test_real_read_sql_failure_is_safe_in_all_boundary_logs(
    action, db_session, monkeypatch, caplog
):
    async def fail(*args, **kwargs):
        raise SQLAlchemyError("synthetic-private-sql-diagnostic")

    monkeypatch.setattr(db_session, "execute", fail)
    loggers = (
        capability_module.logger,
        collection_service.logger,
        collection_repo.logger,
    )
    for logger in loggers:
        logger.addHandler(caplog.handler)
    try:
        with caplog.at_level(logging.ERROR):
            result = await CollectionCapability().execute(
                action, db=db_session, user_id=7, **ARGUMENTS[action]
            )
    finally:
        for logger in loggers:
            logger.removeHandler(caplog.handler)
    assert result["success"] is False and result["error_type"] == "internal"
    assert "synthetic-private" not in json.dumps(result)
    records = [
        record
        for record in caplog.records
        if record.name in {logger.name for logger in loggers}
    ]
    assert {record.name for record in records} == {logger.name for logger in loggers}
    assert all(
        "synthetic-private" not in repr(record.__dict__) and record.exc_info is None
        for record in records
    )


def test_read_success_output_is_validated_and_write_contracts_are_unchanged():
    from tests.capabilities.contracts.catalog import fingerprint
    from tests.capabilities.contracts.snapshots import FINGERPRINTS

    for descriptor in CollectionCapability().actions():
        if descriptor.is_side_effect:
            assert (
                fingerprint(descriptor)
                == FINGERPRINTS[
                    (descriptor.public_name or descriptor.name, descriptor.version)
                ]
            )
            continue
        assert descriptor.name in READ_ACTIONS
        result = ResultNormalizer().normalize(
            {"success": True},
            descriptor=descriptor,
            run_id="schema",
            decision_id="decision",
            invocation_id="invocation",
            trace_id="schema",
        )
        assert result.status == "failed", descriptor.name
