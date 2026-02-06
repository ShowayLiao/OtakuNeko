from pydantic import BaseModel, Field


class DashboardStats(BaseModel):
    """
    用户仪表板统计数据Schema
    
    用于展示用户在不同分类下的收藏总数
    """
    anime: int = Field(default=0, description="动画收藏数量")
    books: int = Field(default=0, description="书籍收藏数量")
    music: int = Field(default=0, description="音乐收藏数量")
    games: int = Field(default=0, description="游戏收藏数量")
    real: int = Field(default=0, description="三次元收藏数量")
    total: int = Field(default=0, description="总收藏数量")
