from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from datetime import datetime
from app.models.enums import CollectionStatus
from .shared import BaseList, SearchBase

if TYPE_CHECKING:
    from .subject import SubjectRead


class CollectionFieldsBase(BaseModel):
    """
    收藏字段基础Schema
    
    包含收藏的所有公共字段，作为其他收藏相关类的基类
    """
    type: Optional[CollectionStatus] = Field(None, description="收藏类型：1想看/2看过/3在看/4搁置/5抛弃")
    rate: Optional[int] = Field(None, ge=0, le=10, description="用户评分 (0-10)")
    comment: Optional[str] = Field(None, max_length=500, description="用户评论")
    private: Optional[bool] = Field(default=False, description="是否私有收藏")
    tags: Optional[List[str]] = Field(None, description="用户自定义标签列表")
    vol_status: Optional[int] = Field(default=0, description="卷数状态")
    ep_status: Optional[int] = Field(default=0, description="集数状态")
    subject_type: Optional[int] = Field(default=0, description="条目类型")


class CollectionBase(CollectionFieldsBase):
    """
    收藏基础信息Schema
    
    包含收藏的所有公共字段，用于数据的存入和更新
    """
    type: CollectionStatus = Field(..., description="收藏类型：1想看/2看过/3在看/4搁置/5抛弃")
    source: str = Field(default="bangumi", pattern="^(bangumi|douban)$", description="数据来源：bangumi/douban")
    source_id: str = Field(..., min_length=1, max_length=50, description="原站ID（Bangumi ID或豆瓣ID）")
    updated_at: Optional[datetime] = Field(None, description="最后更新时间")
    

    class Config:
        from_attributes = True


class CollectionCreate(CollectionBase):
    """
    收藏创建Schema
    
    用于创建新的收藏记录，继承自CollectionBase
    """
    user_id: int = Field(..., description="用户ID")
    pass


class CollectionUpdateBase(CollectionFieldsBase):
    """
    收藏更新Schema
    
    用于更新用户收藏信息，所有字段设为 Optional，支持部分字段更新
    """
    source: Optional[str] = Field(None, description="数据来源：bangumi/douban")
    source_id: Optional[str] = Field(None, description="原站ID（Bangumi ID或豆瓣ID）")
    updated_at: Optional[datetime] = Field(None, description="最后更新时间")
    user_id: Optional[int] = Field(None, description="用户ID")


class CollectionUpdate(CollectionUpdateBase):
    """
    收藏更新Schema
    
    用于更新用户收藏信息，继承自CollectionUpdateBase
    """
    pass

class CollectionUpsertBase(CollectionFieldsBase):
    """
    收藏 Upsert Schema（唯一标识必填 + 业务字段可选）
    
    用于插入或更新：通过 (user_id, source, source_id) 定位记录，
    仅更新客户端显式提供的字段（配合 exclude_unset 使用）
    """
    # ===== 唯一标识字段（必须完整提供，不可为 None）=====
    user_id: int = Field(..., description="用户ID（唯一标识必需）")
    source: str = Field(..., description="数据来源：bangumi/douban（唯一标识必需）")
    source_id: str = Field(..., description="原站ID（Bangumi ID或豆瓣ID）（唯一标识必需）")
    
    updated_at: Optional[datetime] = Field(None, description="最后更新时间")

    class Config:
        populate_by_name = True  # 兼容别名字段（如有）
        # 注意：不要设置 from_attributes（此为输入Schema，非ORM映射）

class CollectionUpsert(CollectionUpsertBase):
    """实际用于API请求的Upsert Schema"""
    pass    



class CollectionRead(CollectionBase):
    """
    收藏读取Schema
    
    用于返回收藏的详细信息，继承自 CollectionBase，增加只读字段
    """
    user_id: int = Field(..., description="用户ID")

    class Config:
        from_attributes = True


class CollectionList(BaseList):
    """
    收藏列表分页响应Schema
    
    用于返回分页的收藏列表，包含总数和条目列表
    """
    items: List[CollectionBase] = Field(default_factory=list, description="收藏列表")

class CollectionUpdateList(BaseList):
    """
    收藏更新列表分页响应Schema
    
    用于返回分页的收藏更新列表，包含总数和条目列表
    """
    items: List[CollectionUpdate] = Field(default_factory=list, description="收藏列表")

class CollectionReadList(BaseList):
    """
    收藏读取列表分页响应Schema
    
    用于返回分页的收藏读取列表，包含总数和条目列表
    """
    items: List[CollectionRead] = Field(default_factory=list, description="收藏列表")


class CollectionSearchByID(BaseModel):
    """
    收藏搜索ByIDSchema
    
    用于根据ID搜索收藏记录，包含用户ID
    """
    user_id: int = Field(..., description="用户ID")
    source: str = Field(..., description="数据来源：bangumi/douban")
    source_id: str = Field(..., description="原站ID（Bangumi ID或豆瓣ID）")

class CollectionSearchBase(SearchBase):
    """
    收藏搜索CloudSchema
    
    用于搜索Cloud数据库中的收藏记录，包含关键词、类型、数据源等参数
    """
    user_id: int = Field(..., description="用户ID")
    status: Optional[CollectionStatus] = Field(None, description="收藏状态：1想看/2看过/3在看/4搁置/5抛弃")
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
    subject: Optional[Dict[str, Any]] = Field(None, description="条目信息")
    
    class Config:
        extra = "forbid"

class CollectionCreateList(BaseList):
    """
    收藏创建列表Schema
    
    用于创建多个收藏记录，包含多个CollectionCreate对象
    """
    collections: List[CollectionCreate] = Field(default_factory=list, description="收藏列表")


class CollectionUpsertList(BaseList):
    """
    收藏插入或更新列表Schema
    
    用于插入或更新多个收藏记录，包含多个CollectionUpsert对象
    """
    collections: List[CollectionUpsert] = Field(default_factory=list, description="收藏列表")


class CollectionSubject(CollectionBase):
    """
    收藏读取Schema
    
    用于返回收藏的详细信息，继承自 CollectionBase，增加只读字段
    """
    user_id: int = Field(..., description="用户ID")
    subject: Optional['SubjectRead'] = Field(None, description="关联的条目信息")

    class Config:
        from_attributes = True


class CollectionSubjectList(CollectionList):
    """
    收藏列表分页响应Schema
    
    用于返回分页的收藏列表，包含总数和条目列表
    """
    total: int = Field(..., description="总记录数")
    items: List[CollectionSubject] = Field(default_factory=list, description="收藏列表")


class CollectionWithSubject(BaseModel):
    """
    收藏及其关联条目信息Schema
    
    用于返回单个收藏及其关联的条目信息
    """
    collection: CollectionRead = Field(..., description="收藏信息")
    subject: Optional['SubjectRead'] = Field(None, description="关联的条目信息")

    class Config:
        from_attributes = True


class CollectionWithSubjectList(BaseList):
    """
    收藏及其关联条目信息列表Schema
    
    用于返回收藏及其关联条目信息的列表
    """
    items: List[CollectionWithSubject] = Field(default_factory=list, description="收藏及其关联条目信息列表")


# 解决循环引用问题
if not TYPE_CHECKING:
    from .subject import SubjectRead
    CollectionWithSubject.model_rebuild()
    CollectionSubject.model_rebuild()