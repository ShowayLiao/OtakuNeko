from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from app.models.enums import SubjectType, CollectionStatus


class BaseList(BaseModel):
    """
    基础列表分页响应Schema
    
    用于返回分页的列表，包含总数和条目列表
    """
    total: int = Field(..., description="总记录数")


class SearchBase(BaseModel):
    """
    基础搜索Schema
    
    用于搜索，包含类型、分页等参数
    """
    type: Optional[SubjectType] = Field(None, description="条目类型")
    skip: Optional[int] = Field(default=0, description="跳过的记录数")
    limit: Optional[int] = Field(default=10, description="返回的最大记录数")
    user_id: Optional[int] = Field(None, description="用户ID")
