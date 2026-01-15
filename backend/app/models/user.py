from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING
from sqlmodel import SQLModel, Field, Relationship


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
    nickname: str = Field(description="昵称")
    email: Optional[str] = Field(default=None, unique=True, nullable=True, description="邮箱")
    avatar_url: Optional[str] = Field(default=None, description="头像URL")
    bangumi_id: Optional[int] = Field(default=None, index=True, description="Bangumi ID")
    sign: Optional[str] = Field(default=None, description="个性签名")
    created_at: datetime = Field(default_factory=utc_now, description="创建时间")
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column_kwargs={"onupdate": utc_now},
        description="更新时间"
    )
    
    if TYPE_CHECKING:
        from .collection import Collection
        collections: list["Collection"] = Relationship(back_populates="user")
