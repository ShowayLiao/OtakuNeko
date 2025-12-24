from sqlmodel import SQLModel, Field
from datetime import datetime
from typing import Optional


class User(SQLModel, table=True):
    """
    用户模型
    """
    id: Optional[int] = Field(default=None, primary_key=True, description="用户ID")
    username: str = Field(unique=True, index=True, description="用户名")
    nickname: str = Field(description="昵称")
    email: str = Field(unique=True, nullable=True, description="邮箱")
    avatar_url: Optional[str] = Field(default=None, description="头像URL")
    created_at: datetime = Field(default_factory=datetime.now, description="创建时间")
    updated_at: datetime = Field(default_factory=datetime.now, description="更新时间")

    __tablename__ = "user"
