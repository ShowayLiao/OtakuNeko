from pydantic import BaseModel, Field, model_validator
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from datetime import datetime, time
from app.models.enums import SubjectType, CollectionStatus
from .shared import BaseList, SearchBase

if TYPE_CHECKING:
    from .collection import CollectionRead


class SubjectBase(BaseModel):
    """
    条目基础信息Schema
    
    包含条目的公共基础字段
    """
    name: str = Field(..., min_length=1, max_length=255, description="条目原名")
    name_cn: Optional[str] = Field(default="", max_length=255, description="条目中文名")
    type: SubjectType = Field(..., description="条目类型：1=书籍/2=动画/3=音乐/4=游戏/6=三次元")
    source: str = Field(default="bangumi", pattern="^(bangumi|douban)$", description="数据来源：bangumi/douban")
    source_id: str = Field(..., min_length=1, max_length=50, description="原站ID（Bangumi ID或豆瓣ID）")
    summary: Optional[str] = Field(None, description="条目简介")
    date: Optional[str] = Field(default="", description="发售/放送日期")
    platform: Optional[str] = Field(default="", description="平台/类型（如TV、小说、Switch等）")
    eps: Optional[int] = Field(default=None, description="集数（针对动画）")
    volumes: Optional[int] = Field(default=None, description="卷数（针对书籍）")
    images: Optional[Dict[str, Any]] = Field(default_factory=dict, description="图片字典（支持多尺寸图片）")
    image: Optional[str] = Field(default="", description="单个封面图片URL")
    tags: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="标签列表")
    meta_tags: Optional[List[str]] = Field(default_factory=list, description="官方元标签")
    infobox: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="详细元数据（如作者、开发商等）")
    rating: Optional[Dict[str, Any]] = Field(default_factory=dict, description="评分信息")
    collection: Optional[Dict[str, Any]] = Field(default_factory=dict, description="收藏状态统计")
    series: Optional[bool] = Field(default=False, description="是否为系列")
    locked: Optional[bool] = Field(default=False, description="是否锁定")
    nsfw: Optional[bool] = Field(default=False, description="是否不适合儿童")
    air_time: Optional[datetime] = Field(default=None, description="放送时间")
    air_weekday: Optional[int] = Field(default=None, description="放送星期 (1-7)")
    last_sync: Optional[datetime] = Field(default=None, description="最后同步时间")

    class Config:
        from_attributes = True


class SubjectCreate(SubjectBase):
    """
    条目创建Schema
    
    用于创建新的条目记录，继承自SubjectBase
    """
    pass


class SubjectRead(SubjectBase):
    """
    条目读取Schema
    
    用于返回条目基本信息，继承自 SubjectBase，增加ID
    """
    id: int = Field(..., description="数据库自增主键")

    class Config:
        from_attributes = True


class SubjectUpdate(BaseModel):
    """
    条目更新Schema
    
    用于更新条目信息，所有字段设为 Optional，支持部分字段更新
    """
    name: Optional[str] = Field(None, description="条目原名")
    name_cn: Optional[str] = Field(default="", description="条目中文名")
    type: Optional[SubjectType] = Field(None, description="条目类型：1=书籍/2=动画/3=音乐/4=游戏/6=三次元")
    source: str = Field(..., description="数据来源：bangumi/douban")
    source_id: str = Field(..., description="原站ID（Bangumi ID或豆瓣ID）")
    summary: Optional[str] = Field(None, description="条目简介")
    date: Optional[str] = Field(None, description="发售/放送日期")
    platform: Optional[str] = Field(None, description="平台/类型（如TV、小说、Switch等）")
    eps: Optional[int] = Field(None, description="集数（针对动画）")
    volumes: Optional[int] = Field(None, description="卷数（针对书籍）")
    images: Optional[Dict[str, Any]] = Field(None, description="图片字典（支持多尺寸图片）")
    image: Optional[str] = Field(None, description="单个封面图片URL")
    tags: Optional[List[Dict[str, Any]]] = Field(None, description="标签列表")
    meta_tags: Optional[List[str]] = Field(None, description="官方元标签")
    infobox: Optional[List[Dict[str, Any]]] = Field(None, description="详细元数据（如作者、开发商等）")
    rating: Optional[Dict[str, Any]] = Field(None, description="评分信息")
    collection: Optional[Dict[str, Any]] = Field(None, description="收藏状态统计")
    series: Optional[bool] = Field(None, description="是否为系列")
    locked: Optional[bool] = Field(None, description="是否锁定")
    nsfw: Optional[bool] = Field(None, description="是否不适合儿童")
    air_time: Optional[datetime] = Field(None, description="放送时间")
    air_weekday: Optional[int] = Field(None, description="放送星期 (1-7)")
    last_sync: Optional[datetime] = Field(None, description="最后同步时间")

    class Config:
        from_attributes = True

class SubjectUpsert(BaseModel):
    """
    条目 Upsert Schema（插入/更新专用）
    
    通过 (source, source_id) 唯一定位记录：
    - 存在 → 仅更新客户端显式提供的字段（配合 exclude_unset）
    - 不存在 → 插入时校验业务必填字段（name, type）
    """
    # ===== 唯一标识字段（必填，不可为 None）=====
    source: str = Field(..., description="数据来源：bangumi/douban（定位必需）")
    source_id: str = Field(..., description="原站ID（Bangumi ID或豆瓣ID）（定位必需）")
    
    # ===== 业务字段（全部 Optional，仅更新显式提供的值）=====
    name: Optional[str] = Field(None, description="条目原名（插入时必填）")
    name_cn: Optional[str] = Field(default="", description="条目中文名")
    type: Optional[SubjectType] = Field(None, description="条目类型：1=书籍/2=动画/3=音乐/4=游戏/6=三次元（插入时必填）")
    summary: Optional[str] = Field(None, description="条目简介")
    date: Optional[str] = Field(None, description="发售/放送日期")
    platform: Optional[str] = Field(None, description="平台/类型")
    eps: Optional[int] = Field(None, description="集数")
    volumes: Optional[int] = Field(None, description="卷数")
    images: Optional[Dict[str, Any]] = Field(default_factory=dict, description="图片字典")
    image: Optional[str] = Field(default="", description="封面URL")
    tags: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="标签列表")
    meta_tags: Optional[List[str]] = Field(default_factory=list, description="官方元标签")
    infobox: Optional[List[Dict[str, Any]]] = Field(default_factory=list, description="详细元数据")
    rating: Optional[Dict[str, Any]] = Field(default_factory=dict, description="评分信息")
    collection: Optional[Dict[str, Any]] = Field(default_factory=dict, description="收藏统计")
    series: Optional[bool] = Field(default=False, description="是否为系列")
    locked: Optional[bool] = Field(default=False, description="是否锁定")
    nsfw: Optional[bool] = Field(default=False, description="是否NSFW")
    air_time: Optional[datetime] = Field(default=None, description="放送时间")
    air_weekday: Optional[int] = Field(default=None, description="放送星期 (1-7)")
    last_sync: Optional[datetime] = Field(default=None, description="最后同步时间")

    class Config:
        populate_by_name = True  # 兼容字段别名
        # ❌ 不设置 from_attributes（此为输入Schema，非ORM映射）

class SubjectList(BaseList):
    """
    条目列表分页响应Schema
    
    用于返回分页的条目列表，包含总数和条目列表
    """
    items: List[SubjectBase] = Field(default_factory=list, description="条目列表")


class SubjectReadList(SubjectList):
    """
    条目列表分页响应Schema
    
    用于返回分页的条目列表，包含总数和条目列表
    """
    total: int = Field(..., description="总记录数")
    items: List[SubjectRead] = Field(default_factory=list, description="条目列表")


class SubjectUpdateList(BaseList):
    """
    条目更新列表分页响应Schema
    
    用于返回分页的条目更新列表，包含总数和条目列表
    """
    items: List[SubjectUpdate] = Field(default_factory=list, description="条目列表")


class SubjectSearchByID(BaseModel):
    """
    条目搜索ByIDSchema
    
    用于根据ID搜索条目，包含关键词、类型、数据源等参数
    """
    source: str = Field(default="bangumi", description="数据来源：bangumi/douban")
    source_id: str = Field(..., description="原站ID（Bangumi ID或豆瓣ID）")
    user_id: Optional[int] = Field(None, description="用户ID")

class SubjectSearchBase(SearchBase):
    """
    条目搜索基础Schema
    
    用于搜索条目，包含关键词、类型、数据源等参数
    """
    pass

class SubjectSearchCloud(BaseModel):
    """
    条目搜索CloudSchema
    
    用于搜索Cloud数据库中的条目，包含关键词、类型、数据源等参数
    """
    type: Optional[SubjectType] = Field(None, description="条目类型")
    skip: Optional[int] = Field(default=0, description="跳过的记录数")
    limit: int = Field(default=10, description="返回的最大记录数")
    user_id: Optional[int] = Field(None, description="用户ID")
    keyword: str = Field(..., description="搜索关键词")
    offset: int = Field(default=0, description="跳移量")


class SubjectUpsertList(BaseList):
    """
    条目插入或更新列表分页响应Schema
    
    用于插入或更新分页的条目列表，包含总数和条目列表
    """
    items: List[SubjectUpsert] = Field(default_factory=list, description="条目列表")


class SubjectSearchByName(SubjectSearchBase):
    """
    条目搜索ByNameSchema
    
    用于根据关键词搜索条目，包含关键词、类型、数据源等参数
    """
    keyword: str = Field(..., description="搜索关键词")


class SubjectListRequest(SubjectList):
    """
    多来源条目列表分页请求Schema
    
    将多类型的数据结构转换为SubjectList格式
    支持两种数据格式：
    1. bangumi_collection.json格式
    2. collection_subject.json格式
    输出为SubjectList格式
    """
    
    class Config:
        from_attributes = True
        extra = "allow"
    
    @model_validator(mode='before')
    @classmethod
    def convert_to_subject_list(cls, data: Any) -> Any:
        """
        将两种不同的JSON数据格式转换为SubjectList格式
        
        Args:
            data: 输入数据，可以是bangumi_collection.json格式或collection_subject.json格式
            
        Returns:
            转换后的SubjectList格式数据
        """
        from .adaptersV2 import bangumi_subject_to_subjectlist
        return bangumi_subject_to_subjectlist(data)


class SubjectCollection(BaseModel):
    """
    收藏读取Schema
    
    用于返回收藏的详细信息，包含收藏信息和关联的条目信息
    """
    # 收藏基本信息
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
    user_id: int = Field(..., description="用户ID")
    
    # 关联的条目信息
    subject: SubjectRead = Field(..., description="关联的条目信息")

    class Config:
        from_attributes = True


class SubjectCollectionList(BaseList):
    """
    收藏列表分页响应Schema
    
    用于返回分页的收藏列表，包含总数和条目列表
    """
    items: List[SubjectCollection] = Field(default_factory=list, description="收藏列表")


class SubjectWithCollection(BaseModel):
    """
    条目及其关联收藏信息Schema
    
    用于返回单个条目及其关联的收藏信息
    """
    subject: SubjectRead = Field(..., description="条目信息")
    collection: Optional['CollectionRead'] = Field(None, description="关联的收藏信息")

    class Config:
        from_attributes = True


class SubjectWithCollectionList(BaseList):
    """
    条目及其关联收藏信息列表Schema
    
    用于返回条目及其关联收藏信息的列表
    """
    items: List[SubjectWithCollection] = Field(default_factory=list, description="条目及其关联收藏信息列表")


# 解决循环引用问题
if not TYPE_CHECKING:
    from .collection import CollectionRead
    SubjectWithCollection.model_rebuild()
