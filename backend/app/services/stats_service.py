from collections import Counter
from typing import Any, cast

from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi_cache.decorator import cache

from app.models import Collection, CollectionStatus, Subject, SubjectType
from app.schemas.dashboard import (
    CollectionGenreCount,
    CollectionStatistics,
    CollectionStatusCounts,
    DashboardStats,
)
from app.core.logging import get_logger

logger = get_logger(__name__)

# SQLModel class attributes are SQLAlchemy expressions at runtime.  The local
# aliases bridge that descriptor boundary for SQLAlchemy's typed overloads.
_COLLECTION_USER_ID = cast(Any, Collection.user_id)
_COLLECTION_SOURCE = cast(Any, Collection.source)
_COLLECTION_SOURCE_ID = cast(Any, Collection.source_id)
_COLLECTION_ID = cast(Any, Collection.id)
_COLLECTION_TYPE = cast(Any, Collection.type)
_COLLECTION_SUBJECT_TYPE = cast(Any, Collection.subject_type)
_SUBJECT_TYPE = cast(Any, Subject.type)
_SUBJECT_SOURCE = cast(Any, Subject.source)
_SUBJECT_SOURCE_ID = cast(Any, Subject.source_id)
_SUBJECT_META_TAGS = cast(Any, Subject.meta_tags)
_SUBJECT_TAGS = cast(Any, Subject.tags)


def stats_key_builder(
    func: Any,
    namespace: str,
    request: Any,
    *args: Any,
    **kwargs: Any,
) -> str:
    """
    自定义缓存 key 构建器
    
    为每个用户生成独立的缓存 key，格式为: dashboard:stats:{user_id}
    
    Args:
        func: 被缓存的函数
        namespace: 命名空间
        request: FastAPI 请求对象
        *args, **kwargs: 函数参数
    
    Returns:
        缓存 key 字符串
    """
    user_id = kwargs.get("user_id", args[0] if args else None)
    return f"dashboard:stats:{user_id}"

@cache(expire=600, namespace="dashboard", key_builder=cast(Any, stats_key_builder))
async def get_user_stats(user_id: int, db: AsyncSession) -> DashboardStats:
    """
    获取用户的收藏统计数据
    
    使用 Group By 查询在数据库层完成聚合，统计用户在不同分类下的收藏数量
    
    Args:
        user_id: 用户ID
        db: 数据库会话
    
    Returns:
        DashboardStats 对象，包含各分类的收藏数量
    """
    logger.info(f"开始获取用户统计数据: user_id={user_id}")
    
    statement = (
        select(_SUBJECT_TYPE, func.count(_COLLECTION_SOURCE_ID))
        .join(Collection, and_(
            _COLLECTION_SOURCE == _SUBJECT_SOURCE,
            _COLLECTION_SOURCE_ID == _SUBJECT_SOURCE_ID
        ))
        .where(_COLLECTION_USER_ID == user_id)
        .group_by(_SUBJECT_TYPE)
    )
    
    logger.debug(f"构建的查询语句: {statement}")
    
    result = await db.execute(statement)
    results = result.all()
    
    logger.info(f"查询完成，获取到 {len(results)} 条结果")
    logger.debug(f"查询结果: {results}")
    
    stats = DashboardStats()
    logger.info(f"初始化 DashboardStats 对象: anime={stats.anime}, books={stats.books}, music={stats.music}, games={stats.games}, real={stats.real}, total={stats.total}")
    
    for subject_type, count in results:
        logger.debug(f"处理结果: subject_type={subject_type}, count={count}")
        if subject_type == SubjectType.ANIME:
            stats.anime = count
            logger.info(f"设置 anime 数量: {count}")
        elif subject_type == SubjectType.BOOK:
            stats.books = count
            logger.info(f"设置 books 数量: {count}")
        elif subject_type == SubjectType.MUSIC:
            stats.music = count
            logger.info(f"设置 music 数量: {count}")
        elif subject_type == SubjectType.GAME:
            stats.games = count
            logger.info(f"设置 games 数量: {count}")
        elif subject_type == SubjectType.REAL:
            stats.real = count
            logger.info(f"设置 real 数量: {count}")
        else:
            logger.warning(f"未知的 subject_type: {subject_type}")
    
    # 计算总收藏数量
    stats.total = stats.anime + stats.books + stats.music + stats.games + stats.real
    logger.info(f"计算总收藏数量: {stats.total}")
    
    logger.info(f"完成获取用户统计数据: user_id={user_id}, 结果: anime={stats.anime}, books={stats.books}, music={stats.music}, games={stats.games}, real={stats.real}, total={stats.total}")
    
    return stats


def _effective_subject_type():
    """Use the denormalized collection type, falling back to Subject.type."""
    return func.coalesce(func.nullif(Collection.subject_type, 0), Subject.type)


def _subject_tag_names(meta_tags, tags) -> set[str]:
    """Extract and normalize subject tags without trusting model-provided data."""
    candidates = meta_tags if isinstance(meta_tags, list) else []
    if not candidates and isinstance(tags, list):
        candidates = tags

    names: set[str] = set()
    for tag in candidates:
        value = tag.get("name") if isinstance(tag, dict) else tag
        if isinstance(value, str):
            normalized = value.strip()
            if normalized:
                names.add(normalized)
    return names


async def get_collection_statistics(
    user_id: int,
    db: AsyncSession,
    subject_type: int = int(SubjectType.ANIME),
) -> CollectionStatistics:
    """Aggregate collection statistics in the backend for one trusted user.

    ``Subject.meta_tags`` and ``Subject.tags`` are the repository's current
    tag sources. There is no standalone Genre table, so ``top_genres`` is a
    deterministic, per-subject tag frequency rather than an inferred genre
    taxonomy.
    """
    effective_type = _effective_subject_type()
    join_condition = and_(
        _COLLECTION_SOURCE == _SUBJECT_SOURCE,
        _COLLECTION_SOURCE_ID == _SUBJECT_SOURCE_ID,
    )
    filters = [_COLLECTION_USER_ID == user_id, effective_type == subject_type]

    status_statement = (
        select(_COLLECTION_TYPE, func.count(_COLLECTION_ID))
        .select_from(Collection)
        .outerjoin(Subject, join_condition)
        .where(*filters)
        .group_by(_COLLECTION_TYPE)
    )
    status_result = await db.execute(status_statement)

    status_counts = CollectionStatusCounts()
    status_fields = {
        CollectionStatus.WISH: "wish",
        CollectionStatus.COLLECT: "watched",
        CollectionStatus.DO: "watching",
        CollectionStatus.ON_HOLD: "on_hold",
        CollectionStatus.DROPPED: "dropped",
    }
    for status, count in status_result.all():
        field_name = status_fields.get(CollectionStatus(int(status)))
        if field_name is not None:
            setattr(status_counts, field_name, int(count))

    detail_statement = (
        select(
            _COLLECTION_SOURCE,
            _COLLECTION_SOURCE_ID,
            _SUBJECT_META_TAGS,
            _SUBJECT_TAGS,
        )
        .select_from(Collection)
        .outerjoin(Subject, join_condition)
        .where(*filters)
    )
    detail_result = await db.execute(detail_statement)
    tag_counts: Counter[str] = Counter()
    seen_subjects: set[tuple[str, str]] = set()
    tagged_subject_count = 0
    total = 0

    for source, source_id, meta_tags, tags in detail_result.all():
        total += 1
        key = (str(source), str(source_id))
        if key in seen_subjects:
            continue
        seen_subjects.add(key)
        names = _subject_tag_names(meta_tags, tags)
        if names:
            tagged_subject_count += 1
            tag_counts.update(names)

    top_genres = [
        CollectionGenreCount(name=name, count=count)
        for name, count in sorted(
            tag_counts.items(), key=lambda item: (-item[1], item[0])
        )[:3]
    ]

    return CollectionStatistics(
        subject_type=int(subject_type),
        total=total,
        status_counts=status_counts,
        top_genres=top_genres,
        complete=True,
        genre_subject_count=tagged_subject_count,
        genre_complete=tagged_subject_count == total,
    )
