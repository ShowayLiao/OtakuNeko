from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.database import get_session
from app.models.user import User
from app.core.security import decode_access_token

security = HTTPBearer()


async def get_current_user(
    token_auth: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_session)
) -> User:
    """
    获取当前认证用户
    
    Args:
        token_auth: HTTP Authorization凭据
        db: 数据库会话
        
    Returns:
        当前认证的用户对象
        
    Raises:
        HTTPException: 当令牌无效或用户不存在时返回 401 错误
    """
    token = token_auth.credentials
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="无法验证凭据",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    payload = decode_access_token(token)
    if payload is None:
        print("[DEBUG] decode_access_token returned None")
        raise credentials_exception
    
    print(f"[DEBUG] JWT payload: {payload}")
    
    user_id_str: Optional[str] = payload.get("sub")
    if user_id_str is None:
        print("[DEBUG] payload.get('sub') returned None")
        raise credentials_exception
    
    print(f"[DEBUG] user_id_str: {user_id_str}, type: {type(user_id_str)}")
    
    # 将字符串类型的 user_id 转换为整数类型
    try:
        user_id = int(user_id_str)
        print(f"[DEBUG] user_id after conversion: {user_id}, type: {type(user_id)}")
    except ValueError as e:
        print(f"[DEBUG] ValueError when converting user_id_str to int: {e}")
        raise credentials_exception
    
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalars().first()
    
    if user is None:
        raise credentials_exception
    
    return user
