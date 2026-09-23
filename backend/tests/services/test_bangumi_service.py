from __future__ import annotations

import asyncio

import pytest

from app.schemas.bangumi import SubjectDetail
from app.services import bangumi_service


@pytest.mark.asyncio
async def test_get_bangumi_calendar_rejects_incomplete_weekday_data(monkeypatch):
    async def fake_calendar():
        return [{"weekday": {"id": 1}, "items": []}]

    monkeypatch.setattr(bangumi_service, "fetch_calendar", fake_calendar)

    with pytest.raises(ValueError, match="seven weekdays"):
        await bangumi_service.get_bangumi_calendar()


@pytest.mark.asyncio
async def test_get_bangumi_calendar_refreshes_incomplete_cached_data(monkeypatch):
    async def cached_calendar():
        return [{"weekday": {"id": 1}, "items": []}]

    async def uncached_calendar(_client):
        return [{"weekday": {"id": day_id}, "items": []} for day_id in range(1, 8)]

    cached_calendar.__wrapped__ = uncached_calendar
    monkeypatch.setattr(bangumi_service, "fetch_calendar", cached_calendar)

    result = await bangumi_service.get_bangumi_calendar()

    assert [day.weekday["id"] for day in result.root] == list(range(1, 8))


@pytest.mark.asyncio
async def test_get_bangumi_subject_details_deduplicates_ids_and_keeps_failures(monkeypatch):
    requested: list[int] = []

    async def fake_fetch(subject_id: int):
        requested.append(subject_id)
        if subject_id == 2:
            raise RuntimeError("provider failure")
        return SubjectDetail(id=subject_id, name=f"Anime {subject_id}", summary="summary")

    monkeypatch.setattr(bangumi_service, "fetch_subject_by_id", fake_fetch)

    result = await bangumi_service.get_bangumi_subject_details([1, 2, 1])

    assert set(requested) == {1, 2}
    assert [item["id"] for item in result["details"]] == [1]
    assert result["failed_subject_ids"] == [2]


@pytest.mark.asyncio
async def test_get_bangumi_subject_details_propagates_cancellation(monkeypatch):
    async def cancelled_fetch(_subject_id: int):
        raise asyncio.CancelledError()

    monkeypatch.setattr(bangumi_service, "fetch_subject_by_id", cancelled_fetch)

    with pytest.raises(asyncio.CancelledError):
        await bangumi_service.get_bangumi_subject_details([1])


@pytest.mark.asyncio
async def test_sync_subject_detail_does_not_clear_schedule_fields(monkeypatch):
    captured_updates = []

    async def fake_fetch_subject_detail(_subject_id: int):
        return {"id": 123, "name": "Anime", "type": 2}

    async def fake_batch_update(_db, subject_updates):
        captured_updates.append(subject_updates)

    async def fake_get_by_source(_db, _search_data):
        return None

    monkeypatch.setattr(
        bangumi_service,
        "fetch_subject_detail",
        fake_fetch_subject_detail,
    )
    monkeypatch.setattr("app.services.subject_service.batch_update_subjects", fake_batch_update)
    monkeypatch.setattr(
        "app.repositories.subject_repo.SubjectRepo.get_by_source",
        fake_get_by_source,
    )

    await bangumi_service.sync_subject_detail(123, db=None)

    update_data = captured_updates[0].items[0].model_dump(exclude_unset=True)
    assert "air_time" not in update_data
    assert "air_weekday" not in update_data
    assert "last_sync" not in update_data


@pytest.mark.asyncio
async def test_get_bangumi_subject_details_rejects_more_than_five_ids():
    with pytest.raises(ValueError, match="five"):
        await bangumi_service.get_bangumi_subject_details([1, 2, 3, 4, 5, 6])
