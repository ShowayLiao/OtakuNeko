from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_session
from app.models.user import User
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime

router = APIRouter(prefix="/users", tags=["Users"])


class LocalUserRegisterRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=50, description="用户名")
    has_bangumi_account: bool = Field(False, description="是否有 Bangumi 账号")
    bangumi_id: Optional[int] = Field(None, description="Bangumi ID（如果有账号）")
    avatar: Optional[str] = Field(None, description="头像 Base64 字符串（可选）")


class LocalUserRegisterResponse(BaseModel):
    id: int
    username: str
    email: Optional[str]
    avatar_url: Optional[str]
    bangumi_id: Optional[int]
    created_at: datetime


class UserCheckResponse(BaseModel):
    found: bool
    user: Optional[dict] = None


@router.post("/register-local", response_model=LocalUserRegisterResponse)
async def register_local_user(
    data: LocalUserRegisterRequest,
    db: AsyncSession = Depends(get_session)
):
    """
    注册本地用户（不绑定 Bangumi 账号）
    
    采用"存在即登录"策略：
    - 如果用户名已存在且是本地用户（bangumi_id 为空），直接返回该用户信息
    - 如果用户名已存在但已绑定 Bangumi，提示需通过 Bangumi 登录
    - 如果用户名不存在，创建新用户
    
    Args:
        data: 本地用户注册数据
        db: 数据库会话
        
    Returns:
        用户信息（新注册或已存在的本地用户）
        
    Raises:
        HTTPException: 当用户名已绑定 Bangumi 时返回 400 错误
    """
    try:
        # 检查用户名是否已存在
        existing_user_res = await db.execute(
            select(User).where(User.username == data.username)
        )
        existing_user = existing_user_res.scalars().first()
        
        if existing_user:
            # 用户名已存在，检查是否是本地用户
            if existing_user.bangumi_id is None:
                # 是本地用户，执行更新逻辑 (Upsert)
                print(f"[本地用户注册] 用户 '{data.username}' 已存在，检查是否需要更新")
                
                update_needed = False
                
                # 覆盖 Bangumi ID (如果请求中提供了)
                if data.bangumi_id is not None and existing_user.bangumi_id != data.bangumi_id:
                    existing_user.bangumi_id = data.bangumi_id
                    update_needed = True
                    print(f"[本地用户注册] 更新 bangumi_id: {existing_user.bangumi_id} -> {data.bangumi_id}")
                
                # 覆盖头像 (如果请求中提供了)
                if data.avatar and existing_user.avatar_url != data.avatar:
                    existing_user.avatar_url = data.avatar
                    update_needed = True
                    print(f"[本地用户注册] 更新 avatar_url")
                
                # 如果有变动，提交更新
                if update_needed:
                    db.add(existing_user)
                    await db.commit()
                    await db.refresh(existing_user)
                    print(f"[本地用户注册] 用户 '{data.username}' 信息已更新")
                else:
                    print(f"[本地用户注册] 用户 '{data.username}' 信息无需更新")
                
                return LocalUserRegisterResponse(
                    id=existing_user.id,
                    username=existing_user.username,
                    email=existing_user.email,
                    avatar_url=existing_user.avatar_url,
                    bangumi_id=existing_user.bangumi_id,
                    created_at=existing_user.created_at
                )
            else:
                # 已绑定 Bangumi，提示需通过 Bangumi 登录
                raise HTTPException(
                    status_code=400,
                    detail=f"用户名 '{data.username}' 已绑定 Bangumi 账号，请通过 Bangumi 登录"
                )
        
        # 处理 bangumi_id：根据用户是否有 Bangumi 账号决定
        final_bangumi_id = None
        if data.has_bangumi_account:
            # 用户有 Bangumi 账号，使用提供的 bangumi_id
            final_bangumi_id = data.bangumi_id
        else:
            # 用户没有 Bangumi 账号，bangumi_id 为 None
            final_bangumi_id = None
        
        # 创建新用户
        new_user = User(
            username=data.username,
            nickname=data.username,
            email=None,
            avatar_url=data.avatar,
            bangumi_id=final_bangumi_id,
            sign="本地用户"
        )
        
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
        
        print(f"[本地用户注册] 新用户 '{data.username}' 注册成功，ID: {new_user.id}, bangumi_id: {final_bangumi_id}")
        
        return LocalUserRegisterResponse(
            id=new_user.id,
            username=new_user.username,
            email=new_user.email,
            avatar_url=new_user.avatar_url,
            bangumi_id=new_user.bangumi_id,
            created_at=new_user.created_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        import traceback
        print(f"[本地用户注册] 错误: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"注册失败: {str(e)}")


@router.get("/info")
async def get_user_info(
    username: str = Query(..., description="用户名"),
    db: AsyncSession = Depends(get_session)
):
    """
    获取用户信息
    
    Args:
        username: 用户名
        db: 数据库会话
        
    Returns:
        用户信息
        
    Raises:
        HTTPException: 当用户不存在时返回 404 错误
    """
    try:
        user_res = await db.execute(
            select(User).where(User.username == username)
        )
        user = user_res.scalars().first()
        
        if not user:
            raise HTTPException(
                status_code=404,
                detail=f"用户 '{username}' 不存在"
            )
        
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "avatar_url": user.avatar_url,
            "bangumi_id": user.bangumi_id,
            "sign": user.sign,
            "created_at": user.created_at
        }
        
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        print(f"[获取用户信息] 错误: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"获取用户信息失败: {str(e)}")


@router.get("/check", response_model=UserCheckResponse)
async def check_user_exists(
    username: str = Query(..., description="用户名"),
    db: AsyncSession = Depends(get_session)
):
    """
    检查用户是否存在并返回基本信息
    
    Args:
        username: 用户名
        db: 数据库会话
        
    Returns:
        UserCheckResponse: 包含 found 标志和用户信息（如果存在）
    """
    try:
        user_res = await db.execute(
            select(User).where(User.username == username)
        )
        user = user_res.scalars().first()
        
        if not user:
            print(f"[检查用户] 用户 '{username}' 不存在")
            return UserCheckResponse(found=False)
        
        print(f"[检查用户] 用户 '{username}' 存在，ID: {user.id}, bangumi_id: {user.bangumi_id}")
        
        return UserCheckResponse(
            found=True,
            user={
                "id": user.id,
                "username": user.username,
                "nickname": user.nickname,
                "email": user.email,
                "avatar_url": user.avatar_url,
                "bangumi_id": user.bangumi_id,
                "sign": user.sign,
                "created_at": user.created_at.isoformat() if user.created_at else None
            }
        )
        
    except Exception as e:
        import traceback
        print(f"[检查用户] 错误: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"检查用户失败: {str(e)}")
