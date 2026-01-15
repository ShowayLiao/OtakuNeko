from __future__ import annotations
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any, TYPE_CHECKING
from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Column, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSON
from .enums import SubjectType


def utc_now():
    """获取当前 UTC 时间"""
    return datetime.utcnow()


class Subject(SQLModel, table=True):  # type: ignore[call-arg]
    """
    通用条目模型，支持多数据源（Bangumi、豆瓣等）
    
    兼容Type A（收藏列表中的嵌套Subject）和Type B（条目详情）两种API返回格式
    字段定义完全按照 bangumi_subject.json 数据格式
    """
    # 基础信息
    id: Optional[int] = Field(default=None, primary_key=True, description="数据库自增主键")
    source: str = Field(default="bangumi", index=True, description="数据来源：bangumi/douban")
    source_id: str = Field(index=True, description="原站ID（Bangumi ID或豆瓣ID）")
    type: SubjectType = Field(index=True, description="条目类型：1=书籍/2=动画/3=音乐/4=游戏/6=三次元")
    name: str = Field(description="条目原名")
    name_cn: Optional[str] = Field(default="", description="条目中文名")
    summary: Optional[str] = Field(sa_column=Column(Text), description="条目简介")
    date: Optional[str] = Field(default="", description="发售/放送日期")
    platform: Optional[str] = Field(default="", description="平台/类型（如TV、小说、Switch等）")
    
    # 图片信息
    images: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON), description="图片字典（支持多尺寸图片）")
    image: Optional[str] = Field(default="", description="单个封面图片URL")
    
    # 标签信息
    tags: List[Dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON), description="标签列表")
    meta_tags: List[str] = Field(default_factory=list, sa_column=Column(JSON), description="官方元标签")
    
    # 详细信息
    infobox: List[Dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON), description="详细元数据（如作者、开发商等）")
    rating: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON), description="评分信息")
    collection: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON), description="收藏状态统计")
    
    # 数值信息
    eps: Optional[int] = Field(default=None, description="集数（针对动画）")
    volumes: Optional[int] = Field(default=None, description="卷数（针对书籍）")
    
    # 其他信息
    series: bool = Field(default=False, description="是否为系列")
    locked: bool = Field(default=False, description="是否锁定")
    nsfw: bool = Field(default=False, description="是否不适合儿童")
    
    
    # 联合唯一索引：确保同一数据源的同一条目不重复
    __table_args__ = (
        UniqueConstraint('source', 'source_id', name='uq_source_source_id'),
    )
    

