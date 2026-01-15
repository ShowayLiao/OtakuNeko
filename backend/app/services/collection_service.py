import logging
from datetime import datetime
from typing import Any, Dict, Optional

from sqlalchemy import desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models import Collection, CollectionStatus, Subject, SubjectType
from app.schemas.collection import CollectionUpdate

logger = logging.getLogger(__name__)


async def get_my_collections(
    db: AsyncSession,
    user_id: int,
    status: Optional[CollectionStatus] = None,
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
        status: 收藏状态 (可选，CollectionStatus枚举)
        subject_type: 条目类型 (可选)
        keyword: 搜索关键词 (可选)
        sort_by: 排序字段 ("updated_at" 或 "rate")
        limit: 分页大小
        offset: 分页偏移
    
    Returns:
        包含总数和分页后结果的字典
    """
    query = select(Collection, Subject).where(
        Collection.user_id == user_id,
        Collection.subject_id == Subject.id
    )
    
    if status:
        query = query.where(Collection.type == status)
    
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


async def upsert_collection(
    db: AsyncSession,
    user_id: int,
    sid: Optional[int],
    data: Any
) -> Collection:
    """
    更新或添加收藏
    
    统一的收藏操作业务逻辑：
    - 当提供sid时：更新现有收藏
    - 当不提供sid时：创建新收藏
    - 如果提供sid但收藏不存在，则创建新收藏
    
    Args:
        db: 数据库会话
        user_id: 当前用户ID
        sid: 条目ID，可选，留空则创建新收藏
        data: 收藏更新/添加数据
    
    Returns:
        更新或创建后的 Collection 对象
    """
    from app.schemas.collection import CollectionUpsertRequest
    from app.models.enums import CollectionStatus, SubjectType
    from app.repositories.subject_repo import SubjectRepo
    from app.repositories.collection_repo import CollectionRepo
    import time
    
    def validate_date_format(date_str: str) -> bool:
        """验证日期格式是否为 YYYY-MM-DD"""
        if not date_str:
            return True
        try:
            datetime.strptime(date_str, "%Y-%m-%d")
            return True
        except ValueError:
            return False
    
    def check_date_conflict(release_date: str, publish_date: str) -> tuple[bool, str]:
        """
        检查上映时间和发售时间是否存在冲突
        
        Args:
            release_date: 上映日期 (YYYY-MM-DD)
            publish_date: 发售日期 (YYYY-MM-DD)
            
        Returns:
            (是否有冲突, 错误信息)
        """
        if not release_date or not publish_date:
            return False, ""
        
        try:
            release_dt = datetime.strptime(release_date, "%Y-%m-%d")
            publish_dt = datetime.strptime(publish_date, "%Y-%m-%d")
            
            if release_dt > publish_dt:
                return True, "上映时间不能晚于发售时间"
            
            return False, ""
        except ValueError:
            return False, ""
    
    # 验证请求数据
    if sid is None:
        # 创建新收藏时，必须提供subject数据
        if not data.subject:
            raise ValueError("Subject data is required for creating new collection")
        
        subject_data = data.subject
        
        # 验证日期格式
        if not validate_date_format(subject_data.release_date):
            raise ValueError("上映日期格式错误，请使用 YYYY-MM-DD 格式")
        
        if not validate_date_format(subject_data.publish_date):
            raise ValueError("发售日期格式错误，请使用 YYYY-MM-DD 格式")
        
        # 检查时间冲突
        has_conflict, conflict_msg = check_date_conflict(subject_data.release_date, subject_data.publish_date)
        if has_conflict:
            raise ValueError(conflict_msg)
        
        # 处理Subject数据
        # 生成唯一的source_id
        source_id = f"manual_{int(time.time() * 1000)}"
        
        # 构造Subject数据
        subject_dict = {
            "name": subject_data.name,
            "name_cn": subject_data.name,
            "type": subject_data.type,
            "cover_url": subject_data.cover_url,
            "date": subject_data.publish_date if subject_data.publish_date else subject_data.release_date,
            "tags": subject_data.tags if subject_data.tags else [],
            "images": {}
        }
        
        # 保存Subject，source_id使用生成的manual_xxx
        subject = await SubjectRepo.save(db, subject_dict, source="manual", source_id=source_id)
        logger.info(f"Created new manual subject: {subject.id}, source_id: {source_id}")
        
        # 构造Collection数据
        collection_dict = {
            "type": subject_data.status,
            "rate": subject_data.rate if subject_data.rate > 0 else None,
            "comment": subject_data.comment,
            "private": False,
            "tags": [],
            "updated_at": datetime.now().isoformat() + "Z"
        }
        
        # 保存Collection
        collection = await CollectionRepo.save(db, user_id, subject.id, collection_dict)
        logger.info(f"Created new collection for manual subject: {collection.id}, subject_id: {subject.id}")
        
        return collection
    else:
        # 提供了sid，执行更新或创建逻辑
        # 检查收藏是否存在
        collection = await CollectionRepo.find_by_user_and_subject(db, user_id, sid)
        
        if collection:
            # 更新现有收藏
            if not data.collection:
                raise ValueError("Collection data is required for updating existing collection")
            
            # 构造Collection数据
            collection_dict = {
                "type": data.collection.status,
                "rate": data.collection.rate if data.collection.rate > 0 else None,
                "comment": data.collection.comment,
                "private": data.collection.private,
                "tags": data.collection.tags if data.collection.tags else [],
                "updated_at": datetime.now().isoformat() + "Z"
            }
            
            # 更新Collection
            collection = await CollectionRepo.save(db, user_id, sid, collection_dict)
            logger.info(f"Updated collection: {collection.id}, subject_id: {sid}")
            
            return collection
        else:
            # 创建新收藏
            if not data.subject:
                raise ValueError("Subject data is required for creating new collection")
            
            subject_data = data.subject
            
            # 验证日期格式
            if not validate_date_format(subject_data.release_date):
                raise ValueError("上映日期格式错误，请使用 YYYY-MM-DD 格式")
            
            if not validate_date_format(subject_data.publish_date):
                raise ValueError("发售日期格式错误，请使用 YYYY-MM-DD 格式")
            
            # 检查时间冲突
            has_conflict, conflict_msg = check_date_conflict(subject_data.release_date, subject_data.publish_date)
            if has_conflict:
                raise ValueError(conflict_msg)
            
            # 检查条目是否已存在
            from app.models import Subject
            # 正确的检查：使用source_id和source来匹配，而非id
            result = await db.execute(
                select(Subject).where(
                    Subject.source_id == str(sid),
                    Subject.source == "manual"
                )
            )
            subject = result.scalar_one_or_none()
            
            if not subject:
                # 构造Subject数据
                subject_dict = {
                    "name": subject_data.name,
                    "name_cn": subject_data.name,
                    "type": subject_data.type,
                    "cover_url": subject_data.cover_url,
                    "date": subject_data.publish_date if subject_data.publish_date else subject_data.release_date,
                    "tags": subject_data.tags if subject_data.tags else [],
                    "images": {}
                }
                
                # 保存Subject，source_id使用外部源的真实ID（sid）
                subject = await SubjectRepo.save(db, subject_dict, source="manual", source_id=str(sid))
                logger.info(f"Created new subject with external ID: {subject.id}, source_id: {str(sid)}")
            
            # 构造Collection数据
            collection_dict = {
                "type": subject_data.status,
                "rate": subject_data.rate if subject_data.rate > 0 else None,
                "comment": subject_data.comment,
                "private": False,
                "tags": [],
                "updated_at": datetime.now().isoformat() + "Z"
            }
            
            # 保存Collection
            collection = await CollectionRepo.save(db, user_id, subject.id, collection_dict)
            logger.info(f"Created new collection for subject: {collection.id}, subject_id: {subject.id}")
            
            return collection