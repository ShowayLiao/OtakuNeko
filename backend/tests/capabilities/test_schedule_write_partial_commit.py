"""Real SQL regression for a metadata commit before schedule subject failure."""

from typing import Any

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import col, select

from app.models import AnimeBroadcastMetadata, Collection, Schedule, Subject
from app.models.enums import CollectionStatus
from app.services import schedule_service
from tests.capabilities.schedule_write_fixtures import (
    calendar_payload,
    metadata_payload,
)
from tests.capabilities.test_schedule_write_semantics import dispatch, seed

SOURCE_ID = 799
IDEMPOTENCY_KEY = "schedule-partial-commit"


@pytest.fixture(autouse=True)
def write_dialect(request, monkeypatch):
    if request.node.get_closest_marker("postgres"):
        from app.core.config import settings

        monkeypatch.setattr(settings, "DEPLOY_MODE", "cloud")


async def _snapshot(db: Any) -> dict[str, list[dict[str, Any]]]:
    schedule_rows = await db.execute(select(Schedule).order_by(col(Schedule.id)))
    subject_rows = await db.execute(select(Subject).order_by(col(Subject.id)))
    collection_rows = await db.execute(select(Collection).order_by(col(Collection.id)))
    metadata_rows = await db.execute(
        select(AnimeBroadcastMetadata).order_by(col(AnimeBroadcastMetadata.bangumi_id))
    )
    return {
        "schedules": [row.model_dump(mode="json") for row in schedule_rows.scalars()],
        "subjects": [row.model_dump(mode="json") for row in subject_rows.scalars()],
        "collections": [
            row.model_dump(mode="json") for row in collection_rows.scalars()
        ],
        "metadata": [row.model_dump(mode="json") for row in metadata_rows.scalars()],
    }


async def _run_partial_commit_regression(
    db: Any, external_http: Any, cache_backend: Any, monkeypatch: Any
) -> None:
    from app.services.bangumi_client import BangumiClient
    from app.services.bangumi_data_sync import BangumiDataSyncService

    user, _, _ = await seed(db)
    assert user.id is not None
    db.add(
        Collection(
            user_id=user.id,
            source="bangumi",
            source_id=str(SOURCE_ID),
            type=CollectionStatus.COLLECT,
            comment="preserve while schedule sync fails",
            private=True,
        )
    )
    await db.commit()

    external_http.respond(
        "GET", BangumiClient.CALENDAR_URL, json=calendar_payload(SOURCE_ID)
    )
    external_http.respond(
        "GET",
        BangumiDataSyncService.DATA_SOURCES[0],
        json=metadata_payload(SOURCE_ID),
    )
    before = await _snapshot(db)
    assert before["metadata"] == []
    assert str(SOURCE_ID) not in {row["source_id"] for row in before["subjects"]}

    real_batch_upsert = schedule_service.batch_upsert_subjects
    batch_upsert_calls = 0
    fault_enabled = True

    async def fail_before_subject_commit(*args: Any, **kwargs: Any) -> Any:
        nonlocal batch_upsert_calls
        batch_upsert_calls += 1
        if fault_enabled:
            raise RuntimeError("synthetic pre-subject-commit fault")
        return await real_batch_upsert(*args, **kwargs)

    monkeypatch.setattr(
        schedule_service, "batch_upsert_subjects", fail_before_subject_commit
    )
    session_factory = async_sessionmaker(db.bind, expire_on_commit=False)

    async with session_factory() as first_session:
        failed = await dispatch(
            first_session, user, "sync_bangumi_schedule", IDEMPOTENCY_KEY, {}
        )
    assert failed.error_code == "attention_required", failed.model_dump()
    assert batch_upsert_calls == 1
    assert len(external_http.requests) == 2

    async with session_factory() as reader:
        after_failure = await _snapshot(reader)
    assert len(after_failure["metadata"]) == 1
    assert after_failure["metadata"][0]["bangumi_id"] == SOURCE_ID
    assert after_failure["schedules"] == before["schedules"]
    assert after_failure["subjects"] == before["subjects"]
    assert after_failure["collections"] == before["collections"]

    # Clear the calendar cache so a duplicate operation would have to hit HTTP.
    await cache_backend.clear()
    async with session_factory() as retry_session:
        retry = await dispatch(
            retry_session, user, "sync_bangumi_schedule", IDEMPOTENCY_KEY, {}
        )
    assert retry.error_code == "attention_required", retry.model_dump()
    assert batch_upsert_calls == 1
    assert len(external_http.requests) == 2
    async with session_factory() as reader:
        after_retry = await _snapshot(reader)
    assert after_retry == after_failure

    fault_enabled = False
    external_http.respond(
        "GET", BangumiClient.CALENDAR_URL, json=calendar_payload(SOURCE_ID)
    )
    async with session_factory() as recovery_session:
        recovered = await dispatch(
            recovery_session,
            user,
            "sync_bangumi_schedule",
            "schedule-partial-commit-recovery",
            {},
        )
    assert recovered.status == "succeeded", recovered.model_dump()
    assert batch_upsert_calls == 2
    assert len(external_http.requests) == 3

    async with session_factory() as reader:
        after_recovery = await _snapshot(reader)
    assert after_recovery["metadata"] == after_failure["metadata"]
    assert after_recovery["schedules"] == before["schedules"]
    assert after_recovery["collections"] == before["collections"]
    assert str(SOURCE_ID) in {row["source_id"] for row in after_recovery["subjects"]}


@pytest.mark.asyncio
async def test_sqlite_metadata_partial_commit_is_attention_required(
    db_session, external_http, initialized_cache, monkeypatch
):
    await _run_partial_commit_regression(
        db_session, external_http, initialized_cache, monkeypatch
    )


@pytest.mark.asyncio
@pytest.mark.postgres
async def test_postgres_metadata_partial_commit_is_attention_required(
    postgres_session, external_http, initialized_cache, monkeypatch
):
    await _run_partial_commit_regression(
        postgres_session, external_http, initialized_cache, monkeypatch
    )
