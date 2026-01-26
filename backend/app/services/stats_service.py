from sqlalchemy import func, select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi_cache.decorator import cache

from app.models import Collection, Subject, SubjectType
from app.schemas.dashboard import DashboardStats


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
    statement = (
        select(Subject.type, func.count(Collection.source_id))
        .join(Collection, and_(
            Collection.source == Subject.source,
            Collection.source_id == Subject.source_id
        ))
        .where(Collection.user_id == user_id)
        .group_by(Subject.type)
    )
    
    result = await db.execute(statement)
    results = result.all()
    
    stats = DashboardStats()
    
    for subject_type, count in results:
        if subject_type == SubjectType.ANIME:
            stats.anime = count
        elif subject_type == SubjectType.BOOK:
            stats.book = count
        elif subject_type == SubjectType.MUSIC:
            stats.music = count
        elif subject_type == SubjectType.GAME:
            stats.game = count
        elif subject_type == SubjectType.REAL:
            stats.real = count
    
    return stats
