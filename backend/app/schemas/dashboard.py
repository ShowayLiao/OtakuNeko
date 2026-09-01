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


class CollectionStatusCounts(BaseModel):
    """Fixed-shape watch-status counts for one user's collections."""

    wish: int = Field(default=0, description="想看")
    watched: int = Field(default=0, description="看过")
    watching: int = Field(default=0, description="在看")
    on_hold: int = Field(default=0, description="搁置")
    dropped: int = Field(default=0, description="抛弃")


class CollectionGenreCount(BaseModel):
    """A subject-tag frequency used as a genre/topic proxy."""

    name: str = Field(description="题材标签名称")
    count: int = Field(description="包含该标签的收藏作品数")


class CollectionStatistics(BaseModel):
    """Database-backed, user-scoped collection statistics."""

    subject_type: int = Field(description="条目类型，2 表示动画")
    total: int = Field(default=0, description="符合条目类型的收藏总数")
    status_counts: CollectionStatusCounts = Field(
        default_factory=CollectionStatusCounts,
        description="五种观看状态数量",
    )
    top_genres: list[CollectionGenreCount] = Field(
        default_factory=list,
        description="按作品标签聚合的前三个题材标签",
    )
    complete: bool = Field(
        default=True,
        description="收藏和状态统计是否来自完整数据库结果",
    )
    genre_subject_count: int = Field(
        default=0,
        description="参与题材标签统计的作品数",
    )
    genre_complete: bool = Field(
        default=True,
        description="是否所有收藏作品都有可用题材标签",
    )
