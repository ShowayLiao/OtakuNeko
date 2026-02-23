from __future__ import annotations
from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field


class AnimeBroadcastMetadata(SQLModel, table=True):
    """
    番剧放送元数据模型
    
    用于缓存 bangumi-data 的放送信息，提供番剧的首播时间、时区等元数据
    """
    __tablename__ = "anime_broadcast_metadata"
    
    bangumi_id: int = Field(..., primary_key=True, description="对应 Bangumi 的 subject_id")
    title: str = Field(..., description="番剧原名")
    broadcast_begin: datetime = Field(..., description="首播时间 (ISO8601)")
    broadcast_tz: str = Field(default="Asia/Tokyo", description="时区")
    year: int = Field(..., description="年份 (用于筛选)")
    season: int = Field(..., description="季度 (1, 4, 7, 10)")
    updated_at: datetime = Field(default_factory=datetime.utcnow, description="记录更新时间")
