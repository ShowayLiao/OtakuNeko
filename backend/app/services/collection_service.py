import logging
from datetime import datetime
from typing import Any, Dict, Optional, List

from sqlalchemy import desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models import Collection, CollectionStatus, Subject, SubjectType
from app.repositories.collection_repo import CollectionRepo
from app.schemas.collection import (
    CollectionCreate, CollectionUpdate, CollectionUpdateList,
    CollectionRead, CollectionList, CollectionReadList,
    CollectionSearchByID, CollectionSearchBase, CollectionSearchByName
)

logger = logging.getLogger(__name__)


async def create_collection(
    db: AsyncSession,
    collection_data: CollectionCreate
) -> Collection:
    """
    创建单个收藏记录
    
    Args:
        db: 数据库会话
        collection_data: 收藏数据，使用 CollectionCreate schema
    
    Returns:
        创建的收藏记录
    """
    try:
        # 直接使用 CollectionCreate schema 创建收藏记录
        collection = await CollectionRepo.create(db, collection_data)
        logger.info(f"Created collection: user_id: {collection_data.user_id}, source: {collection_data.source}, source_id: {collection_data.source_id}")
        return collection
    except Exception as e:
        logger.error(f"Failed to create collection: {e}")
        raise


async def get_collection(
    db: AsyncSession,
    search_data: CollectionSearchByID
) -> Optional[CollectionRead]:
    """
    获取单个收藏记录
    
    Args:
        db: 数据库会话
        search_data: 搜索数据，使用 CollectionSearchByID schema
    
    Returns:
        收藏记录的读取Schema，如果不存在则返回 None
    """
    try:
        from app.schemas.subject import SubjectRead as SubjectReadSchema
        
        # 调用仓库方法获取收藏和关联条目
        collection_result = await CollectionRepo.get_by_user_and_subject(db, search_data)
        
        if not collection_result:
            return None
        
        collection, subject = collection_result
        
        # 构造CollectionRead对象
        collection_dict = collection.model_dump()
        
        if subject:
            # 如果有关联条目，添加到收藏记录中
            collection_dict["subject"] = SubjectReadSchema.model_validate(subject)
        else:
            collection_dict["subject"] = None
        
        return CollectionRead(**collection_dict)
    except Exception as e:
        logger.error(f"Failed to get collection: {e}")
        raise


async def update_collection(
    db: AsyncSession,
    collection_data: CollectionUpdate
) -> Optional[Collection]:
    """
    更新用户的收藏信息
    
    Args:
        db: 数据库会话
        collection_data: 更新数据，使用 CollectionUpdate schema
    
    Returns:
        更新后的 Collection 对象，如果不存在则返回 None
    """
    try:
        # 调用仓库方法更新收藏
        collection = await CollectionRepo.update(db, collection_data)
        
        if collection:
            logger.info(f"Updated collection: user_id: {collection_data.user_id}, source: {collection_data.source}, source_id: {collection_data.source_id}")
        else:
            logger.warning(f"Collection not found for update: user_id: {collection_data.user_id}, source: {collection_data.source}, source_id: {collection_data.source_id}")
        
        return collection
    except Exception as e:
        logger.error(f"Failed to update collection: {e}")
        raise


async def delete_collection(
    db: AsyncSession,
    search_data: CollectionSearchByID
) -> bool:
    """
    删除收藏记录
    
    Args:
        db: 数据库会话
        search_data: 搜索数据，使用 CollectionSearchByID schema
    
    Returns:
        删除成功返回 True，收藏记录不存在返回 False
    """
    try:
        deleted = await CollectionRepo.delete(db, search_data)
        if deleted:
            logger.info(f"Deleted collection: user_id: {search_data.user_id}, source: {search_data.source}, source_id: {search_data.source_id}")
        else:
            logger.warning(f"Collection not found for deletion: user_id: {search_data.user_id}, source: {search_data.source}, source_id: {search_data.source_id}")
        return deleted
    except Exception as e:
        logger.error(f"Failed to delete collection: {e}")
        raise


async def get_user_collections(
    db: AsyncSession,
    search_data: CollectionSearchBase
) -> CollectionReadList:
    """
    获取用户的收藏列表，支持多种筛选和排序
    
    Args:
        db: 数据库会话
        search_data: 搜索数据，使用 CollectionSearchBase schema
    
    Returns:
        包含总数和分页后结果的CollectionReadList Schema
    """
    from app.schemas.subject import SubjectRead as SubjectReadSchema
    
    # 调用仓库方法获取收藏列表
    collection_pairs = await CollectionRepo.get_by_user(db, search_data.user_id, None, search_data.skip, search_data.limit)
    
    # 构建CollectionRead对象列表
    collection_read_items = []
    for collection, subject in collection_pairs:
        collection_dict = collection.model_dump()
        
        if subject:
            collection_dict["subject"] = SubjectReadSchema.model_validate(subject)
        else:
            collection_dict["subject"] = None
        
        collection_read_items.append(CollectionRead(**collection_dict))
    
    # 计算总数
    from sqlalchemy import func
    from sqlmodel import select, and_, or_
    
    # 构建总数查询
    total_query = select(func.count(Collection.user_id)).where(Collection.user_id == search_data.user_id)
    
    total_result = await db.execute(total_query)
    total_count = total_result.scalar_one()
    
    # 返回CollectionReadList
    return CollectionReadList(
        total=total_count,
        items=collection_read_items
    )


async def search_collections(
    db: AsyncSession,
    search_data: CollectionSearchByName
) -> CollectionReadList:
    """
    根据关键词搜索收藏记录
    
    Args:
        db: 数据库会话
        search_data: 搜索数据，使用 CollectionSearchByName schema
    
    Returns:
        包含总数和搜索结果的CollectionReadList Schema
    """
    try:
        from app.schemas.subject import SubjectRead as SubjectReadSchema
        from sqlalchemy import func
        from sqlmodel import select, or_, and_
        
        # 调用仓库方法获取搜索结果
        collection_pairs = await CollectionRepo.search_by_keyword(db, search_data)
        logger.info(f"Search collections found: {len(collection_pairs)} results for keyword: {search_data.keyword}")
        
        # 简化转换为CollectionRead对象列表
        collection_read_items = [
            CollectionRead(
                **collection.model_dump(),
                subject=SubjectReadSchema.model_validate(subject) if subject else None
            )
            for collection, subject in collection_pairs
        ]
        
        # 构建并执行总数查询
        total_query = select(func.count(Collection.user_id)).where(Collection.user_id == search_data.user_id)
        
        # 添加关键词搜索条件
        if search_data.keyword:
            total_query = total_query.outerjoin(Subject, 
                and_(Collection.source == Subject.source, Collection.source_id == Subject.source_id))
            total_query = total_query.where(
                or_(
                    Collection.name.ilike(f"%{search_data.keyword}%"),
                    Collection.name_cn.ilike(f"%{search_data.keyword}%"),
                    Collection.comment.ilike(f"%{search_data.keyword}%"),
                    Subject.name.ilike(f"%{search_data.keyword}%"),
                    Subject.name_cn.ilike(f"%{search_data.keyword}%")
                )
            )
        
        total_result = await db.execute(total_query)
        total_count = total_result.scalar_one()
        
        # 返回CollectionReadList
        return CollectionReadList(
            total=total_count,
            items=collection_read_items
        )
    except Exception as e:
        logger.error(f"Failed to search collections: {e}")
        raise


async def upsert_collection(
    db: AsyncSession,
    user_id: int,
    sid: Optional[int] = None,
    data: Optional[dict] = None
) -> Collection:
    """
    更新或添加收藏
    
    统一的收藏操作业务逻辑：
    1. 检查subject是否存在，不存在则创建
    2. 检查collection是否存在，不存在则创建，存在则更新
    
    Args:
        db: 数据库会话
        user_id: 用户ID
        sid: 条目ID，可选
        data: 收藏更新/添加数据，包含collection和subject字段
    
    Returns:
        更新或创建后的 Collection 对象
    
    Raises:
        ValueError: 必要参数缺失或格式错误
        SQLAlchemyError: 数据库操作异常
    """
    from app.repositories.subject_repo import SubjectRepo
    from app.schemas.subject import SubjectCreate, SubjectSearchByID
    from app.schemas.collection import CollectionUpdate, CollectionCreate
    
    # 从data中提取collection和subject信息
    collection_data = data.collection if hasattr(data, 'collection') else data.get('collection') if isinstance(data, dict) else None
    subject_data = data.subject if hasattr(data, 'subject') else data.get('subject') if isinstance(data, dict) else None
    
    # 第一步：检查subject是否存在
    if sid:
        # 使用sid查询subject
        subject = await db.get(Subject, sid)
        if not subject:
            raise ValueError(f"Subject with ID {sid} not found")
        
        # 构建collection搜索数据
        collection_search_data = CollectionSearchByID(
            user_id=user_id,
            source=subject.source,
            source_id=subject.source_id
        )
    elif collection_data:
        # 使用collection_data中的source和source_id查询subject
        subject_search_data = SubjectSearchByID(
            source=collection_data.source,
            source_id=collection_data.source_id
        )
        subject_result = await SubjectRepo.get_by_source(db, subject_search_data)
        subject = subject_result[0] if subject_result else None
        
        # 构建collection搜索数据
        collection_search_data = CollectionSearchByID(
            user_id=user_id,
            source=collection_data.source,
            source_id=collection_data.source_id
        )
    else:
        raise ValueError("Either sid or collection_data is required")
    
    # 第二步：检查collection是否存在
    collection_result = await CollectionRepo.get_by_user_and_subject(db, collection_search_data)
    collection = collection_result[0] if collection_result else None
    
    if not collection:
        # collection不存在，创建新的collection
        logger.info(f"Collection not found, creating new one: user_id={user_id}, source={collection_search_data.source}, source_id={collection_search_data.source_id}")
        
        # 如果没有collection_data，使用默认值创建
        if not collection_data:
            collection_data = CollectionUpdate(
                user_id=user_id,
                source=subject.source,
                source_id=subject.source_id,
                type=CollectionStatus(2),  # 默认状态为"看过"
                rate=None,
                comment=None,
                private=False,
                tags=None
            )
        
        # 转换为CollectionCreate schema
        collection_dict = collection_data.model_dump(exclude_unset=True)
        # 确保设置updated_at字段
        from datetime import datetime
        collection_dict['updated_at'] = collection_dict.get('updated_at') or datetime.now()
        
        collection_create = CollectionCreate(
            user_id=user_id,
            **collection_dict
        )
        
        collection = await CollectionRepo.create(db, collection_create)
        logger.info(f"Created new collection: user_id={user_id}, source={collection.source}, source_id={collection.source_id}")
    else:
        # collection存在，更新现有collection
        logger.info(f"Collection already exists, updating: user_id={user_id}, source={collection_search_data.source}, source_id={collection_search_data.source_id}")
        
        if not collection_data:
            raise ValueError("collection_data is required for updating collection")
        
        # 确保collection_data包含必要的字段
        collection_data.user_id = user_id
        collection_data.source = collection_search_data.source
        collection_data.source_id = collection_search_data.source_id
        
        # 更新collection
        collection = await CollectionRepo.update(db, collection_data)
        logger.info(f"Updated collection: user_id={user_id}, source={collection_search_data.source}, source_id={collection_search_data.source_id}")
    
    return collection


async def batch_upsert_collections(
    db: AsyncSession,
    collections: CollectionList,
    user_id: int
) -> int:
    """
    批量更新或添加收藏
    
    批量处理收藏操作业务逻辑：
    1. 遍历CollectionList中的每个CollectionBase对象
    2. 为每个对象先检查是否存在，存在则更新，否则创建
    
    Args:
        db: 数据库会话
        collections: 收藏列表数据，使用 CollectionList schema
        user_id: 用户ID
    
    Returns:
        成功处理的收藏数量
    
    Raises:
        ValueError: 必要参数缺失或格式错误
        SQLAlchemyError: 数据库操作异常
    """
    from app.schemas.collection import CollectionCreate, CollectionUpdate, CollectionSearchByID
    from sqlalchemy import select
    from app.models.collection import Collection
    
    success_count = 0
    
    for collection_base in collections.items:
        try:
            # 创建搜索数据，用于检查记录是否存在
            search_data = CollectionSearchByID(
                user_id=user_id,
                source=collection_base.source,
                source_id=collection_base.source_id
            )
            
            # 检查记录是否存在，使用直接查询而不是Repo方法，避免ORM对象延迟加载问题
            stmt = select(Collection).where(
                Collection.user_id == user_id,
                Collection.source == collection_base.source,
                Collection.source_id == collection_base.source_id
            )
            result = await db.execute(stmt)
            existing_collection = result.scalars().first()
            
            if existing_collection:
                # 记录存在，执行更新操作
                # 直接更新ORM对象，避免使用Repo方法
                existing_collection.type = collection_base.type
                existing_collection.updated_at = collection_base.updated_at
                existing_collection.rate = collection_base.rate
                existing_collection.comment = collection_base.comment
                existing_collection.private = collection_base.private
                existing_collection.tags = collection_base.tags
                existing_collection.vol_status = collection_base.vol_status
                existing_collection.ep_status = collection_base.ep_status
                existing_collection.subject_type = collection_base.subject_type
                
                await db.commit()
                await db.refresh(existing_collection)
                success_count += 1
            else:
                # 记录不存在，执行创建操作
                # 直接创建ORM对象，避免使用Repo方法
                new_collection = Collection(
                    user_id=user_id,
                    type=collection_base.type,
                    source=collection_base.source,
                    source_id=collection_base.source_id,
                    updated_at=collection_base.updated_at,
                    rate=collection_base.rate,
                    comment=collection_base.comment,
                    private=collection_base.private,
                    tags=collection_base.tags,
                    vol_status=collection_base.vol_status,
                    ep_status=collection_base.ep_status,
                    subject_type=collection_base.subject_type
                )
                db.add(new_collection)
                await db.commit()
                await db.refresh(new_collection)
                success_count += 1
            
            logger.info(f"Successfully upserted collection: user_id={user_id}, source={collection_base.source}, source_id={collection_base.source_id}")
        except Exception as e:
            import traceback
            logger.error(f"Failed to upsert collection: user_id={user_id}, source={collection_base.source}, source_id={collection_base.source_id}, error={e}")
            logger.error(f"Error details: {traceback.format_exc()}")
            await db.rollback()
            continue
    
    return success_count


