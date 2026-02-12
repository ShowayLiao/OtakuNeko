from pydantic import BaseModel, Field
from typing import List, Optional

# 1. 单个 Staff 的结构
class StaffInfo(BaseModel):
    name: str = Field(..., description="人名或公司名")
    role: str = Field(..., description="标准化后的职位 (e.g., Director, Studio)")

# 2. 整个条目的结构
class SubjectDetail(BaseModel):
    id: int
    name: str = Field(..., description="作品原名")
    name_cn: Optional[str] = Field(None, description="中文译名")
    summary: str = Field(..., description="剧情简介")
    score: Optional[float] = Field(None, description="Bangumi 评分")
    rank: Optional[int] = Field(None, description="Bangumi 排名")
    
    # 我们把核心 Staff 直接放在这里，作为分析的关键依据
    core_staff: List[StaffInfo] = Field(default_factory=list, description="核心制作阵容：监督、脚本、制作公司等")