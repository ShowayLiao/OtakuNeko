"""Real SQL conflict coverage for schedule upsert ownership and rollback."""

from datetime import datetime
import json
from typing import Any

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import col, select

from app.models import AnimeBroadcastMetadata, Collection, Schedule, Subject
from app.models.enums import CollectionStatus, SubjectType, WatchType
from app.repositories.schedule_repo import ScheduleRepository
from app.services.schedule_service import ScheduleService
from tests.capabilities.test_schedule_write_semantics import dispatch, seed, snapshot

SERVICE_METHODS = {
    "upsert_schedule": "upsert_schedule",
    "bulk_upsert_schedules": "bulk_upsert_schedules",
}
REPOSITORY_METHODS = {
    "upsert_schedule": "upsert",
    "bulk_upsert_schedules": "batch_upsert",
}
CONFLICT_SOURCE_ID = "foreign-id-target"


@pytest.fixture(autouse=True)
def write_dialect(request, monkeypatch):
    if request.node.get_closest_marker("postgres"):
        from app.core.config import settings

        monkeypatch.setattr(settings, "DEPLOY_MODE", "cloud")


async def _seed_business_state(db: Any) -> tuple[Any, int, int]:
    user, owner_schedule_id, foreign_schedule_id = await seed(db)
    assert user.id is not None
    foreign_schedule = await db.get(Schedule, foreign_schedule_id)
    assert foreign_schedule is not None

    db.add(
        Subject(
            source="bangumi",
            source_id="801",
            type=SubjectType.ANIME,
            name="Baseline subject",
            summary="Baseline subject summary",
        )
    )
    db.add_all(
        [
            Collection(
                user_id=user.id,
                source="bangumi",
                source_id="801",
                type=CollectionStatus.WISH,
                comment="Owner collection remains unchanged",
                private=True,
            ),
            Collection(
                user_id=foreign_schedule.user_id,
                source="bangumi",
                source_id="801",
                type=CollectionStatus.COLLECT,
                comment="Foreign collection remains unchanged",
                private=True,
            ),
        ]
    )
    db.add(
        AnimeBroadcastMetadata(
            bangumi_id=801,
            title="Baseline metadata",
            broadcast_begin=datetime(2026, 10, 20, 12),
            year=2026,
            season=10,
        )
    )
    await db.commit()
    return user, owner_schedule_id, foreign_schedule_id


async def _business_snapshot(db: Any) -> dict[str, Any]:
    subject_rows = await db.execute(select(Subject).order_by(col(Subject.id)))
    collection_rows = await db.execute(select(Collection).order_by(col(Collection.id)))
    metadata_rows = await db.execute(
        select(AnimeBroadcastMetadata).order_by(col(AnimeBroadcastMetadata.bangumi_id))
    )
    return {
        "schedules": await snapshot(db),
        "subjects": [row.model_dump(mode="json") for row in subject_rows.scalars()],
        "collections": [
            row.model_dump(mode="json") for row in collection_rows.scalars()
        ],
        "metadata": [row.model_dump(mode="json") for row in metadata_rows.scalars()],
    }


def _track_write_paths(monkeypatch: Any, action: str) -> dict[str, int]:
    calls = {"service": 0, "repository": 0}
    service_name = SERVICE_METHODS[action]
    repository_name = REPOSITORY_METHODS[action]
    original_service = getattr(ScheduleService, service_name)
    original_repository = getattr(ScheduleRepository, repository_name)

    async def track_service(*args: Any, **kwargs: Any) -> Any:
        calls["service"] += 1
        return await original_service(*args, **kwargs)

    async def track_repository(*args: Any, **kwargs: Any) -> Any:
        calls["repository"] += 1
        return await original_repository(*args, **kwargs)

    monkeypatch.setattr(ScheduleService, service_name, track_service)
    monkeypatch.setattr(ScheduleRepository, repository_name, track_repository)
    return calls


def _record(source_id: str, *, schedule_id: int | None = None) -> dict[str, Any]:
    record: dict[str, Any] = {
        "source": "bangumi",
        "source_id": source_id,
        "day_of_week": 4,
        "start_time": "22:15:00",
        "watch_type": int(WatchType.LEISURE),
    }
    if schedule_id is not None:
        record["id"] = schedule_id
    return record


def _collision_payload(action: str, foreign_schedule_id: int, new_schedule_id: int):
    if action == "upsert_schedule":
        return _record(CONFLICT_SOURCE_ID, schedule_id=foreign_schedule_id)
    return {
        "items": [
            _record("bulk-first", schedule_id=new_schedule_id),
            _record("bulk-foreign-id", schedule_id=foreign_schedule_id),
        ]
    }


def _valid_payload(action: str) -> dict[str, Any]:
    if action == "upsert_schedule":
        return _record("recovery-upsert")
    return {"items": [_record("recovery-bulk")]}


def _assert_normalized_safe_failure(result: Any) -> None:
    assert result.status == "failed", result.model_dump()
    assert result.error_code == "internal", result.model_dump()
    serialized = json.dumps(result.model_dump(mode="json"), allow_nan=False)
    for database_detail in (
        "UNIQUE constraint failed",
        "duplicate key value violates unique constraint",
        "schedules_pkey",
        "IntegrityError",
    ):
        assert database_detail not in serialized


async def _run_foreign_id_collision(db: Any, action: str, monkeypatch: Any) -> None:
    user, _, foreign_schedule_id = await _seed_business_state(db)
    session_factory = async_sessionmaker(db.bind, expire_on_commit=False)

    async with session_factory() as reader:
        before = await _business_snapshot(reader)
    foreign_before = next(
        row for row in before["schedules"] if row["id"] == foreign_schedule_id
    )
    max_schedule_id = max(row["id"] for row in before["schedules"])
    values = _collision_payload(action, foreign_schedule_id, max_schedule_id + 100)
    calls = _track_write_paths(monkeypatch, action)

    async with session_factory() as write_session:
        failed = await dispatch(
            write_session, user, action, f"{action}-foreign-id", values
        )
        # The actual IntegrityError must leave this same Session usable.
        assert await _business_snapshot(write_session) == before
    _assert_normalized_safe_failure(failed)
    assert calls == {"service": 1, "repository": 1}

    async with session_factory() as reader:
        after_failure = await _business_snapshot(reader)
    assert after_failure == before
    assert (
        next(
            row
            for row in after_failure["schedules"]
            if row["id"] == foreign_schedule_id
        )
        == foreign_before
    )

    async with session_factory() as retry_session:
        replay = await dispatch(
            retry_session, user, action, f"{action}-foreign-id", values
        )
    _assert_normalized_safe_failure(replay)
    assert calls == {"service": 1, "repository": 1}
    async with session_factory() as reader:
        assert await _business_snapshot(reader) == before

    async with session_factory() as recovery_session:
        recovered = await dispatch(
            recovery_session,
            user,
            action,
            f"{action}-valid-recovery",
            _valid_payload(action),
        )
    assert recovered.status == "succeeded", recovered.model_dump()
    assert calls == {"service": 2, "repository": 2}
    async with session_factory() as reader:
        after_recovery = await _business_snapshot(reader)
    assert after_recovery["subjects"] == before["subjects"]
    assert after_recovery["collections"] == before["collections"]
    assert after_recovery["metadata"] == before["metadata"]
    assert len(after_recovery["schedules"]) == len(before["schedules"]) + 1
    assert (
        next(
            row
            for row in after_recovery["schedules"]
            if row["id"] == foreign_schedule_id
        )
        == foreign_before
    )
    assert any(
        row["user_id"] == user.id
        and row["source_id"]
        == ("recovery-upsert" if action == "upsert_schedule" else "recovery-bulk")
        for row in after_recovery["schedules"]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("action", ("upsert_schedule", "bulk_upsert_schedules"))
async def test_sqlite_foreign_schedule_id_collision_is_safe_and_atomic(
    db_session, monkeypatch, action
):
    await _run_foreign_id_collision(db_session, action, monkeypatch)


@pytest.mark.asyncio
@pytest.mark.postgres
@pytest.mark.parametrize("action", ("upsert_schedule", "bulk_upsert_schedules"))
async def test_postgres_foreign_schedule_id_collision_is_safe_and_atomic(
    postgres_session, monkeypatch, action
):
    await _run_foreign_id_collision(postgres_session, action, monkeypatch)


async def _run_owner_unique_key_upsert(db: Any, monkeypatch: Any) -> None:
    user, owner_schedule_id, foreign_schedule_id = await _seed_business_state(db)
    session_factory = async_sessionmaker(db.bind, expire_on_commit=False)
    calls = _track_write_paths(monkeypatch, "upsert_schedule")

    async with session_factory() as reader:
        before = await _business_snapshot(reader)
    owner_before = next(
        row for row in before["schedules"] if row["id"] == owner_schedule_id
    )
    foreign_before = next(
        row for row in before["schedules"] if row["id"] == foreign_schedule_id
    )
    values = {
        "source": "bangumi",
        "source_id": "701",
        "day_of_week": 5,
        "start_time": "23:00:00",
        "watch_type": int(WatchType.NEW),
    }

    async with session_factory() as write_session:
        result = await dispatch(
            write_session, user, "upsert_schedule", "owner-unique-key", values
        )
    assert result.status == "succeeded", result.model_dump()
    assert calls == {"service": 1, "repository": 1}

    async with session_factory() as reader:
        after = await _business_snapshot(reader)
    assert len(after["schedules"]) == len(before["schedules"])
    assert after["subjects"] == before["subjects"]
    assert after["collections"] == before["collections"]
    assert after["metadata"] == before["metadata"]
    owner_after = next(
        row for row in after["schedules"] if row["id"] == owner_schedule_id
    )
    assert owner_after["day_of_week"] == 5
    assert owner_after["start_time"] == "23:00:00"
    assert owner_after != owner_before
    assert (
        next(row for row in after["schedules"] if row["id"] == foreign_schedule_id)
        == foreign_before
    )


@pytest.mark.asyncio
async def test_sqlite_owner_unique_key_conflict_updates_only_owner(
    db_session, monkeypatch
):
    await _run_owner_unique_key_upsert(db_session, monkeypatch)


@pytest.mark.asyncio
@pytest.mark.postgres
async def test_postgres_owner_unique_key_conflict_updates_only_owner(
    postgres_session, monkeypatch
):
    await _run_owner_unique_key_upsert(postgres_session, monkeypatch)
