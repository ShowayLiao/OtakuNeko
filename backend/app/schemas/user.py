from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class UserBase(BaseModel):
    """
    用户基础信息Schema
    
    包含用户的可修改基础信息字段
    """
    nickname: Optional[str] = Field(None, description="昵称")
    email: Optional[str] = Field(None, description="邮箱")
    avatar_url: Optional[str] = Field(None, description="头像URL")
    sign: Optional[str] = Field(None, description="个性签名")
    bangumi_id: Optional[int] = Field(None, description="Bangumi ID")

    class Config:
        from_attributes = True


class UserCreate(UserBase):
    """
    用户创建Schema
    
    用于创建新用户，继承自 UserBase，增加必填字段
    """
    username: str = Field(..., description="用户名", min_length=1, max_length=50)
    has_bangumi_account: bool = Field(..., description="是否关联Bangumi账号")


class UserUpdate(UserBase):
    """
    用户更新Schema
    
    用于更新用户资料，所有字段继承自 UserBase 均为 Optional
    """
    pass


class UserRead(UserBase):
    """
    用户读取Schema
    
    用于返回用户信息，继承自 UserBase，增加只读字段
    """
    id: int = Field(..., description="用户ID")
    username: str = Field(..., description="用户名")
    created_at: datetime = Field(..., description="创建时间")
    updated_at: datetime = Field(..., description="更新时间")

    class Config:
        from_attributes = True
