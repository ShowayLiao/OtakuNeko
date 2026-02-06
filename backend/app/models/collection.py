from __future__ import annotations
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING
from sqlmodel import SQLModel, Field, Relationship
from sqlalchemy import Column,UniqueConstraint
from sqlalchemy.dialects.postgresql import JSON
from .enums import CollectionStatus


def utc_now():
    """获取当前 UTC 时间"""
    return datetime.now(timezone.utc)


class Collection(SQLModel, table=True):  # type: ignore[call-arg]
    """用户收藏模型，存储用户对任意类型条目的收藏信息"""
    id: Optional[int] = Field(default=None, primary_key=True, index=True, description="收藏记录唯一ID")
    user_id: int = Field(index=True, foreign_key="users.id", description="用户ID")
    source: str = Field(default="bangumi", index=True, description="数据来源：bangumi/douban")
    source_id: str = Field(index=True, description="原站ID（Bangumi ID或豆瓣ID）")
    type: CollectionStatus = Field(description="收藏类型：1想看/2看过/3在看/4搁置/5抛弃")
    rate: Optional[int] = Field(default=None, description="用户评分")
    comment: Optional[str] = Field(default=None, description="用户评论")
    updated_at: datetime = Field(
        default_factory=utc_now,
        index=True,
        description="最后更新时间"
    )
    private: bool = Field(default=False, description="是否私密收藏")
    tags: list[str] = Field(default_factory=list, sa_column=Column(JSON), description="用户自定义标签")
    vol_status: int = Field(default=0, description="卷数状态")
    ep_status: int = Field(default=0, description="集数状态")
    subject_type: int = Field(default=0, description="条目类型")

    __table_args__ = (
        UniqueConstraint('user_id', 'source', 'source_id', name='uq_user_collection'),
    )


