from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from app.api.deps import get_current_user
from app.api.v1 import rss as rss_module
from app.api.v1.rss import router as rss_router
from app.core.config import settings
from app.harness.persistence.idempotency import InMemoryIdempotencyStore
from app.schemas.rss import RssItemsResponse, RssRulesResponse
from app.schemas.user import UserRead


class FakeQBService:
    calls: list[tuple[str, dict[str, Any]]] = []

    def __init__(self) -> None:
        self.calls.append(("init", {}))

    def add_rss_feed(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("add", kwargs))
        return {"status": "succeeded", "message": "RSS feed added."}

    def upsert_rss_feed(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("upsert", kwargs))
        return {"status": "succeeded", "message": "RSS feed upserted."}

    def remove_rss_item(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("remove", kwargs))
        return {"status": "succeeded", "message": "RSS item removed."}

    def set_rss_rule(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("set-rule", kwargs))
        return {"status": "succeeded", "message": "RSS rule set."}

    def remove_rss_rule(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("remove-rule", kwargs))
        return {"status": "succeeded", "message": "RSS rule removed."}

    def get_rss_items(self) -> RssItemsResponse:
        self.calls.append(("list", {}))
        return RssItemsResponse(items={})

    def get_rss_rules(self) -> RssRulesResponse:
        self.calls.append(("rules", {}))
        return RssRulesResponse(rules={})


def _user(user_id: int) -> UserRead:
    return UserRead(
        id=user_id,
        username=f"user-{user_id}",
        created_at=datetime.now(timezone.utc),
    )


def _app(user_id: int = 7) -> FastAPI:
    app = FastAPI()
    app.include_router(rss_router, prefix="/v1")
    store = InMemoryIdempotencyStore()

    async def override_user() -> UserRead:
        return _user(user_id)

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[rss_module.get_idempotency_store] = lambda: store
    return app


async def _post(app: FastAPI, path: str, payload: dict[str, Any]) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.post(path, json=payload)


@pytest.mark.asyncio
async def test_same_key_replays_without_a_second_qb_write(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ENABLE_QB_PROXY", True)
    monkeypatch.setattr(settings, "QB_ALLOWED_USER_IDS", "7")
    monkeypatch.setattr(rss_module, "QBService", FakeQBService)
    FakeQBService.calls = []
    app = _app()
    payload = {
        "url": "https://example.test/feed",
        "name": "feed",
        "idempotency_key": "rss-add-1",
    }

    first = await _post(app, "/v1/rss/add", payload)
    second = await _post(app, "/v1/rss/add", payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert [name for name, _ in FakeQBService.calls].count("add") == 1


@pytest.mark.asyncio
async def test_same_key_with_changed_payload_returns_conflict_without_qb_write(
    monkeypatch,
) -> None:
    monkeypatch.setattr(settings, "ENABLE_QB_PROXY", True)
    monkeypatch.setattr(settings, "QB_ALLOWED_USER_IDS", "7")
    monkeypatch.setattr(rss_module, "QBService", FakeQBService)
    FakeQBService.calls = []
    app = _app()

    first = await _post(
        app,
        "/v1/rss/add",
        {
            "url": "https://example.test/one",
            "name": "feed",
            "idempotency_key": "rss-add-2",
        },
    )
    conflict = await _post(
        app,
        "/v1/rss/add",
        {
            "url": "https://example.test/two",
            "name": "feed",
            "idempotency_key": "rss-add-2",
        },
    )

    assert first.status_code == 200
    assert conflict.status_code == 409
    assert conflict.json()["error_code"] == "idempotency_conflict"
    assert [name for name, _ in FakeQBService.calls].count("add") == 1


@pytest.mark.asyncio
async def test_missing_or_unsafe_key_is_rejected_before_qb(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ENABLE_QB_PROXY", True)
    monkeypatch.setattr(settings, "QB_ALLOWED_USER_IDS", "7")
    monkeypatch.setattr(rss_module, "QBService", FakeQBService)
    FakeQBService.calls = []
    app = _app()

    missing = await _post(
        app, "/v1/rss/add", {"url": "https://example.test/feed", "name": "feed"}
    )
    unsafe = await _post(
        app,
        "/v1/rss/add",
        {
            "url": "https://example.test/feed",
            "name": "feed",
            "idempotency_key": "bad key",
        },
    )

    assert missing.status_code == 422
    assert unsafe.status_code == 422
    assert FakeQBService.calls == []


@pytest.mark.asyncio
async def test_authenticated_principal_is_part_of_idempotency_scope(monkeypatch) -> None:
    monkeypatch.setattr(settings, "ENABLE_QB_PROXY", True)
    monkeypatch.setattr(settings, "QB_ALLOWED_USER_IDS", "7,8")
    monkeypatch.setattr(rss_module, "QBService", FakeQBService)
    FakeQBService.calls = []
    app = _app(user_id=7)
    payload = {
        "url": "https://example.test/feed",
        "name": "feed",
        "idempotency_key": "same-key-different-user",
    }

    first = await _post(app, "/v1/rss/add", payload)
    app = _app(user_id=8)
    second = await _post(app, "/v1/rss/add", payload)

    assert first.status_code == 200
    assert second.status_code == 200
    assert [name for name, _ in FakeQBService.calls].count("add") == 2
