from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from app.models.enums import CollectionStatus


class SubjectSchema(BaseModel):
    """
    条目信息Schema
    """
    id: int
    source_id: str
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


class SubjectWithUserStatus(SubjectSchema):
    """
    带用户收藏状态的条目信息Schema
    用于搜索结果，返回条目信息以及当前用户是否已收藏
    """
    is_collected: bool = Field(default=False, description="当前用户是否已收藏该条目")
    collection_info: Optional["CollectionOut"] = Field(default=None, description="收藏信息，如果已收藏则返回")

    class Config:
        from_attributes = True


class CollectionItemSchema(BaseModel):
    """
    收藏条目Schema
    """
    subject_id: int        # 条目ID
    updated_at: str        # ISO 8601 格式的日期时间字符串
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
    status: Optional[str] = None
    rate: Optional[int] = None
    comment: Optional[str] = None
    private: bool = False
    tags: List[str] = Field(default_factory=list)
    updated_at: Optional[str] = None
    subject: Optional[dict] = None

    class Config:
        from_attributes = True


class ManualCollectionCreate(BaseModel):
    """
    手动添加收藏的请求Schema
    """
    name: str = Field(..., description="条目标题", min_length=1, max_length=200)
    type: int = Field(..., description="条目类型 (1=书籍/2=动画/3=音乐/4=游戏/6=三次元)", ge=1, le=6)
    status: int = Field(..., description="收藏状态 (1=想看/2=看过/3=在看/4=搁置/5=抛弃)", ge=1, le=5)
    cover_url: str = Field(default="", description="封面图片URL")
    rate: int = Field(default=0, description="用户评分 (0-10)", ge=0, le=10)
    comment: str = Field(default="", description="用户评论", max_length=500)
    release_date: str = Field(default="", description="上映日期 (YYYY-MM-DD)")
    publish_date: str = Field(default="", description="发售日期 (YYYY-MM-DD)")
    tags: str = Field(default="", description="标签 (逗号分隔字符串)")