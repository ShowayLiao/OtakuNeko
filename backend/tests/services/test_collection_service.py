from __future__ import annotations

from typing import Any

import pytest

from app.repositories.collection_repo import CollectionRepo
from app.repositories.subject_repo import SubjectRepo
from app.schemas.adaptersV2 import UnifiedCollectionSubject
from app.schemas.collection import (
    CollectionBase,
    CollectionList,
    CollectionSearchByID,
    CollectionUpdate,
    CollectionUpsertRequest,
)
from app.services import collection_service


@pytest.mark.asyncio
async def test_upsert_ignores_body_user_id_and_injects_trusted_principal(monkeypatch) -> None:
    captured: list[Any] = []

    async def fake_subject(*args: Any, **kwargs: Any):
        return None

    async def fake_batch(_db: Any, payload: Any) -> None:
        captured.append(payload)

    async def fake_get(_db: Any, _search: CollectionSearchByID):
        return (object(), None)

    monkeypatch.setattr(SubjectRepo, "get_by_source", fake_subject)
    monkeypatch.setattr(CollectionRepo, "batch_upsert", fake_batch)
    monkeypatch.setattr(CollectionRepo, "get_by_user_and_subject", fake_get)
    monkeypatch.setattr(
        collection_service,
        "collection_with_subject_to_unified",
        lambda _result: UnifiedCollectionSubject(
            source="bangumi", source_id="100", type=2, user_id=7
        ),
    )
    monkeypatch.setattr(
        collection_service,
        "clear_collection_cache",
        lambda _user_id: {"status": "cleared"},
    )

    request = CollectionUpsertRequest(
        collection=CollectionUpdate(
            source="bangumi",
            source_id="100",
            type=2,
            user_id=999,
        )
    )

    await collection_service.upsert_collection(object(), 7, data=request)

    assert len(captured) == 1
    item = captured[0].collections[0]
    assert item.user_id == 7


@pytest.mark.asyncio
async def test_cache_clear_failure_returns_structured_warning(monkeypatch) -> None:
    async def failing_clear(**kwargs: Any) -> None:
        raise RuntimeError("cache unavailable")

    monkeypatch.setattr(collection_service.FastAPICache, "clear", failing_clear)

    outcome = await collection_service.clear_collection_cache(7)

    assert outcome == {"status": "warning", "code": "cache_clear_failed"}


@pytest.mark.asyncio
async def test_batch_upsert_rolls_back_when_repository_fails(monkeypatch) -> None:
    class FakeSession:
        rollback_calls = 0

        async def rollback(self) -> None:
            self.rollback_calls += 1

    async def failing_batch(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("database write failed")

    monkeypatch.setattr(CollectionRepo, "batch_upsert", failing_batch)
    session = FakeSession()
    collections = CollectionList(
        total=1,
        items=[CollectionBase(type=2, source="bangumi", source_id="100")],
    )

    with pytest.raises(RuntimeError, match="database write failed"):
        await collection_service.batch_upsert_collections(session, collections, 7)

    assert session.rollback_calls == 1


@pytest.mark.asyncio
async def test_post_commit_cache_failure_is_not_reported_as_write_failure() -> None:
    async def failing_clear() -> None:
        raise RuntimeError("cache backend unavailable")

    assert await collection_service._repository_write(failing_clear) is None
