from __future__ import annotations
from typing import Optional
from datetime import datetime
from sqlmodel import SQLModel, Field
from sqlalchemy import Column
from sqlalchemy.dialects.postgresql import JSON
from .enums import CollectionStatus


class Collection(SQLModel, table=True):  # type: ignore[call-arg]
    """用户收藏模型，存储用户对任意类型条目的收藏信息"""
    
    user_id: int = Field(primary_key=True, description="用户ID")
    subject_id: int = Field(primary_key=True, foreign_key="subject.id", description="关联的条目ID")
    type: CollectionStatus = Field(description="收藏类型：1想看/2看过/3在看/4搁置/5抛弃")
    rate: Optional[int] = Field(default=None, description="用户评分")
    comment: Optional[str] = Field(default=None, description="用户评论")
    updated_at: datetime = Field(description="最后更新时间")
    private: bool = Field(default=False, description="是否私密收藏")
    tags: list[str] = Field(default_factory=list, sa_column=Column(JSON), description="用户自定义标签")
    
    # 移除了与Subject的Relationship，避免循环导入和Mapper错误
    # 保留subject_id字段用于手动关联
