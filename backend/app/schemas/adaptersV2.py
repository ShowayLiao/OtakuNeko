from typing import Dict, Any, List, Optional
import logging
from datetime import datetime
from .subject import SubjectUpsert, SubjectUpsertList, SubjectRead, SubjectReadList, SubjectWithCollection, SubjectWithCollectionList
from .collection import CollectionUpsert, CollectionUpsertList, CollectionRead, CollectionReadList, CollectionWithSubject, CollectionWithSubjectList
from ..models import SubjectType
from app.models.enums import CollectionStatus
from pydantic import BaseModel, Field
from .shared import BaseList

logger = logging.getLogger(__name__)


class UnifiedCollectionSubject(BaseModel):
    """
    统一视图模型
    无论数据源是Collection还是Subject，都转换为此格式返回给前端。
    允许 collection 或 subject 任意一方为空。
    """
    collection: Optional['CollectionRead'] = Field(None, description="收藏信息，若条目未关联收藏则为 null")
    subject: Optional['SubjectRead'] = Field(None, description="条目信息，若收藏为空收藏则为 null")

    class Config:
        from_attributes = True


class UnifiedList(BaseList):
    """
    统一视图模型列表
    
    用于返回统一视图模型的列表，无论数据源是Collection还是Subject，都转换为此格式返回给前端。
    允许 collection 或 subject 任意一方为空。
    
    Attributes:
        total: 总记录数
        items: 统一视图模型列表
    """
    items: List[UnifiedCollectionSubject] = Field(default_factory=list, description="统一视图模型列表")


# 解决循环导入问题
UnifiedCollectionSubject.model_rebuild()
UnifiedList.model_rebuild()


def convert_to_collection_subject_list(
    collection_read_list: CollectionReadList, 
    subject_read_list: SubjectReadList
) -> 'CollectionSubjectList':
    """
    将 CollectionReadList 和 SubjectReadList 转换为 CollectionSubjectList
    
    Args:
        collection_read_list: 收藏读取列表
        subject_read_list: 条目读取列表
        
    Returns:
        转换后的 CollectionSubjectList 对象
    """
    from .adapters import CollectionSubject, CollectionSubjectList
    
    # 创建 subject 字典，方便通过 source 和 source_id 查找
    subject_dict = {}
    for subject in subject_read_list.items:
        key = (subject.source, subject.source_id)
        subject_dict[key] = subject
    
    # 转换 CollectionRead 为 CollectionSubject
    collection_subjects = []
    for collection in collection_read_list.items:
        # 查找对应的 subject
        key = (collection.source, collection.source_id)
        subject = subject_dict.get(key)
        
        # 创建 CollectionSubject 对象
        collection_subject = CollectionSubject(
            user_id=collection.user_id,
            source=collection.source,
            source_id=collection.source_id,
            type=collection.type,
            rate=collection.rate,
            comment=collection.comment,
            private=collection.private,
            tags=collection.tags,
            vol_status=collection.vol_status,
            ep_status=collection.ep_status,
            subject_type=collection.subject_type,
            updated_at=collection.updated_at,
            subject=subject
        )
        collection_subjects.append(collection_subject)
    
    # 创建并返回 CollectionSubjectList
    return CollectionSubjectList(
        total=collection_read_list.total,
        items=collection_subjects
    )


def bangumi_subject_to_subjectlist(data: Dict[str, Any]) -> SubjectUpsertList:
    """
    将 Bangumi 条目数据格式或收藏数据格式转换为 SubjectUpsertList 格式
    输入参考 bangumi_subject.json 或 bangumi_collection.json
    输出使用 SubjectUpsertList schema
    
    Args:
        data: 原始 Bangumi 条目 JSON 数据或收藏 JSON 数据
        
    Returns:
        转换后的 SubjectUpsertList 对象
    """
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
        
        # 处理不同格式的差异
        # 检查是否存在subject字段（收藏格式）
        if "subject" in item and isinstance(item["subject"], dict):
            # 使用收藏格式中的subject数据
            subject_data = item["subject"]
            # 从item中获取subject_id（如果存在）
            subject_id = item.get("subject_id")
            if subject_id:
                subject_upsert_data = {
                    "source": "bangumi",
                    "source_id": str(subject_id)
                }
            else:
                subject_upsert_data = {
                    "source": "bangumi",
                    "source_id": str(subject_data.get("id", ""))
                }
        else:
            # 使用直接的条目格式数据
            subject_data = item
            subject_upsert_data = {
                "source": "bangumi",
                "source_id": str(item.get("id", ""))
            }
        
        # 处理其他字段
        if "name" in subject_data:
            subject_upsert_data["name"] = subject_data["name"]
        
        if "name_cn" in subject_data:
            subject_upsert_data["name_cn"] = subject_data["name_cn"]
        
        if "type" in subject_data:
            try:
                subject_upsert_data["type"] = SubjectType(subject_data["type"])
            except ValueError:
                logger.warning(f"未知的Subject类型: {subject_data['type']}, 将使用None")
                subject_upsert_data["type"] = None
        
        if "date" in subject_data:
            subject_upsert_data["date"] = subject_data["date"]
        
        if "platform" in subject_data:
            subject_upsert_data["platform"] = subject_data["platform"]
        
        if "images" in subject_data and isinstance(subject_data["images"], dict):
            subject_upsert_data["images"] = subject_data["images"]
            # 如果存在common图片，使用它作为image字段
            if "common" in subject_data["images"]:
                subject_upsert_data["image"] = subject_data["images"]["common"]
        
        if "image" in subject_data:
            subject_upsert_data["image"] = subject_data["image"]
        
        if "summary" in subject_data:
            subject_upsert_data["summary"] = subject_data["summary"]
        
        if "tags" in subject_data and isinstance(subject_data["tags"], list):
            subject_upsert_data["tags"] = subject_data["tags"]
            # 从tags列表中提取name字段作为meta_tags
            meta_tags = []
            for tag in subject_data["tags"]:
                if isinstance(tag, dict) and "name" in tag:
                    meta_tags.append(tag["name"])
            if meta_tags:
                subject_upsert_data["meta_tags"] = meta_tags
        
        if "meta_tags" in subject_data and isinstance(subject_data["meta_tags"], list):
            subject_upsert_data["meta_tags"] = subject_data["meta_tags"]
        
        if "infobox" in subject_data and isinstance(subject_data["infobox"], list):
            subject_upsert_data["infobox"] = subject_data["infobox"]
        
        if "rating" in subject_data and isinstance(subject_data["rating"], dict):
            subject_upsert_data["rating"] = subject_data["rating"]
        
        if "collection" in subject_data and isinstance(subject_data["collection"], dict):
            subject_upsert_data["collection"] = subject_data["collection"]
        
        if "eps" in subject_data:
            subject_upsert_data["eps"] = subject_data["eps"]
        
        if "volumes" in subject_data:
            subject_upsert_data["volumes"] = subject_data["volumes"]
        
        if "series" in subject_data:
            subject_upsert_data["series"] = subject_data["series"]
        
        if "locked" in subject_data:
            subject_upsert_data["locked"] = subject_data["locked"]
        
        if "nsfw" in subject_data:
            subject_upsert_data["nsfw"] = subject_data["nsfw"]
        
        # 如果只有score字段，创建rating字典
        if "score" in subject_data and not subject_upsert_data.get("rating"):
            subject_upsert_data["rating"] = {
                "score": subject_data["score"]
            }
        
        # 使用SubjectUpsert进行验证和转换
        try:
            subject = SubjectUpsert(**subject_upsert_data)
            subjects.append(subject)
        except Exception as e:
            # 如果验证失败，跳过该条目
            logger.warning(f"验证Subject数据失败: {e}, 数据: {subject_upsert_data}")
            continue
    
    # 返回转换后的SubjectUpsertList对象
    return SubjectUpsertList(
        total=len(subjects),
        items=subjects
    )


def bangumi_collection_to_subjectlist(data: Dict[str, Any]) -> SubjectUpsertList:
    """
    将 Bangumi 收藏数据格式转换为 SubjectUpsertList 格式
    输入参考 bangumi_collection.json
    输出使用 SubjectUpsertList schema
    
    Args:
        data: 原始 Bangumi 收藏 JSON 数据
        
    Returns:
        转换后的 SubjectUpsertList 对象
    """
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
        subject_upsert_data = {
            "source": "bangumi",
            "source_id": str(subject_data.get("id", ""))
        }
        
        # 处理其他字段
        if "name" in subject_data:
            subject_upsert_data["name"] = subject_data["name"]
        
        if "name_cn" in subject_data:
            subject_upsert_data["name_cn"] = subject_data["name_cn"]
        
        if "type" in subject_data:
            try:
                subject_upsert_data["type"] = SubjectType(subject_data["type"])
            except ValueError:
                logger.warning(f"未知的Subject类型: {subject_data['type']}, 将使用None")
                subject_upsert_data["type"] = None
        
        if "date" in subject_data:
            subject_upsert_data["date"] = subject_data["date"]
        
        if "images" in subject_data and isinstance(subject_data["images"], dict):
            subject_upsert_data["images"] = subject_data["images"]
            # 如果存在common图片，使用它作为image字段
            if "common" in subject_data["images"]:
                subject_upsert_data["image"] = subject_data["images"]["common"]
        
        if "tags" in subject_data and isinstance(subject_data["tags"], list):
            subject_upsert_data["tags"] = subject_data["tags"]
            # 从tags列表中提取name字段作为meta_tags
            meta_tags = []
            for tag in subject_data["tags"]:
                if isinstance(tag, dict) and "name" in tag:
                    meta_tags.append(tag["name"])
            if meta_tags:
                subject_upsert_data["meta_tags"] = meta_tags
        
        if "score" in subject_data:
            # 如果只有score字段，创建rating字典
            subject_upsert_data["rating"] = {
                "score": subject_data["score"]
            }
        
        if "eps" in subject_data:
            subject_upsert_data["eps"] = subject_data["eps"]
        
        if "volumes" in subject_data:
            subject_upsert_data["volumes"] = subject_data["volumes"]
        
        if "collection" in subject_data and isinstance(subject_data["collection"], dict):
            subject_upsert_data["collection"] = subject_data["collection"]
        
        # 使用SubjectUpsert进行验证和转换
        try:
            subject = SubjectUpsert(**subject_upsert_data)
            subjects.append(subject)
        except Exception as e:
            # 如果验证失败，跳过该条目
            logger.warning(f"验证Subject数据失败: {e}, 数据: {subject_upsert_data}")
            continue
    
    # 返回转换后的SubjectUpsertList对象
    return SubjectUpsertList(
        total=len(subjects),
        items=subjects
    )


def bangumi_collection_to_collectionlist(data: Dict[str, Any], user_id: int) -> CollectionUpsertList:
    """
    将 Bangumi 收藏数据格式转换为 CollectionUpsertList 格式
    输入参考 bangumi_collection.json
    输出使用 CollectionUpsertList schema
    
    Args:
        data: 原始 Bangumi 收藏 JSON 数据
        user_id: 用户ID，用于设置 CollectionUpsert 中的 user_id 字段
        
    Returns:
        转换后的 CollectionUpsertList 对象
    """
    # 确保data是字典类型
    if not isinstance(data, dict):
        raise ValueError("Input data must be a dictionary")
    
    # 提取data数组，支持直接传入data字段或完整的JSON结构
    raw_items = data.get("data", [])
    if not isinstance(raw_items, list):
        raw_items = []
    
    collections = []
    
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
        collection_upsert_data = {
            "user_id": user_id,
            "source": "bangumi",
            "source_id": str(item.get("subject_id", subject_data.get("id", ""))),
            "type": CollectionStatus(2)  # 默认值为"看过"
        }
        
        # 处理其他字段
        if "type" in item:
            try:
                collection_upsert_data["type"] = CollectionStatus(item["type"])
            except ValueError:
                logger.warning(f"未知的Collection类型: {item['type']}, 将使用默认值 2 (看过)")
                collection_upsert_data["type"] = CollectionStatus(2)
        
        if "rate" in item:
            collection_upsert_data["rate"] = item["rate"]
        
        if "comment" in item:
            collection_upsert_data["comment"] = item["comment"]
        
        if "private" in item:
            collection_upsert_data["private"] = item["private"]
        
        if "tags" in item and isinstance(item["tags"], list):
            collection_upsert_data["tags"] = item["tags"]
        
        if "vol_status" in item:
            collection_upsert_data["vol_status"] = item["vol_status"]
        
        if "ep_status" in item:
            collection_upsert_data["ep_status"] = item["ep_status"]
        
        if "subject_type" in item:
            collection_upsert_data["subject_type"] = item["subject_type"]
        elif "type" in subject_data:
            collection_upsert_data["subject_type"] = subject_data["type"]

        if "updated_at" in item:
            try:
                # 尝试将updated_at转换为datetime对象
                from datetime import datetime, timezone
                updated_at_value = item["updated_at"]
                if isinstance(updated_at_value, str):
                    # 解析ISO格式的字符串（Bangumi API返回的格式）
                    dt = datetime.fromisoformat(updated_at_value)
                    # 转换为UTC时间并移除时区信息，避免数据库操作时的时区冲突
                    if dt.tzinfo:
                        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
                    collection_upsert_data["updated_at"] = dt
                elif isinstance(updated_at_value, datetime):
                    # 已经是datetime对象，确保移除时区信息
                    if updated_at_value.tzinfo:
                        updated_at_value = updated_at_value.astimezone(timezone.utc).replace(tzinfo=None)
                    collection_upsert_data["updated_at"] = updated_at_value
                else:
                    # 其他类型，使用当前UTC时间（不带时区信息）
                    logger.warning(f"updated_at类型不正确，使用当前UTC时间: {type(updated_at_value)}")
                    collection_upsert_data["updated_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
            except Exception as e:
                # 如果处理失败，使用当前UTC时间（不带时区信息）
                from datetime import datetime, timezone
                logger.warning(f"处理updated_at失败: {e}")
                collection_upsert_data["updated_at"] = datetime.now(timezone.utc).replace(tzinfo=None)
        
        # 使用CollectionUpsert进行验证和转换
        try:
            collection = CollectionUpsert(**collection_upsert_data)
            collections.append(collection)
        except Exception as e:
            # 如果验证失败，跳过该条目
            logger.warning(f"验证Collection数据失败: {e}, 数据: {collection_upsert_data}")
            continue
    
    # 返回转换后的CollectionUpsertList对象
    return CollectionUpsertList(
        total=len(collections),
        collections=collections
    )


def douban_to_bangumi_list(douban_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    将豆瓣数据转换为 Bangumi 收藏格式列表
    输入参考 tofu[208745052].json
    输出参考 bangumi_collection.json
    
    Args:
        douban_data: 豆瓣数据（字典格式）
        
    Returns:
        Bangumi 收藏格式的 JSON 数据列表
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
    
    # 提取interest数组
    interest_items = douban_data.get("interest", [])
    if not isinstance(interest_items, list):
        interest_items = []
    
    bangumi_items = []
    
    for item in interest_items:
        # 确保item是字典类型
        if not isinstance(item, dict):
            continue
        
        # 提取interest数据
        db_interest = item.get("interest", {})
        if not isinstance(db_interest, dict):
            continue
        
        # 获取状态和类型
        db_status = db_interest.get("status", "")
        bgm_type = status_map.get(db_status, 2)

        # 直接从interest数据中获取subject
        db_subject = db_interest.get("subject", {})
        if not isinstance(db_subject, dict):
            continue
        
        # 获取subject类型
        db_subject_type = db_subject.get("type", "")
        bgm_subject_type = subject_type_map.get(db_subject_type, 1)

        if db_subject_type not in subject_type_map:
            logger.warning(f"无法识别的豆瓣类型: '{db_subject_type}'，使用默认值 1 (书籍)")

        # 处理图片
        pic = db_subject.get("pic", {})
        if not isinstance(pic, dict):
            pic = {}
        
        large_url = pic.get("large", "")
        normal_url = pic.get("normal", "")
        small_url = pic.get("small", "")
        medium_url = pic.get("medium", "")
        grid_url = pic.get("grid", "")
        
        # 处理评分
        rating = db_interest.get("rating", {})
        if isinstance(rating, dict):
            rate = rating.get("value", 0)
            # 豆瓣评分是5分制，转换为10分制
            rate = int(rate * 2)
        else:
            rate = 0

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
        bangumi_item = {
            "updated_at": db_interest.get("create_time", ""),
            "comment": db_interest.get("comment", "") or None,
            "tags": db_interest.get("tags", []),
            "subject": {
                "date": db_subject.get("pubdate", [""])[0] if isinstance(db_subject.get("pubdate"), list) else db_subject.get("pubdate", ""),
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
                "score": db_subject.get("rating", {}).get("value", 0) if isinstance(db_subject.get("rating"), dict) else 0,
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
            "rate": rate,
            "private": db_interest.get("is_private", False)
        }
        
        bangumi_items.append(bangumi_item)
    
    # 返回Bangumi格式的列表
    return {
        "data": bangumi_items
    }


def douban_to_subjectlist(douban_data: Dict[str, Any]) -> SubjectUpsertList:
    """
    将豆瓣数据转换为 SubjectUpsertList 格式
    先转换为 Bangumi 收藏格式，再调用 bangumi_subject_to_subjectlist
    
    Args:
        douban_data: 豆瓣数据（字典格式）
        
    Returns:
        转换后的 SubjectUpsertList 对象
    """
    # 先转换为 Bangumi 收藏格式
    bangumi_data = douban_to_bangumi_list(douban_data)
    
    # 调用 bangumi_subject_to_subjectlist 进行转换
    return bangumi_subject_to_subjectlist(bangumi_data)


def douban_to_collectionlist(douban_data: Dict[str, Any], user_id: int) -> CollectionUpsertList:
    """
    将豆瓣数据转换为 CollectionUpsertList 格式
    先转换为 Bangumi 收藏格式，再调用 bangumi_collection_to_collectionlist
    
    Args:
        douban_data: 豆瓣数据（字典格式）
        user_id: 用户ID，用于设置 CollectionUpsert 中的 user_id 字段
        
    Returns:
        转换后的 CollectionUpsertList 对象
    """
    # 先转换为 Bangumi 收藏格式
    bangumi_data = douban_to_bangumi_list(douban_data)
    
    # 调用 bangumi_collection_to_collectionlist 进行转换
    return bangumi_collection_to_collectionlist(bangumi_data, user_id)


def collection_with_subject_to_unified(
    collection_with_subject: CollectionWithSubject
) -> UnifiedCollectionSubject:
    """
    将 CollectionWithSubject 转换为 UnifiedCollectionSubject
    
    Args:
        collection_with_subject: 收藏及其关联条目信息
        
    Returns:
        转换后的统一视图模型对象
    """
    return UnifiedCollectionSubject(
        subject=collection_with_subject.subject,
        collection=collection_with_subject.collection
    )


def collection_with_subject_list_to_unified_list(
    collection_with_subject_list: CollectionWithSubjectList
) -> UnifiedList:
    """
    将 CollectionWithSubjectList 转换为 UnifiedList
    
    Args:
        collection_with_subject_list: 收藏及其关联条目信息列表
        
    Returns:
        转换后的统一视图模型列表
    """
    items = [
        collection_with_subject_to_unified(item)
        for item in collection_with_subject_list.items
    ]
    return UnifiedList(
        total=collection_with_subject_list.total,
        items=items
    )


def subject_with_collection_to_unified(
    subject_with_collection: SubjectWithCollection
) -> UnifiedCollectionSubject:
    """
    将 SubjectWithCollection 转换为 UnifiedCollectionSubject
    
    Args:
        subject_with_collection: 条目及其关联收藏信息
        
    Returns:
        转换后的统一视图模型对象
    """
    return UnifiedCollectionSubject(
        subject=subject_with_collection.subject,
        collection=subject_with_collection.collection
    )


def subject_with_collection_list_to_unified_list(
    subject_with_collection_list: SubjectWithCollectionList
) -> UnifiedList:
    """
    将 SubjectWithCollectionList 转换为 UnifiedList
    
    Args:
        subject_with_collection_list: 条目及其关联收藏信息列表
        
    Returns:
        转换后的统一视图模型列表
    """
    items = [
        subject_with_collection_to_unified(item)
        for item in subject_with_collection_list.items
    ]
    return UnifiedList(
        total=subject_with_collection_list.total,
        items=items
    )


def bangumi_search_to_unified_list(data: Dict[str, Any]) -> UnifiedList:
    """
    将 Bangumi 搜索响应数据转换为 UnifiedList 格式
    输入参考 Bangumi API 搜索响应
    输出使用 UnifiedList schema
    
    Args:
        data: 原始 Bangumi 搜索响应 JSON 数据
        
    Returns:
        转换后的 UnifiedList 对象
    """
    # 确保data是字典类型
    if not isinstance(data, dict):
        raise ValueError("Input data must be a dictionary")
    
    # 提取data数组，支持直接传入data字段或完整的JSON结构
    raw_items = data.get("data", [])
    if not isinstance(raw_items, list):
        raw_items = []
    
    items = []
    
    for item in raw_items:
        # 确保item是字典类型
        if not isinstance(item, dict):
            continue
        
        # 处理类型
        subject_type = item.get("type")
        try:
            type_enum = SubjectType(subject_type) if subject_type else None
        except ValueError:
            logger.warning(f"未知的Subject类型: {subject_type}, 将使用None")
            type_enum = None
        
        # 构造SubjectRead数据
        subject_read = SubjectRead(
            id=0,  # 默认ID，数据库中会生成
            source="bangumi",
            source_id=str(item.get("id", "")),
            name=item.get("name", ""),
            name_cn=item.get("name_cn", ""),
            type=type_enum,
            summary=item.get("summary"),
            date=item.get("date", ""),
            platform=item.get("platform", ""),
            eps=item.get("eps"),
            volumes=item.get("volumes"),
            images=item.get("images", {}),
            image=item.get("image", ""),
            tags=item.get("tags", []),
            meta_tags=item.get("meta_tags", []),
            infobox=item.get("infobox", []),
            rating=item.get("rating", {}),
            collection=item.get("collection", {}),
            series=item.get("series", False),
            locked=item.get("locked", False),
            nsfw=item.get("nsfw", False),
        )
        
        # 构造UnifiedCollectionSubject对象
        unified_item = UnifiedCollectionSubject(
            subject=subject_read,
            collection=None  # 搜索响应中可能没有收藏数据
        )
        
        items.append(unified_item)
    
    # 返回转换后的UnifiedList对象
    return UnifiedList(
        total=len(items),
        items=items
    )


