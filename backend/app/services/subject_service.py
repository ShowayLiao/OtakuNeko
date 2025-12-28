from typing import Optional, List, Dict, Any
from sqlmodel import select, or_
from sqlalchemy.ext.asyncio import AsyncSession
from app.models import Subject, SubjectType, Collection, User
from app.services.bangumi_client import search_subjects as search_bangumi_subjects
from app.services.bangumi_service import adapt_bangumi_subject
from app.schemas.collection import SubjectWithUserStatus, CollectionOut
from app.models.enums import CollectionStatus
import logging

logger = logging.getLogger(__name__)

# 收藏状态枚举值到字符串的映射
COLLECTION_STATUS_MAP = {
    CollectionStatus.WISH.value: "wish",       # 1 -> "wish"
    CollectionStatus.COLLECT.value: "collect", # 2 -> "collect"
    CollectionStatus.DO.value: "do",           # 3 -> "do"
    CollectionStatus.ON_HOLD.value: "on_hold", # 4 -> "on_hold"
    CollectionStatus.DROPPED.value: "dropped"  # 5 -> "dropped"
}


async def search_subjects(
    db: AsyncSession,
    keyword: Optional[str] = None,
    subject_type: Optional[int] = None,
    user_id: Optional[int] = None,
    limit: int = 20,
    offset: int = 0
) -> List[Dict[str, Any]]:
    """
    在本地数据库的所有 Subject 中搜索
    
    Args:
        db: 数据库会话
        keyword: 搜索关键词 (可选)
        subject_type: 条目类型 (1=书籍/2=动画/3=音乐/4=游戏/6=三次元) (可选)
        user_id: 用户ID，用于查询收藏状态 (可选)
        limit: 返回结果数量限制
        offset: 结果偏移量
    
    Returns:
        SubjectWithUserStatus 字典列表
    """
    # 构建查询，使用 LEFT JOIN 获取收藏状态
    if user_id:
        query = select(Subject, Collection).outerjoin(
            Collection,
            (Collection.subject_id == Subject.id) & (Collection.user_id == user_id)
        )
    else:
        query = select(Subject)
    
    # 添加过滤条件
    if keyword:
        # 使用 ilike 实现大小写不敏感的模糊搜索，同时在 name 和 name_cn 字段中匹配
        query = query.where(
            or_(
                Subject.name.ilike(f"%{keyword}%"),
                Subject.name_cn.ilike(f"%{keyword}%")
            )
        )
    
    if subject_type:
        try:
            # 验证 subject_type 是否有效
            subject_type_enum = SubjectType(subject_type)
            query = query.where(Subject.type == subject_type_enum)
        except ValueError:
            # 如果类型无效，返回空列表
            return []
    
    # 添加分页
    query = query.limit(limit).offset(offset)
    
    # 执行查询
    result = await db.execute(query)
    rows = result.all()
    
    # 构造结果列表
    final_list = []
    for row in rows:
        if user_id:
            subject, collection = row
        else:
            subject = row[0] if isinstance(row, tuple) else row
            collection = None
        
        # 从 Subject 对象构造基础数据
        item_dict = SubjectWithUserStatus.model_validate(subject).model_dump()
        
        # 检查是否已收藏
        if collection:
            item_dict["is_collected"] = True
            # 构造收藏信息
            status_str = COLLECTION_STATUS_MAP.get(collection.type.value) if collection.type else None
            collection_info = CollectionOut(
                subject_id=collection.subject_id,
                status=status_str,
                rate=collection.rate,
                comment=collection.comment,
                private=collection.private,
                tags=collection.tags or [],
                updated_at=collection.updated_at.isoformat() if collection.updated_at else None
            )
            item_dict["collection_info"] = collection_info.model_dump()
        else:
            item_dict["is_collected"] = False
            item_dict["collection_info"] = None
        
        final_list.append(item_dict)
    
    return final_list


async def search_mixed(
    db: AsyncSession,
    keyword: str,
    subject_type: Optional[int] = None,
    user_id: Optional[int] = None,
    limit: int = 20,
    offset: int = 0
) -> Dict[str, Any]:
    """
    混合搜索服务：本地优先，远程回退
    
    实现策略：
    1. Step 1 (Local): 使用 SQL LIKE 查询本地 Subject 表，同时查询用户收藏状态
    2. Step 2 (Remote Check): 如果本地结果数量为 0，则调用 Bangumi API
    3. Step 3 (Adaptation): 如果数据来自 Remote，使用适配器模式转换为统一格式，但不入库
    
    Args:
        db: 数据库会话
        keyword: 搜索关键词
        subject_type: 条目类型 (1=书籍/2=动画/3=音乐/4=游戏/6=三次元) (可选)
        user_id: 用户ID，用于查询收藏状态 (可选)
        limit: 返回结果数量限制
        offset: 结果偏移量
    
    Returns:
        包含搜索结果和来源信息的字典：
        {
            "data": List[Dict],  # 统一格式的条目数据 (SubjectWithUserStatus)
            "source": "local" | "remote",  # 数据来源
            "total": int  # 总数
        }
    """
    # Step 1: 本地搜索
    local_results = await search_subjects(db, keyword, subject_type, user_id, limit, offset)
    
    if local_results:
        # 本地有结果，返回本地数据
        return {
            "data": local_results,
            "source": "local",
            "total": len(local_results)
        }
    
    # Step 2: 本地无结果，尝试远程搜索
    try:
        logger.info(f"本地无结果，尝试从 Bangumi API 搜索: {keyword}")
        remote_response = await search_bangumi_subjects(keyword, subject_type, limit, offset)
        
        # 提取数据列表
        remote_data_list = remote_response.get("data", [])
        
        if not remote_data_list:
            return {
                "data": [],
                "source": "remote",
                "total": 0
            }
        
        # Step 3: 使用适配器模式转换数据格式
        adapted_results = []
        for bangumi_data in remote_data_list:
            try:
                adapted_data = adapt_bangumi_subject(bangumi_data)
                # 远程搜索的数据默认未收藏
                adapted_data["is_collected"] = False
                adapted_data["collection_info"] = None
                adapted_results.append(adapted_data)
            except Exception as e:
                logger.error(f"适配 Bangumi 数据失败: {e}, 数据: {bangumi_data}")
                continue
        
        return {
            "data": adapted_results,
            "source": "remote",
            "total": len(adapted_results)
        }
        
    except Exception as e:
        logger.error(f"远程搜索失败: {e}")
        # 返回空结果
        return {
            "data": [],
            "source": "remote",
            "total": 0,
            "error": str(e)
        }