from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING, List
from sqlmodel import SQLModel, Field, Relationship

if TYPE_CHECKING:
    from .schedule import Schedule


def utc_now():
    """获取当前 UTC 时间，返回不带时区信息的datetime对象"""
    return datetime.utcnow()


class User(SQLModel, table=True):
    """
    用户模型
    """
    __tablename__ = "users"
    
    id: Optional[int] = Field(default=None, primary_key=True, description="用户ID")
    username: str = Field(unique=True, index=True, description="用户名")
    avatar_url: Optional[str] = Field(default=None, description="头像URL")
    bangumi_id: Optional[int] = Field(default=None, index=True, description="Bangumi ID")
    bangumi_name: Optional[str] = Field(default=None, description="Bangumi 用户名")
    sign: Optional[str] = Field(default=None, description="个性签名")
    created_at: datetime = Field(default_factory=utc_now, description="创建时间")
    
