from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from app.models.enums import CollectionStatus


class SubjectSchema(BaseModel):
    """
    条目信息Schema
    """
    id: int
    name: str
    name_cn: Optional[str] = None
    cover_url: str
    type: int
    eps: Optional[int] = None
    volumes: Optional[int] = None
    platform: Optional[str] = None
    score: Optional[float] = None
    rank: Optional[int] = None
    tags: List[str] = Field(default_factory=list)
    summary: Optional[str] = None
    date: Optional[str] = None

    class Config:
        from_attributes = True


class CollectionItemSchema(BaseModel):
    """
    收藏条目Schema
    """
    id: int                # Collection ID
    updated_at: datetime
    status: str            # 转换回 'watching' 等字符串
    rate: Optional[int] = None   # 用户评分
    comment: Optional[str] = None
    private: bool = False
    tags: List[str] = Field(default_factory=list)
    # 嵌套的条目信息
    subject: SubjectSchema # 包含 name_cn, cover_url, tags, eps 等

    class Config:
        from_attributes = True


class CollectionListResponse(BaseModel):
    """
    收藏列表分页响应Schema
    """
    total: int
    items: List[CollectionItemSchema]


class CollectionUpdate(BaseModel):
    """
    用于接收收藏更新请求的Schema
    """
    status: Optional[CollectionStatus] = Field(
        None, description="收藏状态 (1=想看/2=看过/3=在看/4=搁置/5=抛弃)"
    )
    rate: Optional[int] = Field(
        None, ge=0, le=10, description="用户评分 (0-10)"
    )
    comment: Optional[str] = Field(
        None, max_length=500, description="用户评论"
    )
    private: Optional[bool] = Field(
        None, description="是否私有收藏"
    )
    tags: Optional[List[str]] = Field(
        None, description="用户自定义标签列表"
    )


class CollectionOut(BaseModel):
    """
    用于返回收藏信息的Schema
    """
    subject_id: int
    status: Optional[CollectionStatus] = None
    rate: Optional[int] = None
    comment: Optional[str] = None
    private: bool = False
    tags: List[str] = Field(default_factory=list)
    updated_at: Optional[str] = None
    subject: Optional[dict] = None

    class Config:
        from_attributes = True