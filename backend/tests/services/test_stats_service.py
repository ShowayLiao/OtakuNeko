from __future__ import annotations

import pytest

from app.models import Collection, CollectionStatus, Subject, SubjectType, User
from app.services.stats_service import get_collection_statistics


@pytest.mark.asyncio
async def test_collection_statistics_aggregates_statuses_and_distinct_subject_tags(
    db_session,
):
    user = User(username="stats-user")
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)

    subjects = [
        Subject(
            source="bangumi",
            source_id="1",
            type=SubjectType.ANIME,
            name="Anime 1",
            meta_tags=["恋爱", "校园"],
        ),
        Subject(
            source="bangumi",
            source_id="2",
            type=SubjectType.ANIME,
            name="Anime 2",
            tags=[{"name": "恋爱"}, {"name": "科幻"}],
        ),
        Subject(
            source="bangumi",
            source_id="3",
            type=SubjectType.ANIME,
            name="Anime 3",
            meta_tags=["校园"],
        ),
    ]
    db_session.add_all(subjects)
    db_session.add_all(
        [
            Collection(
                user_id=user.id,
                source="bangumi",
                source_id="1",
                type=CollectionStatus.WISH,
                subject_type=SubjectType.ANIME,
            ),
            Collection(
                user_id=user.id,
                source="bangumi",
                source_id="2",
                type=CollectionStatus.COLLECT,
                subject_type=SubjectType.ANIME,
            ),
            Collection(
                user_id=user.id,
                source="bangumi",
                source_id="3",
                type=CollectionStatus.DO,
                subject_type=SubjectType.ANIME,
            ),
        ]
    )
    await db_session.commit()

    result = await get_collection_statistics(user.id, db_session)

    assert result.total == 3
    assert result.status_counts.model_dump() == {
        "wish": 1,
        "watched": 1,
        "watching": 1,
        "on_hold": 0,
        "dropped": 0,
    }
    assert [item.model_dump() for item in result.top_genres] == [
        {"name": "恋爱", "count": 2},
        {"name": "校园", "count": 2},
        {"name": "科幻", "count": 1},
    ]
    assert result.complete is True
    assert result.genre_complete is True


@pytest.mark.asyncio
async def test_collection_statistics_does_not_include_other_users_or_subject_types(
    db_session,
):
    user = User(username="stats-owner")
    other_user = User(username="stats-other")
    db_session.add_all([user, other_user])
    await db_session.commit()
    await db_session.refresh(user)
    await db_session.refresh(other_user)

    db_session.add_all(
        [
            Subject(
                source="bangumi",
                source_id="10",
                type=SubjectType.ANIME,
                name="Anime",
                meta_tags=["动画"],
            ),
            Subject(
                source="bangumi",
                source_id="11",
                type=SubjectType.BOOK,
                name="Book",
                meta_tags=["小说"],
            ),
        ]
    )
    db_session.add_all(
        [
            Collection(
                user_id=user.id,
                source="bangumi",
                source_id="10",
                type=CollectionStatus.WISH,
                subject_type=SubjectType.ANIME,
            ),
            Collection(
                user_id=user.id,
                source="bangumi",
                source_id="11",
                type=CollectionStatus.WISH,
                subject_type=SubjectType.BOOK,
            ),
            Collection(
                user_id=other_user.id,
                source="bangumi",
                source_id="10",
                type=CollectionStatus.COLLECT,
                subject_type=SubjectType.ANIME,
            ),
        ]
    )
    await db_session.commit()

    result = await get_collection_statistics(user.id, db_session)

    assert result.total == 1
    assert result.status_counts.wish == 1
    assert result.status_counts.watched == 0
    assert [item.name for item in result.top_genres] == ["动画"]
