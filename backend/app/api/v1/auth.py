from fastapi import APIRouter, Depends, HTTPException
from typing import Optional
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_session
from app.models.user import User
from app.core.security import create_access_token
from app.services.user_service import UserService
from app.schemas.user import UserLogin

router = APIRouter(prefix="/auth", tags=["Auth"])


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50, description="用户名")
    nickname: Optional[str] = Field(None, max_length=100, description="用户昵称")
    bangumi_id: Optional[int] = Field(None, description="第三方平台ID")
    bangumi_name: Optional[str] = Field(None, max_length=50, description="Bangumi 用户名")
    avatar_url: Optional[str] = Field(None, max_length=255, description="头像图片URL")
    sign: Optional[str] = Field(None, max_length=200, description="用户签名/个性签名")
    
    class Config:
        extra = "forbid"


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: dict


@router.post("/login", response_model=LoginResponse)
async def login(
    data: LoginRequest,
    db: AsyncSession = Depends(get_session)
):
    """
    用户登录/注册/信息更新综合接口
    
    采用智能判断策略：
    - 如果用户名不存在：自动创建新用户，使用请求中的可选字段（如果提供），否则使用默认值
    - 如果用户名已存在：选择性更新非空且变更的字段
    
    Args:
        data: 登录请求数据，包含 username 和可选的补充信息
        db: 数据库会话
        
    Returns:
        包含 JWT 访问令牌和用户完整信息的响应
        
    Raises:
        HTTPException: 当数据库操作失败时返回 500 错误
    """
    try:
        # 将 LoginRequest 转换为 UserLogin
        login_data = UserLogin(
            username=data.username,
            avatar_url=data.avatar_url,
            bangumi_id=data.bangumi_id,
            bangumi_name = data.bangumi_name,
            sign=data.sign
        )
        
        # 调用 UserService.login_user 方法
        user = await UserService.login_user(db, login_data)
        
        # 生成 token
        token = create_access_token(data={"sub": str(user.id), "username": user.username})
        
        # 构建用户信息响应
        user_info = {
            "id": user.id,
            "username": user.username,
            "avatar_url": user.avatar_url,
            "bangumi_id": user.bangumi_id,
            "bangumi_name": user.bangumi_name,
            "sign": user.sign,
            "created_at": user.created_at
        }
        
        # 返回统一格式响应
        return LoginResponse(
            access_token=token,
            token_type="bearer",
            user=user_info
        )
            
    except Exception as e:
        await db.rollback()
        import traceback
        print(f"[登录] 错误: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"登录失败: {str(e)}")
