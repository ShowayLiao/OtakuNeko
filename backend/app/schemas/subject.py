from pydantic import BaseModel, Field, model_validator
from typing import Optional, List, Dict, Any
from app.models.enums import SubjectType, CollectionStatus


class SubjectBase(BaseModel):
    """
    条目基础信息Schema
    
    包含条目的公共基础字段
    """
    name: str = Field(..., description="条目原名")
    name_cn: Optional[str] = Field(default="", description="条目中文名")
    type: SubjectType = Field(..., description="条目类型：1=书籍/2=动画/3=音乐/4=游戏/6=三次元")
    source: str = Field(default="bangumi", description="数据来源：bangumi/douban")
    source_id: str = Field(..., description="原站ID（Bangumi ID或豆瓣ID）")
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
    rating: Dict[str, Any] = Field(default_factory=dict, description="评分信息")
    collection: Optional[Dict[str, Any]] = Field(default_factory=dict, description="收藏状态统计")
    series: Optional[bool] = Field(default=False, description="是否为系列")
    locked: Optional[bool] = Field(default=False, description="是否锁定")
    nsfw: Optional[bool] = Field(default=False, description="是否不适合儿童")

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
    name_cn: Optional[str] = Field(None, description="条目中文名")
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

    class Config:
        from_attributes = True


class SubjectList(BaseModel):
    """
    条目列表分页响应Schema
    
    用于返回分页的条目列表，包含总数和条目列表
    """
    total: int = Field(..., description="总记录数")
    items: List[SubjectBase] = Field(default_factory=list, description="条目列表")


class SubjectReadList(SubjectList):
    """
    条目列表分页响应Schema
    
    用于返回分页的条目列表，包含总数和条目列表
    """
    total: int = Field(..., description="总记录数")
    items: List[SubjectRead] = Field(default_factory=list, description="条目列表")


class SubjectUpdateList(SubjectUpdate):
    """
    条目列表分页响应Schema
    
    用于返回分页的条目列表，包含总数和条目列表
    """
    total: int = Field(..., description="总记录数")
    items: List[SubjectUpdate] = Field(default_factory=list, description="条目列表")


class SubjectSearchByID(BaseModel):
    """
    条目搜索ByIDSchema
    
    用于根据ID搜索条目，包含关键词、类型、数据源等参数
    """
    source: str = Field(default="bangumi", description="数据来源：bangumi/douban")
    source_id: str = Field(..., description="原站ID（Bangumi ID或豆瓣ID）")
    user_id: Optional[int] = Field(None, description="用户ID")

class SubjectSearchBase(BaseModel):
    """
    条目搜索基础Schema
    
    用于搜索条目，包含关键词、类型、数据源等参数
    """
    type: Optional[SubjectType] = Field(None, description="条目类型")
    skip: Optional[int] = Field(default=0, description="跳过的记录数")
    limit: Optional[int] = Field(default=10, description="返回的最大记录数")
    user_id: Optional[int] = Field(None, description="用户ID")

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
        """
        from .adapters import adapt_to_subject_list
        return adapt_to_subject_list(data)