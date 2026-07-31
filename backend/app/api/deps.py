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


def _parse_qb_allowed_user_ids(raw_value: str) -> set[int] | None:
    """Parse the server-owned qB allowlist, returning None for invalid config."""
    if not raw_value.strip():
        return set()

    tokens = [token.strip() for token in raw_value.split(",")]
    parsed_ids: set[int] = set()
    for token in tokens:
        if not token or not token.isascii() or not token.isdecimal():
            return None
        try:
            user_id = int(token)
        except ValueError:
            return None
        if user_id <= 0:
            return None
        parsed_ids.add(user_id)
    return parsed_ids


def check_qb_access(
    user: UserRead = Depends(get_current_user),
) -> None:
    """Require an authenticated user explicitly allowed to use the qB proxy."""
    check_qb_enabled()
    allowed_user_ids = _parse_qb_allowed_user_ids(settings.QB_ALLOWED_USER_IDS)
    if (
        allowed_user_ids is None
        or not allowed_user_ids
        or user.id not in allowed_user_ids
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="QBittorrent access is not authorized",
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
