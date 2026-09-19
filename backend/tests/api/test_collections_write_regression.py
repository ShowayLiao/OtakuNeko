"""Collection 写接口回归测试（PUT / DELETE）。

现有的 `tests/api/test_collections_idempotency.py` 只覆盖 POST，而且把服务函数
和 session 都替换掉了（`get_session` 被覆盖成 `lambda: None`）。这里用真实
session、真实仓库和真实 `SqlIdempotencyStore` 跑完整链路。

守护的缺陷：写路径把 Pydantic DTO 副本当作 ORM 行，`db.add` / `db.delete` 抛
`UnmappedInstanceError`。异常被 `CollectionHttpIdempotencyAdapter` 吞成
"state unknown"，于是接口返回 409 而不是 200，数据一行都没改。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import httpx
import pytest
from fastapi import FastAPI
from sqlmodel import select

from app.api.deps import get_current_user
from app.api.v1.collections import router as collections_router
from app.db.database import get_session

# 导入模型以注册表结构：conftest 的 db_session 依赖 SQLModel.metadata
from app.models import Collection, Subject, User  # noqa: F401
from app.models.enums import CollectionStatus, SubjectType
from app.schemas.user import UserRead

pytestmark = pytest.mark.usefixtures("initialized_cache")

USER_ID = 7
SOURCE = "bangumi"
SOURCE_ID = "100"


def _user() -> UserRead:
    return UserRead(
        id=USER_ID,
        username="write-user",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )


async def _seed(db_session) -> Collection:
    """PUT/DELETE 的读回路径要求存在同名 Subject（_is_valid_subject 校验 name）。"""
    user = User(id=USER_ID, username="write-user", hashed_password="x")
    subject = Subject(
        source=SOURCE,
        source_id=SOURCE_ID,
        type=SubjectType.ANIME,
        name="条目标题",
        last_sync=datetime.now(timezone.utc),
    )
    collection = Collection(
        user_id=USER_ID,
        source=SOURCE,
        source_id=SOURCE_ID,
        type=CollectionStatus.WISH,
        rate=1,
        comment="旧评论",
        updated_at=datetime(2020, 1, 1),
    )
    db_session.add_all([user, subject, collection])
    await db_session.commit()
    return collection


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


async def _request(
    app: FastAPI, method: str, path: str, *, key: str, json: Any = None
) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        return await client.request(
            method,
            path,
            json=json,
            headers={"Idempotency-Key": key},
        )


async def _reload(db_session, collection_id: int) -> Collection | None:
    db_session.expire_all()
    result = await db_session.execute(
        select(Collection).where(Collection.id == collection_id)
    )
    return result.scalar_one_or_none()


@pytest.mark.asyncio
async def test_put_updates_the_collection_and_persists(
    db_session, wired_app
) -> None:
    seeded = await _seed(db_session)
    collection_id = seeded.id

    response = await _request(
        wired_app,
        "PUT",
        f"/v1/collections/{SOURCE}/{SOURCE_ID}",
        key="put-1",
        json={"type": 2, "rate": 9},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["collection"]["rate"] == 9
    assert response.headers["x-collection-cache-status"] == "cleared"

    persisted = await _reload(db_session, collection_id)
    assert persisted is not None
    assert persisted.rate == 9
    assert persisted.type == CollectionStatus.COLLECT
    # 未提交的字段不能被清掉
    assert persisted.comment == "旧评论"


@pytest.mark.asyncio
async def test_put_replays_for_the_same_idempotency_key(
    db_session, wired_app
) -> None:
    await _seed(db_session)
    path = f"/v1/collections/{SOURCE}/{SOURCE_ID}"
    payload = {"type": 2, "rate": 9}

    first = await _request(wired_app, "PUT", path, key="put-replay", json=payload)
    second = await _request(wired_app, "PUT", path, key="put-replay", json=payload)

    assert first.status_code == 200, first.text
    assert second.status_code == 200, second.text
    assert second.headers["x-idempotency-status"] == "replayed"
    assert second.json() == first.json()


@pytest.mark.asyncio
async def test_put_returns_404_for_a_missing_collection(
    db_session, wired_app
) -> None:
    await _seed(db_session)

    response = await _request(
        wired_app,
        "PUT",
        f"/v1/collections/{SOURCE}/does-not-exist",
        key="put-missing",
        json={"type": 2},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_removes_the_collection(db_session, wired_app) -> None:
    seeded = await _seed(db_session)
    collection_id = seeded.id

    response = await _request(
        wired_app,
        "DELETE",
        f"/v1/collections/{SOURCE}/{SOURCE_ID}",
        key="delete-1",
    )

    assert response.status_code == 200, response.text
    assert response.json()["status"] == "success"
    assert await _reload(db_session, collection_id) is None


@pytest.mark.asyncio
async def test_delete_returns_404_for_a_missing_collection(
    db_session, wired_app
) -> None:
    await _seed(db_session)

    response = await _request(
        wired_app,
        "DELETE",
        f"/v1/collections/{SOURCE}/does-not-exist",
        key="delete-missing",
    )

    assert response.status_code == 404
