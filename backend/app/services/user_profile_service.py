"""
用户画像生成服务
基于用户的观看记录（收藏数据），通过「频次 + 平均分」的二维加权算法，
生成高质量的用户画像，用于动画推荐和个性化分析。
"""

from typing import List, Dict, Any, TYPE_CHECKING, Tuple, TypedDict
from collections import defaultdict
from app.core.logging import get_logger

if TYPE_CHECKING:
    from app.schemas.collection import CollectionSubject

logger = get_logger(__name__)



# 类型定义
class TagStats(TypedDict):
    """标签统计数据类型"""
    count: int
    total_score: float


class FilteredTag(TypedDict):
    """过滤后的标签数据类型"""
    count: int
    avg_score: float


class TasteDictionary(TypedDict):
    """全景字典类型"""
    total_rated: int
    taste_dictionary: Dict[str, List[int]]


class ChartData(TypedDict):
    """图表数据类型"""
    radar: List[Dict[str, Any]]
    bar_count: List[Dict[str, Any]]
    bar_score: List[Dict[str, Any]]


class UserProfile(TypedDict):
    """用户画像完整类型"""
    llm_summary: TasteDictionary
    chart_data: ChartData
    watched_ids: List[int]


def generate_user_profile(collections: List['CollectionSubject']) -> UserProfile:
    """
    生成用户画像的核心函数

    输入：用户收藏列表，每个元素是一个 CollectionSubject Schema
    输出：包含三部分数据的用户画像字典

    Args:
        collections: 用户收藏列表，类型为 List[CollectionSubject]，每个元素包含：
            - 继承自 CollectionBase 的收藏字段（rate, type, comment, tags 等）
            - subject: 关联的 SubjectRead 条目信息（id, name, tags 等）

    Returns:
        包含三部分数据的用户画像：
        1. llm_summary: 供给大模型使用的全景字典
        2. chart_data: 供给前端画图使用的数据结构
        3. watched_ids: 已观看动画的ID列表（去重）

    Raises:
        不会抛出异常，所有错误都会被捕获并返回错误画像
    """
    
    # 输入验证
    if not collections:
        logger.warning("用户收藏列表为空，返回空画像")
        return _create_empty_profile()
    
    try:
        # 步骤1: 数据清洗 - 提取有效数据
        watched_ids, valid_entries = _clean_and_extract_data(collections)
        
        if not valid_entries:
            logger.warning("没有有效的评分数据，返回基础画像")
            return _create_basic_profile(watched_ids)
        
        # 步骤2: 基础统计 - 统计每个标签的出现次数和总分
        tag_stats = _calculate_tag_statistics(valid_entries)
        
        if not tag_stats:
            logger.warning("没有有效的标签数据，返回基础画像")
            return _create_basic_profile(watched_ids)
        
        # 步骤3: 统计学修正 - 计算平均分并过滤小样本
        filtered_tags = _apply_statistical_correction(tag_stats)
        
        if not filtered_tags:
            logger.warning("过滤后没有有效的标签数据，返回基础画像")
            return _create_basic_profile(watched_ids)
        
        # 步骤4: 构建全景字典 - 按频次降序排列
        taste_dictionary = _build_taste_dictionary(filtered_tags)
        
        # 步骤5: 计算综合偏好指数
        affinity_scores = _calculate_affinity_scores(filtered_tags)
        
        # 步骤6: 构建图表数据
        chart_data = _build_chart_data(filtered_tags, affinity_scores)
        
        # 步骤7: 构建最终结果
        return {
            "llm_summary": {
                "total_rated": len(valid_entries),
                "taste_dictionary": taste_dictionary
            },
            "chart_data": chart_data,
            "watched_ids": watched_ids
        }
        
    except Exception as e:
        logger.error(f"生成用户画像时发生错误: {e}", exc_info=True)
        return _create_error_profile(str(e))


def _clean_and_extract_data(collections: List['CollectionSubject']) -> Tuple[List[int], List[Dict[str, Any]]]:
    """
    数据清洗：提取有效数据

    1. 提取所有 subject_id（去重）
    2. 跳过没有评分（rate为0或None）的记录
    3. 提取有效条目的标签和评分

    Args:
        collections: CollectionSubject 列表

    Returns:
        Tuple[watched_ids, valid_entries]
        - watched_ids: 所有观看过的动画ID列表（去重）
        - valid_entries: 有效条目的列表，每个元素包含tags和score

    Note:
        会跳过格式异常或数据不完整的条目
    """
    watched_ids = []
    valid_entries = []

    for item in collections:
        try:
            subject = item.subject
            if not subject:
                continue

            # 提取subject_id
            subject_id = subject.id or subject.source_id
            if subject_id:
                try:
                    subject_id_int = int(subject_id)
                    if subject_id_int not in watched_ids:
                        watched_ids.append(subject_id_int)
                except (ValueError, TypeError):
                    pass

            # 检查是否有有效评分
            score = item.rate
            if score is None or score == 0:
                continue

            # 提取标签
            tags = subject.tags or []
            if not tags:
                continue

            # 存储有效条目
            valid_entries.append({
                "tags": tags,
                "score": float(score)
            })

        except Exception as e:
            logger.debug(f"处理收藏条目时跳过（可能数据格式异常）: {e}")
            continue

    return watched_ids, valid_entries


def _calculate_tag_statistics(valid_entries: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    基础统计：统计每个标签的出现次数和累加总分
    
    Args:
        valid_entries: 有效条目列表，每个元素包含tags和score
    
    Returns:
        标签统计字典：{tag_name: {"count": X, "total_score": Y}}
    """
    tag_stats = defaultdict(lambda: {"count": 0, "total_score": 0.0})
    
    for entry in valid_entries:
        tags = entry["tags"]
        score = entry["score"]
        
        # 处理标签列表（每个标签是字典，包含name字段）
        for tag_item in tags:
            try:
                # 提取标签名称
                tag_name = tag_item.get("name")
                if not tag_name:
                    continue
                
                # 更新统计
                tag_stats[tag_name]["count"] += 1
                tag_stats[tag_name]["total_score"] += score
            except (AttributeError, KeyError):
                # 跳过格式异常的标签
                continue
    
    return dict(tag_stats)


def _apply_statistical_correction(tag_stats: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """
    统计学修正：计算平均分并过滤小样本
    
    1. 计算每个标签的平均分（保留一位小数）
    2. 过滤掉 count < 2 的标签（避免极小样本造成的噪音）
    
    Args:
        tag_stats: 标签统计字典
    
    Returns:
        过滤后的标签字典：{tag_name: {"count": X, "avg_score": Y}}
    """
    filtered_tags = {}
    
    for tag_name, stats in tag_stats.items():
        count = stats["count"]
        total_score = stats["total_score"]
        
        # 过滤小样本
        if count < 2:
            continue
        
        # 计算平均分（保留一位小数）
        avg_score = round(total_score / count, 1)
        
        filtered_tags[tag_name] = {
            "count": count,
            "avg_score": avg_score
        }
    
    return filtered_tags


def _build_taste_dictionary(filtered_tags: Dict[str, Dict[str, Any]]) -> Dict[str, List[int]]:
    """
    构建全景字典：将标签转化为紧凑格式
    
    格式："标签名": [频次, 平均分]
    按频次降序排列
    
    Args:
        filtered_tags: 过滤后的标签字典
    
    Returns:
        全景字典：{tag_name: [count, avg_score]}
    """
    # 按频次降序排序
    sorted_tags = sorted(
        filtered_tags.items(),
        key=lambda x: x[1]["count"],
        reverse=True
    )
    
    taste_dict = {}
    for tag_name, stats in sorted_tags:
        taste_dict[tag_name] = [stats["count"], stats["avg_score"]]
    
    return taste_dict


def _calculate_affinity_scores(filtered_tags: Dict[str, Dict[str, Any]]) -> Dict[str, int]:
    """
    计算综合偏好指数 (Affinity Score)
    
    计算公式：基础分（基于评分） + 频次加分
    基础分：评分映射到0-70分（0分→0，10分→70）
    频次加分：基于频次排名，最高30分
    
    Args:
        filtered_tags: 过滤后的标签字典
    
    Returns:
        偏好指数字典：{tag_name: score(0-100)}
    """
    if not filtered_tags:
        return {}
    
    # 提取所有标签的频次用于排名
    tag_counts = {tag: stats["count"] for tag, stats in filtered_tags.items()}
    
    # 按频次降序排序，用于计算排名加分
    sorted_by_count = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)
    rank_map = {tag: i for i, (tag, _) in enumerate(sorted_by_count)}
    total_tags = len(sorted_by_count)
    
    affinity_scores = {}
    
    for tag_name, stats in filtered_tags.items():
        avg_score = stats["avg_score"]
        count = stats["count"]
        
        # 基础分：评分映射到0-70分
        # 评分范围0-10，映射到0-70
        base_score = int((avg_score / 10.0) * 70)
        
        # 频次加分：基于排名，最高30分
        # 排名越靠前（频次越高），加分越多
        rank = rank_map[tag_name]
        frequency_bonus = int((1 - rank / max(total_tags, 1)) * 30)
        
        # 总得分（0-100）
        total_score = min(100, base_score + frequency_bonus)
        
        affinity_scores[tag_name] = total_score
    
    return affinity_scores


def _build_chart_data(filtered_tags: Dict[str, Dict[str, Any]], 
                     affinity_scores: Dict[str, int]) -> Dict[str, Any]:
    """
    构建图表数据
    
    包含三部分：
    1. 雷达图：取affinity score排名前6的tag
    2. 频次柱状图：取count排名前5的tag
    3. 质量柱状图：取avg_score排名前5的tag
    
    Args:
        filtered_tags: 过滤后的标签字典
        affinity_scores: 偏好指数字典
    
    Returns:
        图表数据字典
    """
    if not filtered_tags:
        return {
            "radar": [],
            "bar_count": [],
            "bar_score": []
        }
    
    # 1. 雷达图数据：取affinity score排名前6的tag
    radar_data = []
    if affinity_scores:
        sorted_by_affinity = sorted(
            affinity_scores.items(),
            key=lambda x: x[1],
            reverse=True
        )[:6]
        radar_data = [
            {"name": tag, "value": score}
            for tag, score in sorted_by_affinity
        ]
    
    # 2. 频次柱状图数据：取count排名前5的tag
    bar_count_data = []
    sorted_by_count = sorted(
        filtered_tags.items(),
        key=lambda x: x[1]["count"],
        reverse=True
    )[:5]
    bar_count_data = [
        {"name": tag, "value": stats["count"]}
        for tag, stats in sorted_by_count
    ]
    
    # 3. 质量柱状图数据：取avg_score排名前5的tag
    bar_score_data = []
    sorted_by_score = sorted(
        filtered_tags.items(),
        key=lambda x: x[1]["avg_score"],
        reverse=True
    )[:5]
    bar_score_data = [
        {"name": tag, "value": stats["avg_score"]}
        for tag, stats in sorted_by_score
    ]
    
    return {
        "radar": radar_data,
        "bar_count": bar_count_data,
        "bar_score": bar_score_data
    }


def _create_empty_profile() -> Dict[str, Any]:
    """创建空画像（输入为空时使用）"""
    return {
        "llm_summary": {
            "total_rated": 0,
            "taste_dictionary": {}
        },
        "chart_data": {
            "radar": [],
            "bar_count": [],
            "bar_score": []
        },
        "watched_ids": []
    }


def _create_basic_profile(watched_ids: List[int]) -> Dict[str, Any]:
    """创建基础画像（数据不足时使用）"""
    return {
        "llm_summary": {
            "total_rated": 0,
            "taste_dictionary": {}
        },
        "chart_data": {
            "radar": [],
            "bar_count": [],
            "bar_score": []
        },
        "watched_ids": watched_ids
    }


def _create_error_profile(error_msg: str) -> Dict[str, Any]:
    """创建错误画像（发生异常时使用）"""
    return {
        "llm_summary": {
            "total_rated": 0,
            "taste_dictionary": {},
            "error": error_msg
        },
        "chart_data": {
            "radar": [],
            "bar_count": [],
            "bar_score": []
        },
        "watched_ids": [],
        "error": error_msg
    }


# 四象限分类函数（根据需求可选）
def _extract_four_quadrants(filtered_tags: Dict[str, Dict[str, Any]]) -> Dict[str, List[str]]:
    """
    四象限分类提取（根据原始需求，可选功能）
    
    1. 真爱区 (Core Favorites): avg_score >= 7.5
    2. 电子榨菜区 (Time Killers): avg_score < 6.5 且 count >= 5
    3. 雷区 (Avoid Tags): avg_score < 5.0
    
    Args:
        filtered_tags: 过滤后的标签字典
    
    Returns:
        四象限分类字典
    """
    core_favorites = []
    time_killers = []
    avoid_tags = []
    
    for tag_name, stats in filtered_tags.items():
        avg_score = stats["avg_score"]
        count = stats["count"]
        
        # 真爱区
        if avg_score >= 7.5:
            core_favorites.append(tag_name)
        
        # 电子榨菜区
        if avg_score < 6.5 and count >= 5:
            time_killers.append(tag_name)
        
        # 雷区
        if avg_score < 5.0:
            avoid_tags.append(tag_name)
    
    # 真爱区排序：按综合权重降序排列，取前5个
    if core_favorites:
        core_favorites_with_stats = [
            (tag, filtered_tags[tag]["avg_score"], filtered_tags[tag]["count"])
            for tag in core_favorites
        ]
        
        # 归一化频次
        max_count = max([c for _, _, c in core_favorites_with_stats]) if core_favorites_with_stats else 1
        
        # 计算综合权重：(avg_score * 0.7) + (归一化后的count * 0.3)
        weighted_scores = []
        for tag, avg_score, count in core_favorites_with_stats:
            normalized_count = count / max_count
            weight = (avg_score * 0.7) + (normalized_count * 0.3)
            weighted_scores.append((tag, weight))
        
        # 按权重降序排序，取前5个
        core_favorites = [
            tag for tag, _ in sorted(weighted_scores, key=lambda x: x[1], reverse=True)
        ][:5]
    
    # 电子榨菜区排序：按count降序排列，取前3个
    if time_killers:
        time_killers_with_counts = [
            (tag, filtered_tags[tag]["count"]) for tag in time_killers
        ]
        time_killers = [
            tag for tag, _ in sorted(time_killers_with_counts, key=lambda x: x[1], reverse=True)
        ][:3]
    
    # 雷区：取前3个（按平均分升序，即最不喜欢的）
    if avoid_tags:
        avoid_tags_with_scores = [
            (tag, filtered_tags[tag]["avg_score"]) for tag in avoid_tags
        ]
        avoid_tags = [
            tag for tag, _ in sorted(avoid_tags_with_scores, key=lambda x: x[1])
        ][:3]
    
    return {
        "core_favorites": core_favorites,
        "time_killers": time_killers,
        "avoid_tags": avoid_tags
    }