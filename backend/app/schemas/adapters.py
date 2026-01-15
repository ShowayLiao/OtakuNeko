from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


def adapt_bangumi_subject(bangumi_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    将 Bangumi 官方 API 返回的原始 JSON 数据适配为数据库 Subject 模型格式
    
    Args:
        bangumi_data: Bangumi API 返回的原始 JSON 数据 (参考 bangumi_subject.json)
        
    Returns:
        适配后的 Subject 数据字典
    """
    from ..models import SubjectType
    
    # 处理图片
    images = bangumi_data.get("images", {})
    cover_url = images.get("large", images.get("common", ""))
    
    # 处理评分信息
    rating = bangumi_data.get("rating", {})
    score = rating.get("score")
    rank = rating.get("rank")
    rating_details = rating.copy()
    
    # 处理标签
    tags = []
    raw_tags = bangumi_data.get("tags", [])
    if raw_tags:
        tags = [tag["name"] for tag in raw_tags if isinstance(tag, dict) and "name" in tag]
    
    # 处理收藏统计
    collection = bangumi_data.get("collection", {})
    collection_total = sum(collection.values()) if collection else None
    
    # 处理类型
    subject_type = bangumi_data.get("type")
    try:
        type_enum = SubjectType(subject_type) if subject_type else None
    except ValueError:
        logger.warning(f"未知的Subject类型: {subject_type}, 将使用None")
        type_enum = None
    
    # 构造适配后的数据
    adapted_data = {
        "source": "bangumi",
        "source_id": str(bangumi_data.get("id", "")),
        "type": type_enum,
        "name": bangumi_data.get("name", ""),
        "name_cn": bangumi_data.get("name_cn", ""),
        "summary": bangumi_data.get("summary"),
        "cover_url": cover_url,
        "images": images,
        "date": bangumi_data.get("date"),
        "platform": bangumi_data.get("platform"),
        "score": score,
        "rank": rank,
        "eps": bangumi_data.get("eps"),
        "volumes": bangumi_data.get("volumes"),
        "collection_total": collection_total,
        "tags": tags,
        "meta_tags": bangumi_data.get("meta_tags", []),
        "infobox": bangumi_data.get("infobox", []),
        "rating_details": rating_details
    }
    
    return adapted_data


def convert_douban_to_bangumi(douban_item: Dict[str, Any]) -> Dict[str, Any]:
    """
    将豆瓣数据转换为 Bangumi 收藏格式

    Args:
        douban_item: 豆瓣收藏项（字典格式）

    Returns:
        Bangumi 收藏格式的 JSON 数据
    """
    status_map = {
        "mark": 1,
        "done": 2,
        "doing": 3,
    }

    subject_type_map = {
        "book": 1,
        "movie": 6,
        "tv": 6,
        "music": 3,
        "game": 4
    }

    db_status = douban_item.get("status", "")
    bgm_type = status_map.get(db_status, 2)

    db_subject_type = douban_item.get("type", "")
    bgm_subject_type = subject_type_map.get(db_subject_type, 1)

    if db_subject_type not in subject_type_map:
        logger.warning(f"无法识别的豆瓣类型: '{db_subject_type}'，使用默认值 1 (书籍)")

    db_interest = douban_item.get("interest", {})
    db_subject = db_interest.get("subject", {})

    pic = db_subject.get("pic", {})
    large_url = pic.get("large", "")
    normal_url = pic.get("normal", "")
    small_url = pic.get("small", "")
    medium_url = pic.get("medium", "")
    grid_url = pic.get("grid", "")
    
    cover_url = large_url or normal_url or ""

    rating = db_interest.get("rating", {})
    rate = rating.get("value", 0) if rating else 0

    db_tags = db_subject.get("genres", [])
    bangumi_tags = []
    for tag in db_tags:
        if isinstance(tag, str):
            bangumi_tags.append({
                "name": tag,
                "count": 0,
                "total_cont": 0
            })
        elif isinstance(tag, dict):
            bangumi_tags.append({
                "name": tag.get("name", ""),
                "count": tag.get("count", 0),
                "total_cont": tag.get("total_cont", 0)
            })


    bangumi_data = {
        "updated_at": db_interest.get("create_time", ""),
        "comment": db_interest.get("comment", "") or None,
        "tags": db_interest.get("tags", []),
        "subject": {
            "date": db_subject.get("pubdate", [""])[0],
            "images": {
                "large": large_url,
                "common": normal_url,
                "medium": medium_url,
                "small": small_url,
                "grid": grid_url
            },
            "name": db_subject.get("title", ""),
            "name_cn": db_subject.get("title", ""),
            "short_summary": db_subject.get("intro", ""),
            "tags": bangumi_tags,
            "score": db_subject.get("rating", {}).get("value", 0),
            "id": int(db_subject.get("id", 0)),
            "type": bgm_subject_type,
            "eps": 0,
            "volumes": 0,
            "collection_total": 0,
            "rank": 0
        },
        "subject_id": int(db_subject.get("id", 0)),
        "vol_status": 0,
        "ep_status": 0,
        "subject_type": bgm_subject_type,
        "type": bgm_type,
        "rate": rate*2,
        "private": db_interest.get("is_private", False)
    }

    return bangumi_data
