from typing import Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.database import get_session
from app.models.user import User
from app.schemas.user import UserRead
from app.core.security import decode_access_token
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger(__name__)

security = HTTPBearer()
optional_security = HTTPBearer(auto_error=False)


async def get_current_user(
    token_auth: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_session)
) -> UserRead:
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
        logger.debug("decode_access_token returned None")
        raise credentials_exception
    
    logger.debug(f"JWT payload: {payload}")
    
    user_id_str: Optional[str] = payload.get("sub")
    if user_id_str is None:
        logger.debug("payload.get('sub') returned None")
        raise credentials_exception
    
    logger.debug(f"user_id_str: {user_id_str}")
    
    try:
        user_id = int(user_id_str)
        logger.debug(f"user_id after conversion: {user_id}")
    except ValueError as e:
        logger.debug(f"ValueError converting user_id_str: {e}")
        raise credentials_exception
    
    result = await db.execute(
        select(User).where(User.id == user_id)
    )
    user = result.scalars().first()
    
    if user is None:
        raise credentials_exception
    
    return UserRead.model_validate(user)


def check_qb_enabled():
    """
    检查 QBittorrent 代理是否启用
    
    Returns:
        None
        
    Raises:
        HTTPException: 当 ENABLE_QB_PROXY 为 false 时返回 403 错误
    """
    if not settings.ENABLE_QB_PROXY:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="QBittorrent proxy is disabled",
        )


async def get_optional_user(
    token_auth: Optional[HTTPAuthorizationCredentials] = Depends(optional_security),
    db: AsyncSession = Depends(get_session)
) -> Optional[UserRead]:
    if token_auth is None:
        return None
    token = token_auth.credentials
    payload = decode_access_token(token)
    if payload is None:
        return None
    user_id_str = payload.get("sub")
    if user_id_str is None:
        return None
    try:
        user_id = int(user_id_str)
    except ValueError:
        return None
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalars().first()
    if user is None:
        return None
    return UserRead.model_validate(user)
