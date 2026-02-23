from enum import IntEnum


class SubjectType(IntEnum):
    """
    Bangumi条目类型枚举
    
    对应Bangumi API中的type字段
    """
    BOOK = 1  # 书籍/小说
    ANIME = 2  # 动画
    MUSIC = 3  # 音乐
    GAME = 4  # 游戏
    REAL = 6  # 三次元


class CollectionStatus(IntEnum):
    """
    Bangumi收藏状态枚举
    
    对应Bangumi API中的收藏记录type字段
    """
    WISH = 1  # 想看
    COLLECT = 2  # 看过
    DO = 3  # 在看
    ON_HOLD = 4  # 搁置
    DROPPED = 5  # 抛弃


class WatchType(IntEnum):
    """
    观看类型枚举
    
    用于表示用户的番剧观看类型
    """
    MEAL = 1  # 饭点
    LEISURE = 2  # 闲暇
    LONG_GRASS = 3  # 长草
    NEW = 4  # 新番
