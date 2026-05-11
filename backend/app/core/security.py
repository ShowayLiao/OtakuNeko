from datetime import datetime, timedelta
from typing import Optional
from jose import JWTError, jwt
from passlib.context import CryptContext
from app.core.config import settings

# 密码加密上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT 配置
SECRET_KEY = settings.JWT_SECRET_KEY
if not SECRET_KEY:
    raise ValueError(
        "JWT_SECRET_KEY is not set. "
        "Set it via environment variable or .env file. "
        "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
    )
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 7  # 7天


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """
    创建 JWT 访问令牌
    
    Args:
        data: 要编码到令牌中的数据（通常包含 user_id 和 username）
        expires_delta: 可选的过期时间增量
        
    Returns:
        JWT 令牌字符串
    """
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    
    encoded_jwt = jwt.encode(to_encode, str(SECRET_KEY), algorithm=ALGORITHM)
    return encoded_jwt


import logging

def decode_access_token(token: str) -> Optional[dict]:
    """
    解码 JWT 访问令牌
    
    Args:
        token: JWT 令牌字符串
        
    Returns:
        解码后的数据字典，如果令牌无效则返回 None
    """
    try:
        logging.debug(f"Attempting to decode token: {token[:20]}...")
        logging.debug(f"SECRET_KEY: {SECRET_KEY}, type: {type(SECRET_KEY)}")
        payload = jwt.decode(token, str(SECRET_KEY), algorithms=[ALGORITHM])
        logging.debug(f"Token decoded successfully: {payload}")
        return payload
    except JWTError as e:
        logging.error(f"JWT Error: {type(e).__name__}: {e}")
        return None


def get_password_hash(password: str) -> str:
    """
    对密码进行哈希处理
    
    Args:
        password: 明文密码
        
    Returns:
        哈希后的密码字符串
    """
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证密码是否匹配
    
    Args:
        plain_password: 明文密码
        hashed_password: 哈希后的密码
        
    Returns:
        如果密码匹配返回 True，否则返回 False
    """
    return pwd_context.verify(plain_password, hashed_password)
