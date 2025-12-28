from typing import Optional, List, Dict, Any
from sqlmodel import select, join, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy import desc, asc
from datetime import datetime
import logging
from app.models import Subject, Collection, CollectionStatus, SubjectType
from app.schemas.collection import CollectionUpdate

logger = logging.getLogger(__name__)


async def get_my_collections(
    db: AsyncSession,
    user_id: int,
    status: Optional[str] = None,
    subject_type: Optional[int] = None,
    keyword: Optional[str] = None,
    sort_by: str = "updated_at",
    limit: int = 20,
    offset: int = 0
) -> Dict[str, Any]:
    """
    获取用户的收藏列表，支持多种筛选和排序
    
    Args:
        db: 数据库会话
        user_id: 用户ID
        status: 收藏状态 (可选)
        subject_type: 条目类型 (可选)
        keyword: 搜索关键词 (可选)
        sort_by: 排序字段 ("updated_at" 或 "rate")
        limit: 分页大小
        offset: 分页偏移
    
    Returns:
        包含总数和分页后结果的字典
    """
    # 状态映射: str -> CollectionStatus
    status_mapping = {
        'watching': 3,    # 在看
        'completed': 2,   # 看过
        'plan': 1,        # 想看
        'on_hold': 4,     # 搁置
        'dropped': 5      # 抛弃
    }
    
    # 构建查询
    # 使用联合查询(select(Collection, Subject))一次性获取所有数据，避免N+1查询问题
    # 注意：由于Collection和Subject模型之间没有定义SQLAlchemy关系，所以不能使用joinedload
    query = select(Collection, Subject).where(
        Collection.user_id == user_id,
        Collection.subject_id == Subject.id
    )
    
    # 添加过滤条件
    if status:
        try:
            status_code = status_mapping[status]
            status_enum = CollectionStatus(status_code)
            query = query.where(Collection.type == status_enum)
        except (KeyError, ValueError):
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
    
    # 添加排序，使用subject_id作为唯一的二级排序键确保稳定性
    tie_breaker = Collection.subject_id.desc()
    
    if sort_by == "rate":
        # 按用户打分倒序，没打分的排后面
        query = query.order_by(desc(Collection.rate).nullslast(), tie_breaker)
    elif sort_by == "score":
        # 按大众评分倒序，没评分的排后面
        query = query.order_by(desc(Subject.score).nullslast(), tie_breaker)
    elif sort_by == "rank":
        # 按 Bangumi 排名升序，Rank 0 转换为 NULL 放到最后
        query = query.order_by(func.nullif(Subject.rank, 0).asc().nullslast(), tie_breaker)
    elif sort_by == "date":
        # 按条目发行日期倒序，没日期的排后面
        query = query.order_by(desc(Subject.date).nullslast(), tie_breaker)
    else:  # 默认按 updated_at 排序
        query = query.order_by(desc(Collection.updated_at), tie_breaker)
    
    # 计算总数
    total = await db.execute(select(func.count()).select_from(query.subquery()))
    total_count = total.scalar_one()
    
    # 分页
    query = query.offset(offset).limit(limit)
    
    # 执行查询
    result = await db.execute(query)
    collections_with_subjects = result.all()
    
    # 构建返回结果
    return {
        "total": total_count,
        "items": [{
            "collection": collection,
            "subject": subject
        } for collection, subject in collections_with_subjects]
    }


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
    # 注意：更新操作只需要Collection数据，不需要Subject数据
    query = select(Collection).where(
        Collection.user_id == user_id,
        Collection.subject_id == subject_id
    )
    result = await db.execute(query)
    collection = result.scalar_one_or_none()
    
    if not collection:
        return None
    
    # 排除未设置的字段
    obj_data = update_data.model_dump(exclude_unset=True)
    
    # 字段映射：API Schema 中的 'status' 对应数据库模型中的 'type'
    field_mapping = {
        'status': 'type'
    }
    
    # 更新字段
    for field, value in obj_data.items():
        # 应用字段映射
        mapped_field = field_mapping.get(field, field)
        
        # 检查模型是否有该字段
        if hasattr(collection, mapped_field):
            setattr(collection, mapped_field, value)
        else:
            logger.warning(f"Field {mapped_field} not found in Collection model")
    
    # 更新时间戳
    collection.updated_at = datetime.now()
    
    # 保存更新
    db.add(collection)
    await db.commit()
    await db.refresh(collection)
    
    return collection