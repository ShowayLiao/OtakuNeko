from pydantic import BaseModel, Field, RootModel
from typing import List, Optional, Dict, Any

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

# 3. 日历相关的结构
class BangumiCalendarImage(BaseModel):
    large: Optional[str] = Field(None, description="大图 URL")
    common: Optional[str] = Field(None, description="中图 URL")
    medium: Optional[str] = Field(None, description="中中图 URL")
    small: Optional[str] = Field(None, description="小图 URL")

class BangumiCalendarRating(BaseModel):
    score: Optional[float] = Field(None, description="评分")
    total: Optional[int] = Field(None, description="评分人数")
    rank: Optional[int] = Field(None, description="排名")
    count: Optional[Dict[str, int]] = Field(None, description="各评分等级的人数分布")

class BangumiCalendarCollection(BaseModel):
    wish: Optional[int] = Field(None, description="想看人数")
    collect: Optional[int] = Field(None, description="在看人数")
    doing: Optional[int] = Field(None, description="在看人数")
    done: Optional[int] = Field(None, description="已看人数")
    on_hold: Optional[int] = Field(None, description="搁置人数")
    dropped: Optional[int] = Field(None, description="抛弃人数")

class BangumiCalendarItem(BaseModel):
    id: int = Field(..., description="动画 ID")
    url: Optional[str] = Field(None, description="动画链接")
    type: Optional[int] = Field(None, description="类型")
    name: str = Field(..., description="动画名称")
    name_cn: Optional[str] = Field(None, description="中文名称")
    summary: Optional[str] = Field(None, description="简介")
    air_date: Optional[str] = Field(None, description="放送日期")
    air_weekday: Optional[int] = Field(None, description="放送星期几")
    images: Optional[BangumiCalendarImage] = Field(None, description="图片信息")
    rating: Optional[BangumiCalendarRating] = Field(None, description="评分信息")
    collection: Optional[BangumiCalendarCollection] = Field(None, description="收藏信息")

class BangumiCalendarDay(BaseModel):
    weekday: Dict[str, Any] = Field(..., description="星期信息")
    items: List[BangumiCalendarItem] = Field(default_factory=list, description="当天放送的动画列表")

class BangumiCalendar(RootModel):
    """
    Bangumi 每日放送信息
    """
    root: List[BangumiCalendarDay]