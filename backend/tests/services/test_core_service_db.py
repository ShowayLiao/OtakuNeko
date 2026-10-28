from datetime import datetime, time, timezone

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.models import Collection, Schedule, Subject, User
from app.models.enums import CollectionStatus, SubjectType, WatchType
from app.schemas.collection import (
    CollectionCreate,
    CollectionSearchBase,
    CollectionSearchByID,
    CollectionUpdate,
    CollectionUpsert,
    CollectionUpsertList,
)
from app.schemas.schedule import ScheduleCreate, ScheduleUpdate, ScheduleUpsert
from app.services import collection_service
from app.services.schedule_service import ScheduleService


async def _create_user(db_session: AsyncSession, username: str) -> int:
    user = User(username=username)
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    assert user.id is not None
    return user.id


async def _create_subject(
    db_session: AsyncSession, source_id: str = "subject-1"
) -> Subject:
    subject = Subject(
        source="bangumi",
        source_id=source_id,
        type=SubjectType.ANIME,
        name=f"Subject {source_id}",
        name_cn=f"中文 {source_id}",
        images={"large": "https://example.test/cover.jpg"},
        tags=[{"name": "drama"}],
        meta_tags=["TV"],
        infobox=[],
        rating={"score": 8.5},
        collection={},
    )
    db_session.add(subject)
    await db_session.commit()
    await db_session.refresh(subject)
    return subject


async def _create_collection(
    db_session: AsyncSession, user_id: int, source_id: str = "subject-1"
) -> Collection:
    collection = await collection_service.create_collection(
        db_session,
        CollectionCreate(
            user_id=user_id,
            source="bangumi",
            source_id=source_id,
            type=CollectionStatus.DO,
            rate=7,
            comment="initial comment",
            private=False,
            tags=["initial"],
            updated_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        ),
    )
    return collection


def _schedule_data(
    user_id: int,
    source_id: str = "schedule-1",
    *,
    day_of_week: int = 2,
    start_time: time = time(20, 30),
) -> ScheduleCreate:
    return ScheduleCreate(
        user_id=user_id,
        source="bangumi",
        source_id=source_id,
        day_of_week=day_of_week,
        start_time=start_time,
        watch_day=day_of_week,
        watch_time=time(21, 0),
        duration=1,
        watch_type=WatchType.NEW,
    )


@pytest.mark.db
async def test_collection_create_persists_fields(
    db_session: AsyncSession, initialized_cache
) -> None:
    user_id = await _create_user(db_session, "collection-create")
    await _create_subject(db_session)
    timestamp = datetime(2026, 2, 3, 4, 5, tzinfo=timezone.utc)

    result = await collection_service.create_collection(
        db_session,
        CollectionCreate(
            user_id=user_id,
            source="bangumi",
            source_id="subject-1",
            type=CollectionStatus.WISH,
            rate=8,
            comment="watch later",
            private=True,
            tags=["priority", "spring"],
            updated_at=timestamp,
        ),
    )

    assert result.id is not None
    persisted = await db_session.get(Collection, result.id)
    assert result.user_id == user_id
    assert persisted is not None
    assert persisted.source_id == "subject-1"
    assert persisted.type == CollectionStatus.WISH
    assert persisted.rate == 8
    assert persisted.comment == "watch later"
    assert persisted.private is True
    assert persisted.tags == ["priority", "spring"]
    assert persisted.updated_at == timestamp.replace(tzinfo=None)


@pytest.mark.db
async def test_collection_get_returns_unified_json_serializable_row(
    db_session: AsyncSession, initialized_cache
) -> None:
    user_id = await _create_user(db_session, "collection-get")
    await _create_subject(db_session)
    created = await _create_collection(db_session, user_id)

    result = await collection_service.get_collection(
        db_session,
        CollectionSearchByID(user_id=user_id, source="bangumi", source_id="subject-1"),
    )

    assert result is not None
    assert result.collection is not None
    assert result.subject is not None
    assert result.collection.source_id == created.source_id
    assert result.collection.user_id == user_id
    assert result.subject.name == "Subject subject-1"
    serialized = result.model_dump(mode="json")
    assert serialized["collection"]["source_id"] == "subject-1"
    assert serialized["subject"]["name"] == "Subject subject-1"


@pytest.mark.db
async def test_collection_get_returns_none_when_record_is_missing(
    db_session: AsyncSession,
) -> None:
    user_id = await _create_user(db_session, "collection-get-empty")

    result = await collection_service.get_collection(
        db_session,
        CollectionSearchByID(user_id=user_id, source="bangumi", source_id="missing"),
    )

    assert result is None


@pytest.mark.db
async def test_collection_read_update_delete_reject_other_user(
    db_session: AsyncSession, initialized_cache
) -> None:
    owner_id = await _create_user(db_session, "collection-access-owner")
    other_user_id = await _create_user(db_session, "collection-access-other")
    await _create_subject(db_session)
    created = await _create_collection(db_session, owner_id)
    search = CollectionSearchByID(
        user_id=other_user_id, source="bangumi", source_id="subject-1"
    )

    found = await collection_service.get_collection(db_session, search)
    updated = await collection_service.update_collection(
        db_session,
        CollectionUpdate.model_validate(
            {
                "user_id": other_user_id,
                "source": "bangumi",
                "source_id": "subject-1",
                "type": CollectionStatus.DROPPED,
                "rate": 1,
                "comment": "unauthorized update",
            }
        ),
    )
    deleted = await collection_service.delete_collection(db_session, search)

    await db_session.refresh(created)
    assert found is None
    assert updated is None
    assert deleted is False
    assert created.user_id == owner_id
    assert created.type == CollectionStatus.DO
    assert created.rate == 7
    assert created.comment == "initial comment"
    assert created.tags == ["initial"]


@pytest.mark.db
async def test_collection_update_persists_changes(
    db_session: AsyncSession, initialized_cache
) -> None:
    user_id = await _create_user(db_session, "collection-update")
    await _create_subject(db_session)
    original = await _create_collection(db_session, user_id)

    result = await collection_service.update_collection(
        db_session,
        CollectionUpdate.model_validate(
            {
                "user_id": user_id,
                "source": "bangumi",
                "source_id": "subject-1",
                "type": CollectionStatus.DROPPED,
                "rate": 3,
                "comment": "stopped watching",
                "tags": ["paused"],
            }
        ),
    )

    assert original.id is not None
    persisted = await db_session.get(Collection, original.id)
    assert result is not None
    assert result.id == original.id
    assert result.type == CollectionStatus.DROPPED
    assert result.rate == 3
    assert result.comment == "stopped watching"
    assert result.tags == ["paused"]
    assert persisted is not None
    assert persisted.type == CollectionStatus.DROPPED
    assert persisted.updated_at is not None


@pytest.mark.db
async def test_collection_update_returns_none_when_record_is_missing(
    db_session: AsyncSession,
) -> None:
    user_id = await _create_user(db_session, "collection-update-empty")

    result = await collection_service.update_collection(
        db_session,
        CollectionUpdate.model_validate(
            {
                "user_id": user_id,
                "source": "bangumi",
                "source_id": "missing",
                "type": CollectionStatus.DO,
            }
        ),
    )

    assert result is None


@pytest.mark.db
async def test_collection_delete_removes_owned_row(
    db_session: AsyncSession, initialized_cache
) -> None:
    user_id = await _create_user(db_session, "collection-delete")
    await _create_subject(db_session)
    created = await _create_collection(db_session, user_id)

    deleted = await collection_service.delete_collection(
        db_session,
        CollectionSearchByID(user_id=user_id, source="bangumi", source_id="subject-1"),
    )

    assert deleted is True
    assert created.id is not None
    assert await db_session.get(Collection, created.id) is None


@pytest.mark.db
async def test_collection_delete_returns_false_when_record_is_missing(
    db_session: AsyncSession,
) -> None:
    user_id = await _create_user(db_session, "collection-delete-empty")

    deleted = await collection_service.delete_collection(
        db_session,
        CollectionSearchByID(user_id=user_id, source="bangumi", source_id="missing"),
    )

    assert deleted is False


@pytest.mark.db
async def test_collection_list_is_user_scoped_and_json_serializable(
    db_session: AsyncSession, initialized_cache
) -> None:
    user_id = await _create_user(db_session, "collection-list-owner")
    other_user_id = await _create_user(db_session, "collection-list-other")
    await _create_subject(db_session)
    await _create_collection(db_session, user_id)
    await _create_collection(db_session, other_user_id)

    result = await collection_service.get_user_collections(
        db_session,
        CollectionSearchBase.model_validate({"user_id": user_id, "limit": 10}),
    )

    assert result.total == 1
    assert len(result.items) == 1
    assert result.items[0].collection is not None
    assert result.items[0].collection.user_id == user_id
    serialized = result.model_dump(mode="json")
    assert serialized["total"] == 1
    assert serialized["items"][0]["collection"]["user_id"] == user_id


@pytest.mark.db
async def test_collection_list_returns_empty_result(
    db_session: AsyncSession,
) -> None:
    user_id = await _create_user(db_session, "collection-list-empty")

    result = await collection_service.get_user_collections(
        db_session,
        CollectionSearchBase.model_validate({"user_id": user_id}),
    )

    assert result.total == 0
    assert result.items == []


@pytest.mark.db
async def test_collection_services_reject_missing_user_id(
    db_session: AsyncSession,
) -> None:
    missing_user_search = CollectionSearchBase.model_construct(
        user_id=None, skip=0, limit=10, type=None, status=None
    )
    with pytest.raises(ValueError, match="user_id is required to list collections"):
        await collection_service.get_user_collections(db_session, missing_user_search)

    with pytest.raises(ValueError, match="user_id, source and source_id are required"):
        await collection_service.update_collection(
            db_session,
            CollectionUpdate.model_validate(
                {"source": "bangumi", "source_id": "subject-1"}
            ),
        )


@pytest.mark.db
async def test_collection_upsert_uses_trusted_user_id(
    db_session: AsyncSession, initialized_cache
) -> None:
    user_id = await _create_user(db_session, "collection-upsert-owner")
    await _create_user(db_session, "collection-upsert-untrusted")
    await _create_subject(db_session)

    result = await collection_service.upsert_collection(
        db_session,
        user_id,
        data={
            "collection": {
                "user_id": user_id + 1,
                "source": "bangumi",
                "source_id": "subject-1",
                "type": CollectionStatus.DO,
                "rate": 9,
                "comment": "trusted principal wins",
            }
        },
    )

    persisted = await db_session.exec(
        select(Collection).where(Collection.source_id == "subject-1")
    )
    rows = persisted.all()
    assert result.collection is not None
    assert result.collection.user_id == user_id
    assert [(row.user_id, row.rate, row.comment) for row in rows] == [
        (user_id, 9, "trusted principal wins")
    ]


@pytest.mark.db
async def test_collection_batch_upsert_uses_trusted_user_id(
    db_session: AsyncSession, initialized_cache
) -> None:
    user_id = await _create_user(db_session, "collection-batch-owner")
    await _create_user(db_session, "collection-batch-untrusted")

    count = await collection_service.batch_upsert_collections(
        db_session,
        CollectionUpsertList(
            total=1,
            collections=[
                CollectionUpsert.model_validate(
                    {
                        "user_id": user_id + 1,
                        "source": "bangumi",
                        "source_id": "batch-subject",
                        "type": CollectionStatus.WISH,
                        "rate": 6,
                    }
                )
            ],
        ),
        user_id=user_id,
    )

    persisted = await db_session.exec(
        select(Collection).where(Collection.source_id == "batch-subject")
    )
    row = persisted.one()
    assert count == 1
    assert row.user_id == user_id
    assert row.type == CollectionStatus.WISH
    assert row.rate == 6


@pytest.mark.db
async def test_collection_empty_batch_upsert_returns_zero_without_writes(
    db_session: AsyncSession, initialized_cache
) -> None:
    user_id = await _create_user(db_session, "collection-empty-batch")

    count = await collection_service.batch_upsert_collections(
        db_session,
        CollectionUpsertList(total=0, collections=[]),
        user_id=user_id,
    )
    persisted = await db_session.exec(select(Collection))

    assert count == 0
    assert persisted.all() == []


@pytest.mark.db
async def test_schedule_create_and_read_use_trusted_user_id(
    db_session: AsyncSession,
) -> None:
    user_id = await _create_user(db_session, "schedule-create-owner")
    await _create_user(db_session, "schedule-create-untrusted")

    created = await ScheduleService.create_schedule(
        db_session, user_id, _schedule_data(user_id + 1)
    )
    assert created is not None
    assert created.id is not None
    schedules = await ScheduleService.get_user_schedules(db_session, user_id)
    serialized = (
        await ScheduleService.get_unified_user_schedules(db_session, user_id)
    ).model_dump(mode="json")

    assert created.user_id == user_id
    assert created.source_id == "schedule-1"
    assert len(schedules) == 1
    assert schedules[0].id == created.id
    assert serialized["total"] == 1
    assert serialized["items"][0]["schedule"]["user_id"] == user_id
    assert serialized["items"][0]["subject"] is None


@pytest.mark.db
async def test_schedule_read_returns_empty_results(db_session: AsyncSession) -> None:
    user_id = await _create_user(db_session, "schedule-list-empty")

    schedules = await ScheduleService.get_user_schedules(db_session, user_id)
    unified = await ScheduleService.get_unified_user_schedules(db_session, user_id)

    assert schedules == []
    assert unified.total == 0
    assert unified.items == []


@pytest.mark.db
async def test_schedule_update_persists_changes(db_session: AsyncSession) -> None:
    user_id = await _create_user(db_session, "schedule-update")
    created = await ScheduleService.create_schedule(
        db_session, user_id, _schedule_data(user_id)
    )
    assert created is not None
    assert created.id is not None

    updated = await ScheduleService.update_schedule(
        db_session,
        created.id,
        user_id,
        ScheduleUpdate.model_validate(
            {
                "day_of_week": 4,
                "start_time": time(22, 15),
                "watch_day": 5,
                "watch_time": time(23, 0),
                "duration": 2,
            }
        ),
    )

    persisted = await db_session.get(Schedule, created.id)
    assert updated is not None
    assert updated.day_of_week == 4
    assert updated.start_time == time(22, 15)
    assert updated.duration == 2
    assert persisted is not None
    assert persisted.watch_day == 5
    assert persisted.watch_time == time(23, 0)


@pytest.mark.db
async def test_schedule_delete_removes_owned_row(db_session: AsyncSession) -> None:
    user_id = await _create_user(db_session, "schedule-delete")
    created = await ScheduleService.create_schedule(
        db_session, user_id, _schedule_data(user_id)
    )
    assert created is not None
    assert created.id is not None

    deleted = await ScheduleService.delete_schedule(db_session, created.id, user_id)

    assert deleted is True
    assert await db_session.get(Schedule, created.id) is None


@pytest.mark.db
async def test_schedule_delete_returns_false_when_missing(
    db_session: AsyncSession,
) -> None:
    user_id = await _create_user(db_session, "schedule-delete-empty")

    deleted = await ScheduleService.delete_schedule(db_session, 9999, user_id)

    assert deleted is False


@pytest.mark.db
async def test_schedule_cross_user_update_is_rejected_without_mutation(
    db_session: AsyncSession,
) -> None:
    owner_id = await _create_user(db_session, "schedule-update-owner")
    other_user_id = await _create_user(db_session, "schedule-update-other")
    created = await ScheduleService.create_schedule(
        db_session, owner_id, _schedule_data(owner_id)
    )
    assert created is not None
    assert created.id is not None

    updated = await ScheduleService.update_schedule(
        db_session,
        created.id,
        other_user_id,
        ScheduleUpdate.model_validate(
            {"source_id": "attacker-controlled", "duration": 99}
        ),
    )

    await db_session.refresh(created)
    assert updated is None
    assert created.user_id == owner_id
    assert created.source_id == "schedule-1"
    assert created.duration == 1


@pytest.mark.db
async def test_schedule_cross_user_delete_is_rejected_and_preserves_row(
    db_session: AsyncSession,
) -> None:
    owner_id = await _create_user(db_session, "schedule-delete-owner")
    other_user_id = await _create_user(db_session, "schedule-delete-other")
    created = await ScheduleService.create_schedule(
        db_session, owner_id, _schedule_data(owner_id)
    )
    assert created is not None
    assert created.id is not None

    deleted = await ScheduleService.delete_schedule(
        db_session, created.id, other_user_id
    )

    persisted = await db_session.get(Schedule, created.id)
    assert deleted is False
    assert persisted is not None
    assert persisted.user_id == owner_id
    assert persisted.source_id == "schedule-1"


@pytest.mark.db
async def test_schedule_upsert_rejects_mismatched_user_without_writes(
    db_session: AsyncSession,
) -> None:
    user_id = await _create_user(db_session, "schedule-upsert-owner")
    await _create_user(db_session, "schedule-upsert-untrusted")

    result = await ScheduleService.upsert_schedule(
        db_session,
        user_id,
        ScheduleUpsert.model_validate(
            {
                "user_id": user_id + 1,
                "source": "bangumi",
                "source_id": "mismatched",
                "day_of_week": 3,
                "start_time": time(19, 0),
                "watch_type": WatchType.NEW,
            }
        ),
    )

    persisted = await db_session.exec(select(Schedule))
    assert result is None
    assert persisted.all() == []


@pytest.mark.db
async def test_schedule_create_returns_existing_row_for_duplicate_time(
    db_session: AsyncSession,
) -> None:
    user_id = await _create_user(db_session, "schedule-duplicate-time")
    first = await ScheduleService.create_schedule(
        db_session, user_id, _schedule_data(user_id, "first")
    )
    assert first is not None
    assert first.id is not None

    duplicate = await ScheduleService.create_schedule(
        db_session, user_id, _schedule_data(user_id, "second")
    )
    assert duplicate is not None
    assert duplicate.id is not None
    rows = await ScheduleService.get_user_schedules(db_session, user_id)

    assert duplicate.id == first.id
    assert duplicate.source_id == "first"
    assert len(rows) == 1
