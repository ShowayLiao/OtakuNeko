from typing import Optional, List, Dict, Any
from sqlmodel import select, join, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import desc, asc
from datetime import datetime
from app.models import Subject, Collection, CollectionStatus, SubjectType
from app.schemas.collection import CollectionUpdate


async def get_my_collections(
    db: AsyncSession,
    user_id: int,
    status: Optional[int] = None,
    subject_type: Optional[int] = None,
    keyword: Optional[str] = None,
    sort_by: str = "updated_at"
) -> List[Dict[str, Any]]:
    """
    获取用户的收藏列表，支持多种筛选和排序
    
    Args:
        db: 数据库会话
        user_id: 用户ID
        status: 收藏状态 (可选)
        subject_type: 条目类型 (可选)
        keyword: 搜索关键词 (可选)
        sort_by: 排序字段 ("updated_at" 或 "rate")
    
    Returns:
        包含 Subject 信息的聚合对象列表
    """
    # 构建查询
    # 直接选择 Collection 和 Subject 两个实体
    query = select(Collection, Subject).where(
        Collection.user_id == user_id,
        Collection.subject_id == Subject.id
    )
    
    # 添加过滤条件
    if status:
        try:
            status_enum = CollectionStatus(status)
            query = query.where(Collection.status == status_enum)
        except ValueError:
            pass  # 无效状态，忽略过滤
    
    if subject_type:
        try:
            # 过滤条目类型
            query = query.where(Subject.type == SubjectType(subject_type))
        except ValueError:
            pass  # 无效类型，忽略过滤
    
    if keyword:
        # 搜索 Subject 的名字
        query = query.where(
            Subject.name.contains(keyword) | Subject.name_cn.contains(keyword)
        )
    
    # 添加排序
    if sort_by == "rate":
        query = query.order_by(desc(Collection.rate), desc(Collection.updated_at))
    else:  # 默认按 updated_at 排序
        query = query.order_by(desc(Collection.updated_at))
    
    # 执行查询
    result = await db.execute(query)
    collections_with_subjects = result.all()
    
    # 构建返回结果
    return [{
        "collection": collection,
        "subject": subject
    } for collection, subject in collections_with_subjects]


async def update_collection(
    db: AsyncSession,
    user_id: int,
    subject_id: int,
    update_data: CollectionUpdate
) -> Optional[Collection]:
    """
    更新用户的收藏信息
    
    Args:
        db: 数据库会话
        user_id: 用户ID
        subject_id: 条目ID
        update_data: 更新数据
    
    Returns:
        更新后的 Collection 对象，如果不存在则返回 None
    """
    # 查询收藏记录
    query = select(Collection).where(
        Collection.user_id == user_id,
        Collection.subject_id == subject_id
    )
    result = await db.execute(query)
    collection = result.scalar_one_or_none()
    
    if not collection:
        return None
    
    # 更新字段
    update_dict = update_data.dict(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(collection, field, value)
    
    # 更新时间戳
    collection.updated_at = datetime.now()
    
    # 保存更新
    db.add(collection)
    await db.commit()
    await db.refresh(collection)
    
    return collection