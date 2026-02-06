from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class UserBase(BaseModel):
    """
    用户基础信息Schema
    
    包含用户的可修改基础信息字段
    """
    username: str = Field(..., description="用户名")
    avatar_url: Optional[str] = Field(default=None, description="头像URL")
    bangumi_id: Optional[int] = Field(default=None, description="Bangumi ID")
    bangumi_name: Optional[str] = Field(default=None, description="Bangumi 用户名")
    sign: Optional[str] = Field(default=None, description="个性签名")

    class Config:
        from_attributes = True


class UserCreate(UserBase):
    """
    用户创建Schema
    
    用于创建新用户，继承自 UserBase
    """
    pass


class UserUpdate(BaseModel):
    """
    用户更新Schema
    
    用于更新用户资料，所有字段均为可选
    """
    username: Optional[str] = Field(None, description="用户名")
    avatar_url: Optional[str] = Field(None, description="头像URL")
    bangumi_id: Optional[int] = Field(None, description="Bangumi ID")
    bangumi_name: Optional[str] = Field(None, description="Bangumi 用户名")
    sign: Optional[str] = Field(None, description="个性签名")

    class Config:
        from_attributes = True


class UserRead(UserBase):
    """
    用户读取Schema
    
    用于返回用户信息，继承自 UserBase，增加只读字段
    """
    id: int = Field(..., description="用户ID")
    created_at: datetime = Field(..., description="创建时间")

    class Config:
        from_attributes = True


class UserList(BaseModel):
    """
    用户列表分页响应Schema
    
    用于返回分页的用户列表，包含总数和用户列表
    """
    total: int = Field(..., description="总记录数")
    items: List[UserRead] = Field(default_factory=list, description="用户列表")


class UserSearch(BaseModel):
    """
    用户搜索Schema
    
    用于搜索用户，包含分页参数
    """
    skip: Optional[int] = Field(default=0, description="跳过的记录数")
    limit: Optional[int] = Field(default=100, description="返回的最大记录数")


class UserLogin(BaseModel):
    """
    用户登录Schema
    
    用于用户登录，包含用户名和其他登录数据
    """
    username: str = Field(..., description="用户名")
    avatar_url: Optional[str] = Field(default=None, description="头像URL")
    bangumi_id: Optional[int] = Field(default=None, description="Bangumi ID")
    bangumi_name: Optional[str] = Field(default=None, description="Bangumi 用户名")
    sign: Optional[str] = Field(default=None, description="个性签名")


class BangumiAvatar(BaseModel):
    """
    Bangumi用户头像Schema
    
    用于表示Bangumi用户的头像信息
    """
    large: str = Field(..., description="大尺寸头像URL")
    medium: str = Field(..., description="中尺寸头像URL")
    small: str = Field(..., description="小尺寸头像URL")


class BangumiUserInfo(BaseModel):
    """
    Bangumi用户信息Schema
    
    用于表示从Bangumi API返回的用户信息
    """
    avatar: BangumiAvatar = Field(..., description="用户头像信息")
    sign: Optional[str] = Field(default=None, description="用户签名")
    url: str = Field(..., description="用户个人页面URL")
    username: str = Field(..., description="用户名")
    nickname: str = Field(..., description="用户昵称")
    id: int = Field(..., description="用户ID")
    user_group: int = Field(..., description="用户组")
