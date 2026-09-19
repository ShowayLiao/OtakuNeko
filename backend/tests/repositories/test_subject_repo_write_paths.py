"""Subject 写入路径回归测试。

这些测试直接调用真实仓库层和真实内存数据库，**不 monkeypatch 仓库**。

它们守护的缺陷：`SubjectRepo.get_by_source` 返回的 `SubjectWithCollection.subject`
是 `SubjectRead` DTO 的副本而不是 session 绑定的 ORM 行，写入路径对它调用
`db.add` / `db.refresh` 会抛 `UnmappedInstanceError`，被仓库自己的
`except SQLAlchemyError` 吞掉后重新抛出——数据一行都没写进去。

因此每个断言都先用 `expire_all()` 清空身份映射再重新查询，确保结论来自数据库，
而不是内存中被误改的对象。
"""

from datetime import datetime, timezone

import pytest
from sqlmodel import select

# 导入模型以注册表结构：conftest 的 db_session 依赖 SQLModel.metadata
from app.models import Collection, Subject, User  # noqa: F401
from app.models.enums import SubjectType
from app.repositories.subject_repo import SubjectRepo
from app.schemas.subject import (
    SubjectCreate,
    SubjectSearchByID,
    SubjectUpdate,
    SubjectUpsert,
    SubjectUpsertList,
)


async def _seed_subject(
    db_session, *, name: str = "旧名称", source_id: str = "100"
) -> Subject:
    subject = Subject(
        source="bangumi",
        source_id=source_id,
        type=SubjectType.ANIME,
        name=name,
        last_sync=datetime.now(timezone.utc),
    )
    db_session.add(subject)
    await db_session.commit()
    return subject


async def _reload(db_session, subject_id: int) -> Subject | None:
    """清空身份映射后重新查询，证明数据真的落库。"""
    db_session.expire_all()
    result = await db_session.execute(
        select(Subject).where(Subject.id == subject_id)
    )
    return result.scalar_one_or_none()


async def _count(db_session) -> int:
    db_session.expire_all()
    result = await db_session.execute(select(Subject))
    return len(list(result.scalars().all()))


@pytest.mark.asyncio
async def test_create_overwrites_the_existing_row_instead_of_failing(db_session):
    existing = await _seed_subject(db_session, name="旧名称", source_id="100")

    created = await SubjectRepo.create(
        db_session,
        SubjectCreate(
            source="bangumi",
            source_id="100",
            type=SubjectType.ANIME,
            name="新名称",
        ),
    )

    assert created is not None
    assert created.id == existing.id

    persisted = await _reload(db_session, existing.id)
    assert persisted is not None
    assert persisted.name == "新名称"
    # 同一 (source, source_id) 不能产生第二行
    assert await _count(db_session) == 1


@pytest.mark.asyncio
async def test_create_does_not_null_a_not_null_last_sync(db_session):
    """Subject.last_sync 是 NOT NULL，而 SubjectCreate 的默认值是 None。

    写路径显式带上 None 时 UPDATE 会写出 NULL 并触发 IntegrityError，所以
    payload 里为 None 的 last_sync 必须被剔除。
    """
    existing = await _seed_subject(db_session, source_id="100")

    await SubjectRepo.create(
        db_session,
        SubjectCreate(
            source="bangumi",
            source_id="100",
            type=SubjectType.ANIME,
            name="新名称",
        ),
    )

    persisted = await _reload(db_session, existing.id)
    assert persisted is not None
    assert persisted.last_sync is not None


@pytest.mark.asyncio
async def test_create_inserts_a_brand_new_subject(db_session):
    created = await SubjectRepo.create(
        db_session,
        SubjectCreate(
            source="bangumi",
            source_id="777",
            type=SubjectType.BOOK,
            name="新条目",
        ),
    )

    assert created.id is not None
    persisted = await _reload(db_session, created.id)
    assert persisted is not None
    assert persisted.name == "新条目"
    assert persisted.type == SubjectType.BOOK


@pytest.mark.asyncio
async def test_update_persists_only_the_provided_fields(db_session):
    existing = await _seed_subject(db_session, name="原名", source_id="100")

    updated = await SubjectRepo.update(
        db_session,
        SubjectUpdate(source="bangumi", source_id="100", name="改名"),
    )

    assert updated is not None
    persisted = await _reload(db_session, existing.id)
    assert persisted is not None
    assert persisted.name == "改名"
    # 未提供的字段不能被清掉
    assert persisted.type == SubjectType.ANIME
    assert persisted.last_sync is not None


@pytest.mark.asyncio
async def test_update_returns_none_for_a_missing_subject(db_session):
    result = await SubjectRepo.update(
        db_session,
        SubjectUpdate(source="bangumi", source_id="does-not-exist", name="改名"),
    )

    assert result is None


@pytest.mark.asyncio
async def test_delete_removes_the_row(db_session):
    existing = await _seed_subject(db_session, source_id="100")

    deleted = await SubjectRepo.delete(
        db_session, SubjectSearchByID(source="bangumi", source_id="100")
    )

    assert deleted is True
    assert await _reload(db_session, existing.id) is None
    assert await _count(db_session) == 0


@pytest.mark.asyncio
async def test_delete_returns_false_for_a_missing_subject(db_session):
    deleted = await SubjectRepo.delete(
        db_session, SubjectSearchByID(source="bangumi", source_id="missing")
    )

    assert deleted is False


@pytest.mark.asyncio
async def test_batch_upsert_tolerates_items_with_different_key_sets(db_session):
    """异构批次回归。

    batch_upsert 会把各条数据的 key 取并集再统一结构。旧实现把缺失的 key 一律
    回填 None，于是"某条设了 series、另一条没设"就会写出
    `NOT NULL constraint failed: subject.series`。NOT NULL 列必须回填模型默认值。
    """
    await SubjectRepo.batch_upsert(
        db_session,
        SubjectUpsertList(
            total=2,
            items=[
                SubjectUpsert(
                    source="bangumi",
                    source_id="900",
                    type=SubjectType.ANIME,
                    name="第一条",
                    series=True,
                ),
                SubjectUpsert(
                    source="bangumi",
                    source_id="901",
                    type=SubjectType.ANIME,
                    name="第二条",
                ),
            ],
        ),
    )

    db_session.expire_all()
    rows = {
        row.source_id: row
        for row in (await db_session.execute(select(Subject))).scalars().all()
    }
    assert rows["900"].series is True
    assert rows["901"].series is False
    assert rows["900"].name == "第一条"
    assert rows["901"].name == "第二条"


@pytest.mark.asyncio
async def test_batch_upsert_rejects_an_item_missing_a_required_field(db_session):
    """既非 nullable、又没有模型默认值的列缺失时必须明确报错，而不是写 NULL。"""
    with pytest.raises(ValueError, match="name"):
        await SubjectRepo.batch_upsert(
            db_session,
            SubjectUpsertList(
                total=2,
                items=[
                    SubjectUpsert(
                        source="bangumi",
                        source_id="902",
                        type=SubjectType.ANIME,
                        name="有名字",
                    ),
                    SubjectUpsert(
                        source="bangumi",
                        source_id="903",
                        type=SubjectType.ANIME,
                    ),
                ],
            ),
        )
