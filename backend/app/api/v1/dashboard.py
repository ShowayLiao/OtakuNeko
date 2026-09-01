from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_session
from app.models import SubjectType
from app.services.stats_service import (
    get_collection_statistics as get_collection_statistics_service,
    get_user_stats,
)
from app.schemas.dashboard import CollectionStatistics, DashboardStats
from app.api.deps import get_current_user
from app.core.logging import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/stats", response_model=DashboardStats)
async def get_user_stats_endpoint(
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """
    获取用户的仪表板统计数据
    
    返回用户在不同分类（动画/书籍/游戏/音乐/三次元）下的收藏总数
    数据缓存 10 分钟，减少数据库查询压力
    
    Args:
        current_user: 当前认证用户
        db: 数据库会话
    
    Returns:
        DashboardStats 对象，包含各分类的收藏数量
    
    Raises:
        HTTPException: 当获取统计数据失败时返回 500 错误
    """
    try:
        stats = await get_user_stats(current_user.id, db)
        
        return stats
        
    except Exception as e:
        logger.error(f"Failed to get user stats: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"获取用户统计数据失败: {str(e)}")


@router.get("/collection-statistics", response_model=CollectionStatistics)
async def get_collection_statistics_endpoint(
    subject_type: SubjectType = Query(SubjectType.ANIME),
    current_user=Depends(get_current_user),
    db: AsyncSession = Depends(get_session),
):
    """Return complete, database-backed collection statistics for the user."""
    try:
        return await get_collection_statistics_service(
            current_user.id,
            db,
            subject_type=int(subject_type),
        )
    except Exception as exc:
        logger.error("Failed to get collection statistics", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="获取收藏统计数据失败",
        ) from exc
