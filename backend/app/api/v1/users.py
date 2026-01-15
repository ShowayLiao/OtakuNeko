from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_session
from app.models.user import User
from app.api.deps import get_current_user

router = APIRouter(prefix="/users", tags=["Users"])


@router.get("/me")
async def get_current_user_endpoint(
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """
    获取当前登录用户信息
    
    Args:
        current_user: 当前认证用户
        db: 数据库会话
        
    Returns:
        当前用户信息
        
    Raises:
        HTTPException: 当获取用户信息失败时返回 500 错误
    """
    try:
        return {
            "id": current_user.id,
            "username": current_user.username,
            "nickname": current_user.nickname,
            "email": current_user.email,
            "avatar_url": current_user.avatar_url,
            "bangumi_id": current_user.bangumi_id,
            "sign": current_user.sign,
            "created_at": current_user.created_at
        }
        
    except Exception as e:
        import traceback
        print(f"[获取当前用户信息] 错误: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"获取当前用户信息失败: {str(e)}")



