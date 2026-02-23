from pydantic import BaseModel, Field, field_validator
from typing import Optional, List
from datetime import time

from ..models.enums import WatchType


class ScheduleBase(BaseModel):
    """
    排班基础信息Schema
    
    包含排班的核心字段
    """
    source: str = Field(..., description="数据来源: bangumi/douban")
    source_id: str = Field(..., min_length=1, max_length=20, description="数据来源的ID")
    day_of_week: int = Field(..., ge=0, le=6, description="星期几，0-6 (周日到周六)")
    start_time: time = Field(..., description="具体的放送时间")
    watch_day: Optional[int] = Field(None, ge=0, le=6, description="观看星期几，0-6 (周日到周六)")
    watch_time: Optional[time] = Field(None, description="具体的观看时间")
    duration: Optional[int] = Field(None, description="观看周期（天）")
    watch_type: Optional[WatchType] = Field(None, description="观看类型")


class ScheduleCreate(ScheduleBase):
    """
    排班创建Schema
    
    用于创建新的排班记录
    """
    user_id: int = Field(..., description="用户ID")
    pass


class ScheduleUpdate(BaseModel):
    """
    排班更新Schema
    
    用于更新现有的排班记录，所有字段均为可选
    """
    source: Optional[str] = Field(None, description="数据来源: bangumi/douban")
    source_id: Optional[str] = Field(None, min_length=1, max_length=20, description="数据来源的ID")
    day_of_week: Optional[int] = Field(None, ge=0, le=6, description="星期几，0-6 (周日到周六)")
    start_time: Optional[time] = Field(None, description="具体的放送时间")
    watch_day: Optional[int] = Field(None, ge=0, le=6, description="观看星期几，0-6 (周日到周六)")
    watch_time: Optional[time] = Field(None, description="具体的观看时间")
    duration: Optional[int] = Field(None, description="观看周期（天）")
    watch_type: Optional[WatchType] = Field(None, description="观看类型")


class ScheduleUpsert(ScheduleBase):
    """
    排班Upsert Schema
    
    用于upsert操作（更新或插入），当提供id时执行更新，否则执行插入
    """
    id: Optional[int] = Field(None, description="排班ID，提供时执行更新操作")
    user_id: int = Field(..., description="用户ID")


class ScheduleRead(ScheduleBase):
    """
    排班读取Schema
    
    用于返回排班的完整信息，支持ORM模式
    """
    id: int = Field(..., description="排班ID")
    user_id: int = Field(..., description="用户ID")
    
    class Config:
        from_attributes = True


class ScheduleUpsertList(BaseModel):
    """
    排班Upsert列表Schema
    
    用于批量upsert操作
    """
    items: List[ScheduleUpsert] = Field(..., description="待处理的排班记录列表")


class ScheduleReadList(BaseModel):
    """
    排班读取列表Schema
    
    用于返回批量排班记录
    """
    items: List[ScheduleRead] = Field(..., description="排班记录列表")
    total: int = Field(..., description="总记录数")
