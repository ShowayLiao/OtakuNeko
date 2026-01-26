from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from app.models.enums import CollectionStatus
from app.schemas.subject import SubjectRead


class CollectionBase(BaseModel):
    """
    收藏基础信息Schema
    
    包含收藏的所有公共字段，用于数据的存入和更新
    """
    type: CollectionStatus = Field(..., description="收藏类型：1想看/2看过/3在看/4搁置/5抛弃")
    rate: Optional[int] = Field(None, ge=0, le=10, description="用户评分 (0-10)")
    comment: Optional[str] = Field(None, max_length=500, description="用户评论")
    private: Optional[bool] = Field(default=False, description="是否私有收藏")
    tags: Optional[List[str]] = Field(None, description="用户自定义标签列表")
    source: str = Field(default="bangumi", description="数据来源：bangumi/douban")
    source_id: str = Field(..., description="原站ID（Bangumi ID或豆瓣ID）")
    vol_status: Optional[int] = Field(default=0, description="卷数状态")
    ep_status: Optional[int] = Field(default=0, description="集数状态")
    subject_type: Optional[int] = Field(default=0, description="条目类型")
    updated_at: Optional[datetime] = Field(None, description="最后更新时间")

    class Config:
        from_attributes = True


class CollectionCreate(CollectionBase):
    """
    收藏创建Schema
    
    用于创建新的收藏记录，继承自CollectionBase
    """
    user_id: int = Field(..., description="用户ID")


class CollectionUpdateBase(BaseModel):
    """
    收藏更新Schema
    
    用于更新用户收藏信息，所有字段设为 Optional，支持部分字段更新
    """
    type: Optional[CollectionStatus] = Field(None, description="收藏类型：1想看/2看过/3在看/4搁置/5抛弃")
    rate: Optional[int] = Field(None, ge=0, le=10, description="用户评分 (0-10)")
    comment: Optional[str] = Field(None, max_length=500, description="用户评论")
    private: Optional[bool] = Field(None, description="是否私有收藏")
    tags: Optional[List[str]] = Field(None, description="用户自定义标签列表")
    source: Optional[str] = Field(None, description="数据来源：bangumi/douban")
    source_id: Optional[str] = Field(None, description="原站ID（Bangumi ID或豆瓣ID）")
    vol_status: Optional[int] = Field(None, description="卷数状态")
    ep_status: Optional[int] = Field(None, description="集数状态")
    subject_type: Optional[int] = Field(None, description="条目类型")
    updated_at: Optional[datetime] = Field(None, description="最后更新时间")
    user_id: Optional[int] = Field(None, description="用户ID")

class CollectionUpdate(CollectionUpdateBase):
    """
    收藏更新Schema
    
    用于更新用户收藏信息，继承自CollectionUpdateBase
    """
    pass


class CollectionRead(CollectionBase):
    """
    收藏读取Schema
    
    用于返回收藏的详细信息，继承自 CollectionBase，增加只读字段
    """
    user_id: int = Field(..., description="用户ID")
    subject: Optional[SubjectRead] = Field(None, description="关联的条目信息")

    class Config:
        from_attributes = True


class CollectionList(BaseModel):
    """
    收藏列表分页响应Schema
    
    用于返回分页的收藏列表，包含总数和条目列表
    """
    total: int = Field(..., description="总记录数")
    items: List[CollectionBase] = Field(default_factory=list, description="收藏列表")

class CollectionUpdateList(CollectionUpdate):
    """
    收藏列表分页响应Schema
    
    用于返回分页的收藏列表，包含总数和条目列表
    """
    total: int = Field(..., description="总记录数")
    items: List[CollectionUpdate] = Field(default_factory=list, description="收藏列表")

class CollectionReadList(BaseModel):
    """
    收藏列表分页响应Schema
    
    用于返回分页的收藏列表，包含总数和条目列表
    """
    total: int = Field(..., description="总记录数")
    items: List[CollectionRead] = Field(default_factory=list, description="收藏列表")


class CollectionSearchByID(BaseModel):
    """
    收藏搜索ByIDSchema
    
    用于根据ID搜索收藏记录，包含用户ID
    """
    user_id: int = Field(..., description="用户ID")
    source: str = Field(..., description="数据来源：bangumi/douban")
    source_id: str = Field(..., description="原站ID（Bangumi ID或豆瓣ID）")

class CollectionSearchBase(BaseModel):
    """
    收藏搜索CloudSchema
    
    用于搜索Cloud数据库中的收藏记录，包含关键词、类型、数据源等参数
    """
    user_id: int = Field(..., description="用户ID")
    type: Optional[CollectionStatus] = Field(None, description="收藏类型：1想看/2看过/3在看/4搁置/5抛弃")
    skip: Optional[int] = Field(default=0, description="跳过的记录数")
    limit: int = Field(default=10, description="返回的最大记录数")

class CollectionSearchByName(CollectionSearchBase):
    """
    收藏搜索ByNameSchema`
    
    用于根据关键词搜索收藏记录，继承自CollectionSearchBase，包含关键词、数据源等参数
    """
    keyword: str = Field(..., description="搜索关键词")


class CollectionSyncRequest(BaseModel):
    """
    收藏同步请求Schema
    
    用于请求同步用户收藏数据，包含分页参数和同步选项
    """
    subject_type: Optional[int] = Field(None, description="条目类型 (1=书籍/2=动画/3=音乐/4=游戏/6=三次元)")
    limit: Optional[int] = Field(default=50, ge=1, le=100, description="每页请求数量")
    offset: Optional[int] = Field(default=0, ge=0, description="分页偏移量")
    sync_count: Optional[int] = Field(default=0, ge=0, description="已同步数量")
    data: Optional[List[Dict[str, Any]]] = Field(None, description="用于豆瓣上传的数据列表")


class CollectionUpsertRequest(BaseModel):
    """
    收藏更新/添加请求Schema
    
    用于请求更新或添加收藏，包含条目信息和收藏信息
    """
    collection: Optional[CollectionUpdate] = Field(None, description="收藏信息")
    subject: Optional[dict] = Field(None, description="条目信息")
    
    class Config:
        extra = "forbid"
