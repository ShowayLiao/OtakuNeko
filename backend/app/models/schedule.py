from __future__ import annotations
from datetime import time
from typing import Optional, TYPE_CHECKING
from sqlmodel import SQLModel, Field, Relationship

from .enums import WatchType

if TYPE_CHECKING:
    from .user import User


class Schedule(SQLModel, table=True):
    """
    番剧排班模型
    
    用于存储用户的番剧观看排班信息
    """
    __tablename__ = "schedules"
    
    id: Optional[int] = Field(default=None, primary_key=True, description="排班ID")
    source: str = Field(description="数据来源: bangumi/douban")
    source_id: str = Field(description="数据来源的ID")
    day_of_week: int = Field(description="星期几，0-6 (周日到周六)")
    start_time: time = Field(description="具体的放送时间")
    watch_day: Optional[int] = Field(default=None, description="观看星期几，0-6 (周日到周六)")
    watch_time: Optional[time] = Field(default=None, description="具体的观看时间")
    duration: Optional[int] = Field(default=None, description="观看周期（天）")
    user_id: int = Field(foreign_key="users.id", description="用户ID")
    watch_type: Optional[WatchType] = Field(default=None, description="观看类型")
    
