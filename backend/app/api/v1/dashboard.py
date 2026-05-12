from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_session
from app.services.stats_service import get_user_stats
from app.schemas.dashboard import DashboardStats
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

