from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_session
from app.api.deps import get_current_user
from app.services.user_service import UserService
from app.schemas.user import UserRead, UserUpdate

router = APIRouter(prefix="/users", tags=["Users"])


class UserCheckResponse(BaseModel):
    """用户检查响应Schema"""
    exists: bool = Field(..., description="用户是否存在")
    avatar_url: str | None = Field(default=None, description="用户头像URL")
    username: str | None = Field(default=None, description="用户名")


@router.get("/me", response_model=UserRead)
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
        user = await UserService.get_user_by_id(db, current_user.id)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[获取当前用户信息] 错误: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"获取当前用户信息失败: {str(e)}")


@router.put("/me", response_model=UserRead)
async def update_current_user_endpoint(
    user_data: UserUpdate,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """
    更新当前用户信息
    
    Args:
        user_data: 用户更新数据
        current_user: 当前认证用户
        db: 数据库会话
        
    Returns:
        更新后的用户信息
        
    Raises:
        HTTPException: 当更新用户信息失败时返回错误
    """
    try:
        updated_user = await UserService.update_user(db, current_user.id, user_data)
        if not updated_user:
            raise HTTPException(status_code=404, detail="用户不存在")
        return updated_user
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[更新当前用户信息] 错误: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"更新当前用户信息失败: {str(e)}")


@router.delete("/me", status_code=204)
async def delete_current_user_endpoint(
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """
    删除当前用户
    
    Args:
        current_user: 当前认证用户
        db: 数据库会话
        
    Returns:
        None
        
    Raises:
        HTTPException: 当删除用户失败时返回错误
    """
    try:
        deleted = await UserService.delete_user(db, current_user.id)
        if not deleted:
            raise HTTPException(status_code=404, detail="用户不存在")
        return None
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[删除当前用户] 错误: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"删除当前用户失败: {str(e)}")


@router.get("/username/{username}", response_model=UserRead)
async def get_user_by_username_endpoint(
    username: str,
    db: AsyncSession = Depends(get_session)
):
    """
    根据用户名获取用户信息
    
    Args:
        username: 用户名
        db: 数据库会话
        
    Returns:
        用户信息
        
    Raises:
        HTTPException: 当获取用户信息失败时返回错误
    """
    try:
        user = await UserService.get_user_by_username(db, username)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        return user
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[根据用户名获取用户信息] 错误: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"获取用户信息失败: {str(e)}")


@router.get("/check-user", response_model=UserCheckResponse)
async def check_user_endpoint(
    username: str,
    db: AsyncSession = Depends(get_session)
):
    """
    检查用户是否存在
    
    Args:
        username: 用户名
        db: 数据库会话
        
    Returns:
        用户检查结果
    """
    try:
        user = await UserService.get_user_by_username(db, username)
        if user:
            return UserCheckResponse(
                exists=True,
                avatar_url=user.avatar_url,
                username=user.username
            )
        return UserCheckResponse(exists=False)
        
    except Exception as e:
        import traceback
        print(f"[检查用户] 错误: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"检查用户失败: {str(e)}")






