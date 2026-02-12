from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi_cache.decorator import cache

from app.models import Collection, Subject, SubjectType
from app.schemas.dashboard import DashboardStats
from app.core.logging import get_logger

logger = get_logger(__name__)


def stats_key_builder(func, namespace: str, request, *args, **kwargs):
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

@cache(expire=600, namespace="dashboard", key_builder=stats_key_builder)
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
        select(Subject.type, func.count(Collection.source_id))
        .join(Collection, and_(
            Collection.source == Subject.source,
            Collection.source_id == Subject.source_id
        ))
        .where(Collection.user_id == user_id)
        .group_by(Subject.type)
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
