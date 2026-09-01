from __future__ import annotations

from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from app.api.v1 import dashboard


@pytest.mark.asyncio
async def test_collection_statistics_endpoint_uses_trusted_current_user(
    monkeypatch,
):
    captured: dict[str, object] = {}

    async def fake_statistics(user_id, db, *, subject_type):
        captured.update(user_id=user_id, db=db, subject_type=subject_type)
        return {"subject_type": subject_type, "total": 0}

    monkeypatch.setattr(dashboard, "get_collection_statistics_service", fake_statistics)

    result = await dashboard.get_collection_statistics_endpoint(
        subject_type=2,
        current_user=SimpleNamespace(id=7),
        db="trusted-db",
    )

    assert result == {"subject_type": 2, "total": 0}
    assert captured == {"user_id": 7, "db": "trusted-db", "subject_type": 2}


@pytest.mark.asyncio
async def test_collection_statistics_endpoint_rejects_unknown_subject_type(
    monkeypatch,
):
    service_called = False

    async def fake_statistics(*args, **kwargs):
        nonlocal service_called
        service_called = True
        return {"subject_type": 5, "total": 0}

    monkeypatch.setattr(dashboard, "get_collection_statistics_service", fake_statistics)

    app = FastAPI()
    app.include_router(dashboard.router)
    app.dependency_overrides[dashboard.get_current_user] = lambda: SimpleNamespace(id=7)
    app.dependency_overrides[dashboard.get_session] = lambda: None

    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
    ) as client:
        response = await client.get(
            "/dashboard/collection-statistics?subject_type=5"
        )

    assert response.status_code == 422
    assert service_called is False
