from typing import Dict, Any, Optional, List
import logging
from datetime import datetime

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
    
    # 处理类型
    subject_type = bangumi_data.get("type")
    try:
        type_enum = SubjectType(subject_type) if subject_type else None
    except ValueError:
        logger.warning(f"未知的Subject类型: {subject_type}, 将使用None")
        type_enum = None
    
    # 构造适配后的数据，直接映射 bangumi_subject.json 中的字段到 Subject 模型
    adapted_data = {
        "source": "bangumi",
        "source_id": str(bangumi_data.get("id", "")),
        "type": type_enum,
        "name": bangumi_data.get("name", ""),
        "name_cn": bangumi_data.get("name_cn", ""),
        "summary": bangumi_data.get("summary"),
        "date": bangumi_data.get("date", ""),
        "platform": bangumi_data.get("platform", ""),
        "images": bangumi_data.get("images", {}),
        "image": bangumi_data.get("image", ""),
        "tags": bangumi_data.get("tags", []),
        "meta_tags": bangumi_data.get("meta_tags", []),
        "infobox": bangumi_data.get("infobox", []),
        "rating": bangumi_data.get("rating", {}),
        "collection": bangumi_data.get("collection", {}),
        "eps": bangumi_data.get("eps"),
        "volumes": bangumi_data.get("volumes"),
        "series": bangumi_data.get("series", False),
        "locked": bangumi_data.get("locked", False),
        "nsfw": bangumi_data.get("nsfw", False)
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

    # 直接使用douban_item作为interest数据，因为它已经是interest列表中的元素
    db_interest = douban_item
    
    # 获取状态和类型
    db_status = db_interest.get("status", "")
    bgm_type = status_map.get(db_status, 2)

    # 直接从interest数据中获取subject
    db_subject = db_interest.get("subject", {})
    
    # 获取subject类型
    db_subject_type = db_subject.get("type", "")
    bgm_subject_type = subject_type_map.get(db_subject_type, 1)

    if db_subject_type not in subject_type_map:
        logger.warning(f"无法识别的豆瓣类型: '{db_subject_type}'，使用默认值 1 (书籍)")

    # 处理图片
    pic = db_subject.get("pic", {})
    large_url = pic.get("large", "")
    normal_url = pic.get("normal", "")
    small_url = pic.get("small", "")
    medium_url = pic.get("medium", "")
    grid_url = pic.get("grid", "")
    
    cover_url = large_url or normal_url or ""

    # 处理评分
    rating = db_interest.get("rating", {})
    rate = rating.get("value", 0) if rating else 0

    # 处理标签
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

    # 构造bangumi格式数据
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


def adapt_to_subject_list(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    将两种不同的JSON数据格式转换为SubjectList格式
    支持两种数据格式：
    1. bangumi_collection.json格式
    2. collection_subject.json格式
    
    Args:
        data: 原始JSON数据
        
    Returns:
        转换后的SubjectList格式数据
    """
    from typing import Any, List
    from .subject import SubjectBase
    
    # 确保data是字典类型
    if not isinstance(data, dict):
        raise ValueError("Input data must be a dictionary")
    
    # 提取data数组，支持直接传入data字段或完整的JSON结构
    raw_items = data.get("data", [])
    if not isinstance(raw_items, list):
        raw_items = []
    
    subjects = []
    
    for item in raw_items:
        # 确保item是字典类型
        if not isinstance(item, dict):
            continue
        
        # 提取subject数据
        subject_data = item.get("subject", {})
        
        # 确保subject_data是字典类型
        if not isinstance(subject_data, dict):
            continue
        
        # 处理不同格式的差异
        # 设置默认值
        if "source" not in subject_data:
            subject_data["source"] = "bangumi"
        
        # 处理source_id，使用subject的id或外部的subject_id
        if "source_id" not in subject_data:
            # 优先使用subject的id
            subject_id = subject_data.get("id")
            if subject_id:
                subject_data["source_id"] = str(subject_id)
            # 其次使用外部的subject_id
            elif "subject_id" in item:
                subject_data["source_id"] = str(item["subject_id"])
            else:
                # 如果没有source_id，跳过该条目
                continue
        
        # 处理images字段
        if "images" in subject_data and isinstance(subject_data["images"], dict):
            # 如果存在common图片，使用它作为image字段
            if "common" in subject_data["images"] and not subject_data.get("image"):
                subject_data["image"] = subject_data["images"]["common"]
        
        # 处理meta_tags字段
        if "meta_tags" not in subject_data and "tags" in subject_data:
            # 从tags列表中提取name字段作为meta_tags
            if isinstance(subject_data["tags"], list):
                meta_tags = []
                for tag in subject_data["tags"]:
                    if isinstance(tag, dict) and "name" in tag:
                        meta_tags.append(tag["name"])
                subject_data["meta_tags"] = meta_tags
        
        # 处理type字段，确保它是整数
        if "type" in subject_data:
            subject_data["type"] = int(subject_data["type"])
        else:
            subject_data["type"] = 2
        
        # 处理评分信息
        if "score" in subject_data and not subject_data.get("rating"):
            # 如果只有score字段，创建rating字典
            subject_data["rating"] = {
                "score": subject_data["score"]
            }
        
        # 确保name字段存在
        if "name" not in subject_data:
            # 使用name_cn或默认名称
            if "name_cn" in subject_data:
                subject_data["name"] = subject_data["name_cn"]
            else:
                subject_data["name"] = f"Subject {subject_data.get('source_id', 'unknown')}"
        
        # 使用SubjectBase进行验证和转换
        try:
            subject = SubjectBase.model_validate(subject_data)
            subjects.append(subject)
        except Exception as e:
            # 如果验证失败，跳过该条目
            logger.warning(f"验证Subject数据失败: {e}, 数据: {subject_data}")
            continue
    
    # 返回转换后的SubjectList格式
    return {
        "total": len(subjects),
        "items": subjects
    }


def adapt_to_collection_read(subject: Any, collection: Optional[Any] = None) -> Any:
    """
    将Subject和Collection对象转换为CollectionRead格式
    
    Args:
        subject: Subject对象
        collection: Collection对象（可选）
        
    Returns:
        转换后的CollectionRead格式数据
    """
    from .subject import SubjectRead
    from .collection import CollectionRead, CollectionBase
    from typing import Optional
    
    # 构造CollectionRead数据
    if collection:
        # 如果有collection数据，使用collection数据作为基础
        collection_dict = collection.model_dump()
        # 添加subject信息
        if subject:
            collection_dict["subject"] = SubjectRead.model_validate(subject)
        else:
            collection_dict["subject"] = None
        return CollectionRead.model_validate(collection_dict)
    elif subject:
        # 如果没有collection数据，使用subject数据构造CollectionRead
        subject_dict = subject.model_dump()
        # 使用Subject信息构造CollectionBase基础数据
        from ..models.enums import CollectionStatus
        collection_base = CollectionBase(
            type=CollectionStatus.COLLECT,  # 默认类型为"看过"
            source=subject_dict.get("source", "bangumi"),
            source_id=subject_dict.get("source_id", ""),
            updated_at=datetime.now(),  # 当前时间
            rate=None,
            comment=None,
            private=False,
            tags=[],
            vol_status=0,
            ep_status=0,
            subject_type=subject_dict.get("type", 0)
        )
        # 构造CollectionRead数据
        collection_read = CollectionRead(
            **collection_base.model_dump(),
            user_id=0,  # 默认用户ID
            subject=SubjectRead.model_validate(subject_dict)
        )
        return collection_read
    else:
        # 如果两者都没有，返回None
        return None


def adapt_to_collection_list(subjects: List[Any], collections: List[Optional[Any]] = None) -> Any:
    """
    将Subject对象列表转换为CollectionList格式
    
    Args:
        subjects: Subject对象列表
        collections: Collection对象列表（可选）
        
    Returns:
        转换后的CollectionList格式数据
    """
    from .collection import CollectionList
    from typing import List, Optional
    
    # 确保collections是列表
    if collections is None:
        collections = [None] * len(subjects)
    
    # 确保collections和subjects长度一致
    if len(collections) != len(subjects):
        # 扩展collections到subjects长度
        collections = collections + [None] * (len(subjects) - len(collections))
    
    # 转换为CollectionRead列表
    collection_read_items = []
    for subject, collection in zip(subjects, collections):
        collection_read = adapt_to_collection_read(subject, collection)
        if collection_read:
            collection_read_items.append(collection_read)
    
    # 构造CollectionList数据
    return CollectionList(
        total=len(collection_base_items),
        items=collection_base_items
    )


def adapt_bangumi_collection_to_list(bangumi_data: Dict[str, Any]) -> Any:
    """
    将bangumi_collection.json格式转换为CollectionList格式
    
    Args:
        bangumi_data: bangumi_collection.json格式的数据
        
    Returns:
        转换后的CollectionList格式数据
    """
    from .collection import CollectionList, CollectionRead, CollectionBase, CollectionCreate
    from .subject import SubjectRead, SubjectBase
    from typing import List
    import datetime
    from app.models.enums import CollectionStatus
    
    # 提取data数组
    raw_items = bangumi_data.get("data", [])
    if not isinstance(raw_items, list):
        raw_items = []
    
    # 构造CollectionBase列表
    collection_base_items = []
    for item in raw_items:
        # 确保item是字典
        if not isinstance(item, dict):
            continue
        
        try:
            # 提取subject数据
            subject_data = item.get("subject", {})
            if not subject_data:
                continue
            
            # 构造CollectionBase数据，使用兼容的方式解析日期字符串
            updated_at_str = item.get("updated_at")
            if updated_at_str:
                try:
                    # 尝试使用fromisoformat（Python 3.7+）
                    updated_at = datetime.datetime.fromisoformat(updated_at_str)
                    # 移除时区信息，转换为 naive datetime
                    updated_at = updated_at.replace(tzinfo=None)
                except (AttributeError, ValueError):
                    # 如果不支持fromisoformat或格式错误，使用dateutil.parser（兼容Python 3.6-）
                    try:
                        from dateutil.parser import parse
                        updated_at = parse(updated_at_str)
                        # 移除时区信息，转换为 naive datetime
                        updated_at = updated_at.replace(tzinfo=None)
                    except Exception:
                        # 如果所有解析方法都失败，使用当前时间
                        updated_at = datetime.datetime.now()
            else:
                updated_at = datetime.datetime.now()
            
            collection_base = CollectionBase(
                type=CollectionStatus(item.get("type", 0)),
                source="bangumi",
                source_id=str(item.get("subject_id", subject_data.get("id", ""))),
                updated_at=updated_at,
                rate=item.get("rate"),
                comment=item.get("comment"),
                private=item.get("private", False),
                tags=item.get("tags", []),
                vol_status=item.get("vol_status", 0),
                ep_status=item.get("ep_status", 0),
                subject_type=item.get("subject_type", subject_data.get("type", 0))
            )
            
            # 将CollectionBase对象添加到列表中
            collection_base_items.append(collection_base)
        except Exception as e:
            logger.error(f"转换bangumi_collection数据失败: {e}, 数据: {item}")
            continue
    
    # 构造CollectionList数据
    return CollectionList(
        total=len(collection_base_items),
        items=collection_base_items
    )


def adapt_remote_data_to_collection_list(remote_data: Dict[str, Any]) -> Any:
    """
    将远程API返回的数据转换为CollectionList格式
    
    Args:
        remote_data: 远程API返回的原始数据
        
    Returns:
        转换后的CollectionList格式数据
    """
    from .collection import CollectionList, CollectionRead, CollectionBase
    from .subject import SubjectRead, SubjectBase
    from typing import List
    import datetime
    
    # 提取data数组
    raw_items = remote_data.get("data", [])
    if not isinstance(raw_items, list):
        raw_items = []
    
    # 使用adapt_to_subject_list转换数据
    adapted_data = adapt_to_subject_list({"data": raw_items})
    
    # 构造CollectionRead列表
    collection_read_items = []
    for subject_data in adapted_data["items"]:
        # 构造SubjectRead数据
        subject_read = SubjectRead(
            **subject_data.model_dump(),
            id=0  # 默认ID
        )
        
        # 构造CollectionBase数据
        collection_base = CollectionBase(
            type=0,  # 默认类型
            source=subject_data.source,
            source_id=subject_data.source_id,
            updated_at=datetime.now(),  # 当前时间
            rate=None,
            comment=None,
            private=False,
            tags=[],
            vol_status=0,
            ep_status=0,
            subject_type=subject_data.type
        )
        
        # 构造CollectionRead数据
        collection_read = CollectionRead(
            **collection_base.model_dump(),
            user_id=0,  # 默认用户ID
            subject=subject_read
        )
        
        collection_read_items.append(collection_read)
    
    # 构造CollectionList数据
    return CollectionList(
        total=len(collection_read_items),
        items=collection_read_items
    )



def adapt_douban_data_to_collection_list(douban_data: List[Dict[str, Any]]) -> Any:
    """
    将豆瓣数据转换为CollectionList格式
    
    Args:
        douban_data: 豆瓣数据列表
        
    Returns:
        转换后的CollectionList格式数据
    """
    from .collection import CollectionList, CollectionRead, CollectionBase
    from .subject import SubjectRead, SubjectBase
    from typing import List
    import datetime
    from app.models.enums import CollectionStatus
    
    # 构造CollectionRead列表
    collection_read_items = []
    for douban_item in douban_data:
        try:
            # 先将豆瓣数据转换为bangumi格式
            bangumi_data = convert_douban_to_bangumi(douban_item)
            
            # 提取subject数据
            subject_data = bangumi_data.get("subject", {})
            if not subject_data:
                continue
            
            # 处理subject数据，设置source为douban
            subject_data["source"] = "douban"
            if "source_id" not in subject_data:
                subject_data["source_id"] = str(subject_data.get("id", ""))
            
            # 构造SubjectRead数据，确保id参数只传递一次
            subject_copy = subject_data.copy()
            # 移除subject_copy中的id字段，使用显式传递的id=0
            subject_copy.pop('id', None)
            
            subject_read = SubjectRead(
                id=0,  # 默认ID，会在数据库中生成
                **subject_copy
            )
            
            # 处理updated_at字段，兼容豆瓣的时间格式
            updated_at_str = bangumi_data.get("updated_at", "")
            try:
                if updated_at_str:
                    # 将豆瓣时间格式转换为ISO格式（替换空格为T）
                    if " " in updated_at_str:
                        updated_at_str = updated_at_str.replace(" ", "T")
                    updated_at = datetime.fromisoformat(updated_at_str)
                else:
                    updated_at = datetime.now()
            except ValueError:
                # 如果解析失败，使用当前时间
                updated_at = datetime.now()
            
            # 构造CollectionBase数据
            collection_base = CollectionBase(
                type=CollectionStatus(bangumi_data.get("type", 0)),
                source="douban",
                source_id=str(bangumi_data.get("subject_id", subject_data.get("id", ""))),
                updated_at=updated_at,
                rate=bangumi_data.get("rate"),
                comment=bangumi_data.get("comment"),
                private=bangumi_data.get("private", False),
                tags=bangumi_data.get("tags", []),
                vol_status=bangumi_data.get("vol_status", 0),
                ep_status=bangumi_data.get("ep_status", 0),
                subject_type=bangumi_data.get("subject_type", subject_data.get("type", 0))
            )
            
            # 构造CollectionRead数据
            collection_read = CollectionRead(
                user_id=0,  # 默认用户ID，会在后续处理中设置
                subject=subject_read,
                **collection_base.model_dump()
            )
            
            collection_read_items.append(collection_read)
        except Exception as e:
            logger.error(f"转换豆瓣数据失败: {e}, 数据: {douban_item}")
            continue
    
    # 构造CollectionList数据
    return CollectionList(
        total=len(collection_read_items),
        items=collection_read_items
    )
