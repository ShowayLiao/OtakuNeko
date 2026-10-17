"""Collection 列表接口的查询边界回归测试。

守护的缺陷：`GET /v1/collections` 的 `limit` / `offset` 没有声明上下界，而兄弟
接口 `GET /v1/subjects` 有（`limit: Query(20, ge=1, le=100)`）。越界值因此会一路
走到 `CollectionRepo` 的 `.limit()` / `.offset()`：

- SQLite 把负 offset 当 0、负 limit 当"不限量"，于是静默返回全部记录（绕过分页）；
- PostgreSQL 直接报 `LIMIT must not be negative` / `OFFSET must not be negative`，
  接口变成 500。

两种部署模式下行为不一致，且都不该发生。这里断言这些值在 HTTP 边界就被拒。
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
from fastapi import FastAPI

from app.api.deps import get_current_user
from app.api.v1.collections import router as collections_router
from app.db.database import get_session
from app.schemas.user import UserRead

pytestmark = pytest.mark.usefixtures("initialized_cache")

USER_ID = 7


def _user() -> UserRead:
    return UserRead(
        id=USER_ID,
        username="bounds-user",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


@pytest.fixture
def wired_app(db_session):
    app = FastAPI()
    app.include_router(collections_router, prefix="/v1")

    async def override_user() -> UserRead:
        return _user()

    async def override_session():
        yield db_session

    app.dependency_overrides[get_current_user] = override_user
    app.dependency_overrides[get_session] = override_session
    yield app
    app.dependency_overrides.clear()


async def _get(app: FastAPI, query: str) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.get(f"/v1/collections?{query}")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [
        "limit=0",
        "limit=-1",
        "limit=101",
        "offset=-1",
        "limit=-1&offset=-1",
    ],
)
async def test_out_of_range_pagination_is_rejected_at_the_boundary(
    wired_app, query: str
) -> None:
    response = await _get(wired_app, query)

    assert response.status_code == 422, response.text


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "query",
    [
        "limit=1",
        "limit=100",
        "limit=10&offset=0",
        "offset=50",
        "",
    ],
)
async def test_in_range_pagination_still_succeeds(wired_app, query: str) -> None:
    response = await _get(wired_app, query)

    assert response.status_code == 200, response.text
    assert "items" in response.json()
