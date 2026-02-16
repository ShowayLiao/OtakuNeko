from pydantic import BaseModel, Field, field_validator
from typing import Optional
from datetime import time


class ScheduleBase(BaseModel):
    """
    排班基础信息Schema
    
    包含排班的核心字段
    """
    subject_id: str = Field(..., min_length=1, max_length=20, description="关联的Bangumi ID")
    day_of_week: int = Field(..., ge=0, le=6, description="星期几，0-6 (周日到周六)")
    start_time: time = Field(..., description="具体的放送时间")
    watch_day: Optional[int] = Field(None, ge=0, le=6, description="观看星期几，0-6 (周日到周六)")
    watch_time: Optional[time] = Field(None, description="具体的观看时间")


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
    subject_id: Optional[str] = Field(None, min_length=1, max_length=20, description="关联的Bangumi ID")
    day_of_week: Optional[int] = Field(None, ge=0, le=6, description="星期几，0-6 (周日到周六)")
    start_time: Optional[time] = Field(None, description="具体的放送时间")
    watch_day: Optional[int] = Field(None, ge=0, le=6, description="观看星期几，0-6 (周日到周六)")
    watch_time: Optional[time] = Field(None, description="具体的观看时间")


class ScheduleRead(ScheduleBase):
    """
    排班读取Schema
    
    用于返回排班的完整信息，支持ORM模式
    """
    id: int = Field(..., description="排班ID")
    user_id: int = Field(..., description="用户ID")
    
    class Config:
        from_attributes = True
