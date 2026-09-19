"""Collection 写入路径回归测试。

这些测试直接调用真实仓库层和真实内存数据库，**不 monkeypatch 仓库**。

守护两个既有缺陷：

1. `CollectionRepo.get_by_user_and_subject` 返回的 `CollectionWithSubject.collection`
   是 `CollectionRead` DTO 的副本（而且 `CollectionRead` 根本没有 id 字段），
   写入路径对它 `db.add` / `db.delete` 会抛 `UnmappedInstanceError`。
2. `CollectionRepo.batch_upsert` 用裸 `model_dump()` 构建 Core insert，把
   `updated_at=None` / `type=None` 写进 NOT NULL 列，每次 upsert 都
   `IntegrityError`。Core insert 只对**省略**的列应用模型默认值。
"""

from datetime import datetime, timezone

import pytest
from sqlmodel import select

# 导入模型以注册表结构：conftest 的 db_session 依赖 SQLModel.metadata
from app.models import Collection, Subject, User  # noqa: F401
from app.models.enums import CollectionStatus, SubjectType
from app.repositories.collection_repo import CollectionRepo
from app.schemas.collection import (
    CollectionSearchByID,
    CollectionUpdate,
    CollectionUpsert,
    CollectionUpsertList,
)

# CollectionRepo.delete / batch_upsert 会调用 FastAPICache.clear
pytestmark = pytest.mark.usefixtures("initialized_cache")

SUBJECT_ID = "100"

# SQLite 不保存 tzinfo，回读回来的更新时间是 naive 的
SEEDED_UPDATED_AT = datetime(2020, 1, 1)


async def _seed_user(db_session) -> User:
    user = User(
        username="write-path-user",
        hashed_password="x",
    )
    db_session.add(user)
    await db_session.commit()
    return user


async def _seed_subject(db_session, source_id: str = SUBJECT_ID) -> Subject:
    subject = Subject(
        source="bangumi",
        source_id=source_id,
        type=SubjectType.ANIME,
        name="条目标题",
        last_sync=datetime.now(timezone.utc),
    )
    db_session.add(subject)
    await db_session.commit()
    return subject


async def _seed_collection(
    db_session,
    user_id: int,
    *,
    source_id: str = SUBJECT_ID,
    collection_type: CollectionStatus = CollectionStatus.WISH,
    rate: int | None = 1,
    comment: str | None = "旧评论",
) -> Collection:
    collection = Collection(
        user_id=user_id,
        source="bangumi",
        source_id=source_id,
        type=collection_type,
        rate=rate,
        comment=comment,
        updated_at=SEEDED_UPDATED_AT,
    )
    db_session.add(collection)
    await db_session.commit()
    return collection


async def _reload(db_session, collection_id: int) -> Collection | None:
    """清空身份映射后重新查询，证明数据真的落库。"""
    db_session.expire_all()
    result = await db_session.execute(
        select(Collection).where(Collection.id == collection_id)
    )
    return result.scalar_one_or_none()


@pytest.mark.asyncio
async def test_update_persists_changes_and_bumps_updated_at(db_session):
    user = await _seed_user(db_session)
    await _seed_subject(db_session)
    seeded = await _seed_collection(db_session, user.id)

    updated = await CollectionRepo.update(
        db_session,
        CollectionUpdate(
            user_id=user.id,
            source="bangumi",
            source_id=SUBJECT_ID,
            type=CollectionStatus.COLLECT,
            rate=9,
        ),
    )

    assert updated is not None
    persisted = await _reload(db_session, seeded.id)
    assert persisted is not None
    assert persisted.type == CollectionStatus.COLLECT
    assert persisted.rate == 9
    # 未提供的字段不能被清掉
    assert persisted.comment == "旧评论"
    # GET /collections 按 updated_at 排序，编辑必须刷新时间戳
    assert persisted.updated_at > SEEDED_UPDATED_AT


@pytest.mark.asyncio
async def test_update_returns_none_when_the_collection_is_missing(db_session):
    user = await _seed_user(db_session)

    result = await CollectionRepo.update(
        db_session,
        CollectionUpdate(
            user_id=user.id,
            source="bangumi",
            source_id="does-not-exist",
            type=CollectionStatus.COLLECT,
        ),
    )

    assert result is None


@pytest.mark.asyncio
async def test_update_rejects_a_missing_identity_field(db_session):
    """缺少 user_id/source/source_id 时必须硬报错，而不是静默 return None。

    静默 None 会让调用方把它当成"记录不存在"，把编程错误伪装成 404。
    """
    with pytest.raises(ValueError):
        await CollectionRepo.update(
            db_session, CollectionUpdate(source="bangumi", source_id=SUBJECT_ID)
        )


@pytest.mark.asyncio
async def test_delete_removes_the_row(db_session):
    user = await _seed_user(db_session)
    await _seed_subject(db_session)
    seeded = await _seed_collection(db_session, user.id)

    deleted = await CollectionRepo.delete(
        db_session,
        CollectionSearchByID(
            user_id=user.id, source="bangumi", source_id=SUBJECT_ID
        ),
    )

    assert deleted is True
    assert await _reload(db_session, seeded.id) is None


@pytest.mark.asyncio
async def test_delete_returns_false_for_a_missing_collection(db_session):
    user = await _seed_user(db_session)

    deleted = await CollectionRepo.delete(
        db_session,
        CollectionSearchByID(
            user_id=user.id, source="bangumi", source_id="missing"
        ),
    )

    assert deleted is False


@pytest.mark.asyncio
async def test_batch_upsert_fills_not_null_columns_for_a_new_row(db_session):
    """回归：NOT NULL constraint failed: collection.updated_at / collection.type。"""
    user = await _seed_user(db_session)

    await CollectionRepo.batch_upsert(
        db_session,
        CollectionUpsertList(
            total=1,
            collections=[
                CollectionUpsert(
                    user_id=user.id,
                    source="bangumi",
                    source_id=SUBJECT_ID,
                    type=CollectionStatus.WISH,
                )
            ],
        ),
    )

    db_session.expire_all()
    result = await db_session.execute(
        select(Collection).where(Collection.source_id == SUBJECT_ID)
    )
    persisted = result.scalar_one()
    assert persisted.type == CollectionStatus.WISH
    assert persisted.updated_at is not None


@pytest.mark.asyncio
async def test_batch_upsert_conflict_updates_only_provided_fields(db_session):
    user = await _seed_user(db_session)
    seeded = await _seed_collection(
        db_session,
        user.id,
        collection_type=CollectionStatus.WISH,
        rate=5,
        comment="保留我",
    )

    await CollectionRepo.batch_upsert(
        db_session,
        CollectionUpsertList(
            total=1,
            collections=[
                CollectionUpsert(
                    user_id=user.id,
                    source="bangumi",
                    source_id=SUBJECT_ID,
                    type=CollectionStatus.DO,
                )
            ],
        ),
    )

    persisted = await _reload(db_session, seeded.id)
    assert persisted is not None
    assert persisted.type == CollectionStatus.DO
    # 未显式提供的列不能被 schema 默认值覆盖
    assert persisted.rate == 5
    assert persisted.comment == "保留我"
    assert persisted.updated_at > SEEDED_UPDATED_AT


@pytest.mark.asyncio
async def test_batch_upsert_rejects_a_missing_type(db_session):
    """type 是 NOT NULL，数据库在冲突解析之前就会校验，必须明确拒绝。"""
    user = await _seed_user(db_session)
    upsert = CollectionUpsert(
        user_id=user.id, source="bangumi", source_id=SUBJECT_ID
    )
    assert upsert.type is None

    with pytest.raises(ValueError, match="type"):
        await CollectionRepo.batch_upsert(
            db_session,
            CollectionUpsertList(total=1, collections=[upsert]),
        )
