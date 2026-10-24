"""Actual fastapi-cache argument envelopes and owner-scoped cache hits."""

from __future__ import annotations

import pytest
import json
from sqlalchemy import event

from app.models import Collection, CollectionStatus, Subject, SubjectType, User
from app.schemas.dashboard import DashboardStats
from app.services.stats_service import get_user_stats, stats_key_builder


@pytest.mark.parametrize("style", ["positional", "keyword"])
def test_decorator_envelope_builds_distinct_trusted_owner_keys(style):
    keys = []
    for owner in (101, 202):
        args = (owner, object()) if style == "positional" else ()
        kwargs = {} if style == "positional" else {"user_id": owner, "db": object()}
        keys.append(
            stats_key_builder(
                None, "dashboard", request=None, response=None, args=args, kwargs=kwargs
            )
        )
    assert keys == ["dashboard:stats:101", "dashboard:stats:202"]


@pytest.mark.parametrize("owner", [None, 0, -1, True, "101"])
def test_cache_key_requires_valid_trusted_owner(owner):
    with pytest.raises(ValueError, match="trusted user"):
        stats_key_builder(
            None, "dashboard", request=None, args=(owner, object()), kwargs={}
        )


def test_legacy_direct_key_builder_calls_remain_user_scoped():
    assert (
        stats_key_builder(None, "dashboard", None, 101, object())
        == "dashboard:stats:101"
    )
    assert (
        stats_key_builder(None, "dashboard", None, user_id=202, db=object())
        == "dashboard:stats:202"
    )


@pytest.mark.asyncio
async def test_real_decorated_cache_is_owner_scoped_and_hits_without_sql(
    db_session, sqlite_engine, initialized_cache
):
    users = [User(username="cache-owner-a"), User(username="cache-owner-b")]
    db_session.add_all(users)
    await db_session.commit()
    user_ids = [user.id for user in users if user.id is not None]
    assert len(user_ids) == 2
    await initialized_cache.set(
        "dashboard:stats:None", json.dumps({"total": 999}).encode(), expire=600
    )
    for index, owner in enumerate(users):
        for number in range(index + 1):
            source_id = f"synthetic-cache-{index}-{number}"
            db_session.add(
                Subject(source_id=source_id, name=source_id, type=SubjectType.ANIME)
            )
            db_session.add(
                Collection(
                    user_id=user_ids[index],
                    source_id=source_id,
                    type=CollectionStatus.COLLECT,
                )
            )
    await db_session.commit()
    reads = []

    def collect(connection, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            reads.append(statement)

    event.listen(sqlite_engine.sync_engine, "before_cursor_execute", collect)
    try:
        first = DashboardStats.model_validate(
            await get_user_stats(user_ids[0], db_session)
        )
        assert first.total == 1 and len(reads) == 1
        hot = DashboardStats.model_validate(
            await get_user_stats(user_id=user_ids[0], db=db_session)
        )
        assert hot == first and len(reads) == 1
        second = DashboardStats.model_validate(
            await get_user_stats(user_id=user_ids[1], db=db_session)
        )
        assert second.total == 2 and len(reads) == 2
        second_hot = DashboardStats.model_validate(
            await get_user_stats(user_ids[1], db_session)
        )
        assert second_hot == second and len(reads) == 2
    finally:
        event.remove(sqlite_engine.sync_engine, "before_cursor_execute", collect)
