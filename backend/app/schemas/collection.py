from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict
from datetime import datetime
from app.models.enums import CollectionStatus
from app.schemas.subject import SubjectRead


class CollectionBase(BaseModel):
    """
    收藏基础信息Schema
    
    包含收藏的公共字段
    """
    status: CollectionStatus = Field(..., description="收藏状态 (1=想看/2=看过/3=在看/4=搁置/5=抛弃)")
    rate: Optional[int] = Field(None, ge=0, le=10, description="用户评分 (0-10)")
    comment: Optional[str] = Field(None, max_length=500, description="用户评论")
    private: bool = Field(default=False, description="是否私有收藏")
    tags: List[str] = Field(default_factory=list, description="用户自定义标签列表")

    class Config:
        from_attributes = True


class CollectionUpdate(CollectionBase):
    """
    收藏更新Schema
    
    用于更新用户收藏信息，所有字段设为 Optional，支持部分字段更新
    """
    status: Optional[CollectionStatus] = Field(None, description="收藏状态 (1=想看/2=看过/3=在看/4=搁置/5=抛弃)")
    rate: Optional[int] = Field(None, ge=0, le=10, description="用户评分 (0-10)")
    comment: Optional[str] = Field(None, max_length=500, description="用户评论")
    private: Optional[bool] = Field(None, description="是否私有收藏")
    tags: Optional[List[str]] = Field(None, description="用户自定义标签列表")


class CollectionRead(CollectionBase):
    """
    收藏读取Schema
    
    用于返回收藏的详细信息，继承自 CollectionBase，增加只读字段
    """
    subject_id: int = Field(..., description="关联的条目ID")
    updated_at: datetime = Field(..., description="最后更新时间")
    subject: Optional[SubjectRead] = Field(None, description="关联的条目信息")

    class Config:
        from_attributes = True


class CollectionList(BaseModel):
    """
    收藏列表分页响应Schema
    
    用于返回分页的收藏列表，包含总数和条目列表
    """
    total: int = Field(..., description="总记录数")
    items: List[CollectionRead] = Field(default_factory=list, description="收藏列表")


class ManualCollectionCreate(BaseModel):
    """
    手动添加收藏的请求Schema
    
    用于用户手动创建条目并添加到收藏
    """
    name: str = Field(..., description="条目标题", min_length=1, max_length=200)
    type: int = Field(..., description="条目类型 (1=书籍/2=动画/3=音乐/4=游戏/6=三次元)", ge=1, le=6)
    status: int = Field(..., description="收藏状态 (1=想看/2=看过/3=在看/4=搁置/5=抛弃)", ge=1, le=5)
    cover_url: str = Field(default="", description="封面图片URL")
    rate: int = Field(default=0, description="用户评分 (0-10)", ge=0, le=10)
    comment: str = Field(default="", description="用户评论", max_length=500)
    release_date: str = Field(default="", description="上映日期 (YYYY-MM-DD)")
    publish_date: str = Field(default="", description="发售日期 (YYYY-MM-DD)")
    tags: List[str] = Field(default_factory=list, description="标签列表")

    @field_validator('tags', mode='before')
    @classmethod
    def parse_tags(cls, v):
        """
        验证器：兼容字符串格式的标签输入
        
        支持逗号分隔的字符串格式，自动转换为 List[str]
        """
        if isinstance(v, str):
            return [tag.strip() for tag in v.split(',') if tag.strip()]
        return v


class CollectionSyncRequest(BaseModel):
    """
    收藏同步请求Schema
    
    用于统一处理 BGM 和 豆瓣的收藏同步请求
    """
    source: str = Field(..., description="数据来源: bgm=Bangumi, douban=豆瓣")
    subject_type: Optional[int] = Field(None, description="条目类型 (1=书籍/2=动画/3=音乐/4=游戏/6=三次元)")
    data: Optional[List[Dict]] = Field(None, description="豆瓣数据列表 (仅当source=douban时需要)")

    class Config:
        from_attributes = True


class CollectionUpsertRequest(BaseModel):
    """
    收藏更新/添加请求Schema
    
    用于 PUT /collections/{sid} 端点，支持更新现有收藏或创建新收藏
    如果收藏已存在，则更新收藏信息（使用 collection 字段）
    如果收藏不存在，则创建新收藏（需要提供 subject 字段）
    """
    collection: Optional[CollectionUpdate] = Field(None, description="收藏信息（更新时使用）")
    subject: Optional[ManualCollectionCreate] = Field(None, description="条目信息（创建新收藏时使用）")

    class Config:
        from_attributes = True
