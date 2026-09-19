from __future__ import annotations

import asyncio

import pytest

from app.schemas.subject import SubjectSearchBase
from app.services import subject_service


@pytest.mark.asyncio
@pytest.mark.parametrize("cancelled_side", ["local", "remote"])
async def test_search_mixed_propagates_cancellation(monkeypatch, cancelled_side):
    async def cancelled_search(*_args, **_kwargs):
        raise asyncio.CancelledError()

    async def empty_remote_search(*_args, **_kwargs):
        return subject_service.UnifiedList(total=0, items=[])

    monkeypatch.setattr(
        subject_service,
        "search_subject_by_name",
        cancelled_search if cancelled_side == "local" else empty_remote_search,
    )
    monkeypatch.setattr(
        subject_service,
        "search_subject_cloud",
        cancelled_search if cancelled_side == "remote" else empty_remote_search,
    )

    with pytest.raises(asyncio.CancelledError):
        await subject_service.search_mixed(
            db=None,
            search_data=SubjectSearchBase(keyword="anime"),
        )


async def _seed_subject(db_session, *, source_id: str = "123"):
    from datetime import datetime

    from app.models import Subject
    from app.models.enums import SubjectType

    subject = Subject(
        source="bangumi",
        source_id=source_id,
        type=SubjectType.ANIME,
        name="条目标题",
        last_sync=datetime(2020, 1, 1),
    )
    db_session.add(subject)
    await db_session.commit()
    return subject


def _patch_bangumi_data(monkeypatch, payload):
    """替换外部 I/O 边界（bangumi-data 下载），不触碰仓库。"""
    from app.services.bangumi_data_sync import BangumiDataSyncService

    async def fake_fetch():
        return payload

    monkeypatch.setattr(BangumiDataSyncService, "fetch_bangumi_data", fake_fetch)


def _catalog(source_id: str, begin: str) -> dict:
    return {
        "items": [
            {
                "sites": [{"site": "bangumi", "id": source_id}],
                "begin": begin,
            }
        ]
    }


@pytest.mark.asyncio
async def test_sync_subject_air_time_persists_air_time_and_weekday(
    db_session, monkeypatch
):
    from datetime import datetime

    from sqlmodel import select

    from app.models import Subject

    seeded = await _seed_subject(db_session)
    subject_id = seeded.id
    _patch_bangumi_data(
        monkeypatch, _catalog("123", "2024-04-07T01:05:00.000000Z")
    )

    assert await subject_service.sync_subject_air_time(db_session, "123") is True

    db_session.expire_all()
    persisted = (
        await db_session.execute(select(Subject).where(Subject.id == subject_id))
    ).scalar_one()
    assert persisted.air_time == datetime(2024, 4, 7, 1, 5)
    # 2024-04-07 是周日，接口约定 1-7
    assert persisted.air_weekday == 7
    assert persisted.last_sync > datetime(2020, 1, 1)


@pytest.mark.asyncio
async def test_sync_subject_air_time_derives_weekday_from_the_original_offset(
    db_session, monkeypatch
):
    """深夜番按日本放送日归属，不能因为 UTC 归一化被算到前一天。"""
    from datetime import datetime

    from sqlmodel import select

    from app.models import Subject

    seeded = await _seed_subject(db_session)
    subject_id = seeded.id
    _patch_bangumi_data(
        monkeypatch, _catalog("123", "2024-04-07T00:30:00+09:00")
    )

    assert await subject_service.sync_subject_air_time(db_session, "123") is True

    db_session.expire_all()
    persisted = (
        await db_session.execute(select(Subject).where(Subject.id == subject_id))
    ).scalar_one()
    # 落库归一到 UTC：2024-04-06T15:30Z
    assert persisted.air_time == datetime(2024, 4, 6, 15, 30)
    # 星期按原始 +09:00 的周日计算
    assert persisted.air_weekday == 7


@pytest.mark.asyncio
async def test_sync_subject_air_time_returns_false_for_an_unknown_subject(
    db_session, monkeypatch
):
    _patch_bangumi_data(monkeypatch, _catalog("123", "2024-04-07T01:05:00Z"))

    assert await subject_service.sync_subject_air_time(db_session, "999") is False


@pytest.mark.asyncio
async def test_sync_subject_air_time_propagates_fetch_failures(
    db_session, monkeypatch
):
    """抓取失败是内部故障，必须抛出去让路由回 500，不能伪装成条目不存在。"""
    from app.services.bangumi_data_sync import BangumiDataSyncService

    await _seed_subject(db_session)

    async def failing_fetch():
        raise RuntimeError("无法下载 bangumi-data 数据")

    monkeypatch.setattr(BangumiDataSyncService, "fetch_bangumi_data", failing_fetch)

    with pytest.raises(RuntimeError):
        await subject_service.sync_subject_air_time(db_session, "123")
