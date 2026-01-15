from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


class SubjectBase(BaseModel):
    """
    条目基础信息Schema
    
    包含条目的公共基础字段
    """
    name: str = Field(..., description="条目原名")
    name_cn: Optional[str] = Field(None, description="条目中文名")
    cover_url: str = Field(..., description="封面图片URL")
    type: int = Field(..., description="条目类型")
    eps: Optional[int] = Field(None, description="集数")
    volumes: Optional[int] = Field(None, description="卷数")
    platform: Optional[str] = Field(None, description="平台")
    summary: Optional[str] = Field(None, description="条目简介")
    tags: List[str] = Field(default_factory=list, description="标签列表")
    date: Optional[str] = Field(None, description="发售/放送日期")

    class Config:
        from_attributes = True


class SubjectRead(SubjectBase):
    """
    条目读取Schema
    
    用于返回条目基本信息，继承自 SubjectBase，增加ID和评分相关字段
    """
    id: int = Field(..., description="数据库自增主键")
    source_id: str = Field(..., description="原站ID")
    score: Optional[float] = Field(None, description="评分")
    rank: Optional[int] = Field(None, description="排名")

    class Config:
        from_attributes = True


class SubjectDetail(SubjectRead):
    """
    条目详细信息Schema
    
    包含条目的完整信息，用于详情页展示，继承自 SubjectRead，增加大字段
    """
    collection_total: Optional[int] = Field(None, description="总收藏人数")
    meta_tags: List[str] = Field(default_factory=list, description="官方元标签")
    infobox: List[Dict[str, str]] = Field(default_factory=list, description="详细元数据")
    rating_details: Dict[str, Any] = Field(default_factory=dict, description="评分分布详情")
    images: Dict[str, Any] = Field(default_factory=dict, description="图片字典")

    class Config:
        from_attributes = True


class SubjectWithUserStatus(SubjectRead):
    """
    带用户收藏状态的条目信息Schema
    
    用于搜索结果，返回条目信息以及当前用户是否已收藏
    继承自 SubjectRead，扩展了收藏状态相关字段
    """
    is_collected: bool = Field(default=False, description="当前用户是否已收藏该条目")
    is_favorited: bool = Field(default=False, description="当前用户是否已收藏该条目（与is_collected同义，保持字段一致性）")
    collection_info: Optional[Dict[str, Any]] = Field(default=None, description="收藏信息，如果已收藏则返回")

    class Config:
        from_attributes = True


class SubjectUpdate(BaseModel):
    """
    条目更新Schema
    
    用于更新条目信息，保留用于未来错误修正功能
    所有字段都是可选的
    """
    name: Optional[str] = Field(None, description="条目原名")
    name_cn: Optional[str] = Field(None, description="条目中文名")
    cover_url: Optional[str] = Field(None, description="封面图片URL")
    type: Optional[int] = Field(None, description="条目类型")
    eps: Optional[int] = Field(None, description="集数")
    volumes: Optional[int] = Field(None, description="卷数")
    platform: Optional[str] = Field(None, description="平台")
    summary: Optional[str] = Field(None, description="条目简介")
    tags: Optional[List[str]] = Field(None, description="标签列表")
    date: Optional[str] = Field(None, description="发售/放送日期")
    score: Optional[float] = Field(None, description="评分")
    rank: Optional[int] = Field(None, description="排名")
    collection_total: Optional[int] = Field(None, description="总收藏人数")
    meta_tags: Optional[List[str]] = Field(None, description="官方元标签")
    infobox: Optional[List[Dict[str, str]]] = Field(None, description="详细元数据")
    rating_details: Optional[Dict[str, Any]] = Field(None, description="评分分布详情")
    images: Optional[Dict[str, Any]] = Field(None, description="图片字典")

    class Config:
        from_attributes = True
