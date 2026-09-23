from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.api.deps import get_current_user
from app.api.v1 import collections as collections_module
from app.api.v1.collections import router as collections_router
from app.harness.persistence.idempotency import InMemoryIdempotencyStore
from app.schemas.user import UserRead


def _user(user_id: int) -> UserRead:
    return UserRead(
        id=user_id,
        username=f"user-{user_id}",
        created_at=datetime.now(timezone.utc),
    )


def _collection(source_id: str = "100") -> dict[str, Any]:
    return {
        "user_id": 7,
        "source": "bangumi",
        "source_id": source_id,
        "type": 2,
        "rate": None,
        "comment": None,
        "private": False,
        "tags": [],
        "vol_status": 0,
        "ep_status": 0,
        "subject_type": 2,
        "updated_at": None,
        "subject": None,
    }


def _app(user_id: int = 7) -> FastAPI:
    app = FastAPI()
    app.include_router(collections_router, prefix="/v1")
    store = InMemoryIdempotencyStore()

    async def override_user() -> UserRead:
        return _user(user_id)

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[
        collections_module.get_collection_idempotency_store
    ] = lambda: store
    app.dependency_overrides[collections_module.get_session] = lambda: None
    return app


async def _post(
    app: FastAPI,
    payload: dict[str, Any],
    *,
    key: str | None = "collection-create-1",
) -> httpx.Response:
    headers = {"Idempotency-Key": key} if key is not None else {}
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.post(
            "/v1/collections/?sid=42",
            json=payload,
            headers=headers,
        )


def test_collection_scope_contains_principal_method_and_canonical_resource() -> None:
    from app.harness.persistence.collection_http import (
        canonical_collection_resource_key,
        collection_idempotency_scope,
        collection_payload_hash,
    )

    resource = canonical_collection_resource_key("BANGUMI", "001")
    assert resource == "collections/bangumi/001"
    assert canonical_collection_resource_key("bangumi", "a/b") == "collections/bangumi/a%2Fb"
    assert collection_idempotency_scope(7, "put", resource) == (
        "principal:7|method:PUT|resource:collections/bangumi/001"
    )
    assert collection_payload_hash({"user_id": 7, "type": 2}) == collection_payload_hash(
        {"user_id": 999, "type": 2}
    )


@pytest.mark.asyncio
async def test_claim_failure_never_calls_collection_operation() -> None:
    from app.harness.persistence.collection_http import CollectionHttpIdempotencyAdapter

    class FailingStore:
        async def execute_once(self, *args: Any, **kwargs: Any):
            raise RuntimeError("idempotency store unavailable")

    calls = 0

    async def operation() -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return {"status": "succeeded"}

    with pytest.raises(RuntimeError, match="idempotency store unavailable"):
        await CollectionHttpIdempotencyAdapter(FailingStore()).execute(
            principal_id=7,
            method="POST",
            resource_key="collections/batch",
            idempotency_key="claim-failure",
            payload={"items": []},
            operation=operation,
        )
    assert calls == 0


@pytest.mark.asyncio
async def test_missing_or_oversized_header_is_rejected_before_write(monkeypatch) -> None:
    calls = 0

    async def fake_upsert(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return _collection()

    monkeypatch.setattr(collections_module, "upsert_collection", fake_upsert)
    monkeypatch.setattr(
        collections_module,
        "clear_collection_cache",
        lambda _user_id: {"status": "cleared"},
    )
    app = _app()
    payload = {"collection": {"type": 2, "user_id": 999}}

    missing = await _post(app, payload, key=None)
    oversized = await _post(app, payload, key="x" * 129)

    assert missing.status_code == 422
    assert oversized.status_code == 422
    assert calls == 0


@pytest.mark.asyncio
async def test_same_payload_replays_without_a_second_collection_write(monkeypatch) -> None:
    calls = 0

    async def fake_upsert(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return _collection()

    async def fake_get(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return _collection()

    monkeypatch.setattr(collections_module, "upsert_collection", fake_upsert)
    monkeypatch.setattr(collections_module, "get_collection", fake_get)
    monkeypatch.setattr(
        collections_module,
        "clear_collection_cache",
        lambda _user_id: {"status": "cleared"},
    )
    app = _app()
    payload = {"collection": {"type": 2, "user_id": 999}}

    first = await _post(app, payload)
    second = await _post(app, payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.headers["x-idempotency-status"] == "replayed"
    assert calls == 1
    assert second.json() == first.json()


@pytest.mark.asyncio
async def test_changed_payload_with_same_key_returns_conflict(monkeypatch) -> None:
    calls = 0

    async def fake_upsert(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return _collection()

    async def fake_get(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return _collection()

    monkeypatch.setattr(collections_module, "upsert_collection", fake_upsert)
    monkeypatch.setattr(collections_module, "get_collection", fake_get)
    monkeypatch.setattr(
        collections_module,
        "clear_collection_cache",
        lambda _user_id: {"status": "cleared"},
    )
    app = _app()

    first = await _post(app, {"collection": {"type": 2}}, key="same-key")
    conflict = await _post(app, {"collection": {"type": 3}}, key="same-key")

    assert first.status_code == 200
    assert conflict.status_code == 409
    assert conflict.json()["error_code"] == "idempotency_conflict"
    assert calls == 1


@pytest.mark.asyncio
async def test_same_key_isolated_by_authenticated_principal(monkeypatch) -> None:
    calls = 0
    current_user_id = 7

    async def override_user() -> UserRead:
        return _user(current_user_id)

    async def fake_upsert(*args: Any, **kwargs: Any) -> dict[str, Any]:
        nonlocal calls
        calls += 1
        return _collection()

    async def fake_get(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return _collection()

    monkeypatch.setattr(collections_module, "upsert_collection", fake_upsert)
    monkeypatch.setattr(collections_module, "get_collection", fake_get)
    monkeypatch.setattr(
        collections_module,
        "clear_collection_cache",
        lambda _user_id: {"status": "cleared"},
    )
    app = _app()
    app.dependency_overrides[get_current_user] = override_user
    payload = {"collection": {"type": 2}}

    first = await _post(app, payload, key="same-key-different-user")
    current_user_id = 8
    second = await _post(app, payload, key="same-key-different-user")

    assert first.status_code == 200
    assert second.status_code == 200
    assert calls == 2


@pytest.mark.asyncio
async def test_cache_clear_failure_is_a_warning_after_successful_write(monkeypatch) -> None:
    async def fake_upsert(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return _collection()

    async def fake_get(*args: Any, **kwargs: Any) -> dict[str, Any]:
        return _collection()

    monkeypatch.setattr(collections_module, "upsert_collection", fake_upsert)
    monkeypatch.setattr(collections_module, "get_collection", fake_get)
    monkeypatch.setattr(
        collections_module,
        "clear_collection_cache",
        lambda _user_id: {"status": "warning", "code": "cache_clear_failed"},
    )
    response = await _post(_app(), {"collection": {"type": 2}})

    assert response.status_code == 200
    assert response.headers["x-collection-cache-status"] == "warning"
    assert response.json()["source_id"] == "100"


@pytest.mark.asyncio
async def test_batch_item_limit_is_rejected_before_idempotency_claim() -> None:
    app = _app()
    items = [
        {
            "type": 2,
            "source": "bangumi",
            "source_id": str(index),
        }
        for index in range(101)
    ]

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/v1/collections/batch",
            json={"total": len(items), "items": items},
            headers={"Idempotency-Key": "batch-too-large"},
        )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_anonymous_collection_write_is_denied() -> None:
    app = FastAPI()
    app.include_router(collections_router, prefix="/v1")
    app.dependency_overrides[
        collections_module.get_collection_idempotency_store
    ] = lambda: InMemoryIdempotencyStore()

    response = await _post(
        app,
        {"collection": {"type": 2}},
        key="anonymous-write",
    )

    assert response.status_code in {401, 403}
