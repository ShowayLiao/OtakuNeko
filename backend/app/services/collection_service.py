from datetime import datetime
from typing import Any, Dict, Optional, List

from sqlalchemy import desc, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from app.models import Collection, CollectionStatus, Subject, SubjectType
from app.repositories.collection_repo import CollectionRepo
from app.repositories.subject_repo import SubjectRepo
from app.schemas.collection import (
    CollectionCreate, CollectionUpdate, CollectionUpdateList,
    CollectionRead, CollectionList, CollectionReadList,
    CollectionSearchByID, CollectionSearchBase, CollectionSearchByName, CollectionCreateList,
    CollectionWithSubject, CollectionWithSubjectList, CollectionUpsertList
)
from app.schemas.subject import SubjectCreate, SubjectSearchByID
from app.schemas.adaptersV2 import (
    UnifiedCollectionSubject, UnifiedList,
    collection_with_subject_to_unified, collection_with_subject_list_to_unified_list
)
from fastapi_cache import FastAPICache
from app.core.logging import get_logger

logger = get_logger(__name__)


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
        
        # 清除用户的统计数据缓存
        await FastAPICache.clear(key=f'dashboard:stats:{collection_data.user_id}')
        logger.info(f"Cleared stats cache for user_id: {collection_data.user_id}")
        
        return collection
    except Exception as e:
        logger.error(f"Failed to create collection: {e}")
        raise

async def get_collection(
    db: AsyncSession,
    search_data: CollectionSearchByID
) -> Optional[UnifiedCollectionSubject]:
    """
    获取单个收藏记录
    
    Args:
        db: 数据库会话
        search_data: 搜索数据，使用 CollectionSearchByID schema
    
    Returns:
        统一视图模型对象，如果不存在则返回 None
    """
    try:
        # 调用仓库方法获取收藏和关联条目
        collection_result = await CollectionRepo.get_by_user_and_subject(db, search_data)
        
        if not collection_result:
            return None
        
        # 使用转换函数转换为统一视图模型
        return collection_with_subject_to_unified(collection_result)
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
            # 清除用户的统计数据缓存
            await FastAPICache.clear(key=f'dashboard:stats:{collection_data.user_id}')
            logger.info(f"Cleared stats cache for user_id: {collection_data.user_id}")
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
            # 清除用户的统计数据缓存
            await FastAPICache.clear(key=f'dashboard:stats:{search_data.user_id}')
            logger.info(f"Cleared stats cache for user_id: {search_data.user_id}")
        else:
            logger.warning(f"Collection not found for deletion: user_id: {search_data.user_id}, source: {search_data.source}, source_id: {search_data.source_id}")
        return deleted
    except Exception as e:
        logger.error(f"Failed to delete collection: {e}")
        raise

async def get_user_collections(
    db: AsyncSession,
    search_data: CollectionSearchBase
) -> UnifiedList:
    """
    获取用户的收藏列表，支持多种筛选和排序
    
    Args:
        db: 数据库会话
        search_data: 搜索数据，使用 CollectionSearchBase schema
    
    Returns:
        统一视图模型列表
    """
    try:
        # 调用仓库方法获取收藏列表
        collection_with_subject_list = await CollectionRepo.get_by_user(db, search_data.user_id, search_data.type, search_data.skip, search_data.limit)
        logger.info(f"Get collections found: {collection_with_subject_list.total} results for user_id: {search_data.user_id}, type: {search_data.type}")
        
        # 使用转换函数转换为统一视图模型列表
        return collection_with_subject_list_to_unified_list(collection_with_subject_list)
    except Exception as e:
        logger.error(f"Failed to get collections: {e}")
        raise

async def search_collections(
    db: AsyncSession,
    search_data: CollectionSearchByName
) -> UnifiedList:
    """
    根据关键词搜索收藏记录
    
    Args:
        db: 数据库会话
        search_data: 搜索数据，使用 CollectionSearchByName schema
    
    Returns:
        统一视图模型列表
    """
    try:
        # 调用仓库方法获取搜索结果
        collection_with_subject_list = await CollectionRepo.search_by_keyword(db, search_data)
        logger.info(f"Search collections found: {collection_with_subject_list.total} results for keyword: {search_data.keyword}")
        
        # 使用转换函数转换为统一视图模型列表
        return collection_with_subject_list_to_unified_list(collection_with_subject_list)
    except Exception as e:
        logger.error(f"Failed to search collections: {e}")
        raise


async def upsert_collection(
    db: AsyncSession,
    user_id: int,
    sid: Optional[int] = None,
    data: Optional[dict] = None
) -> UnifiedCollectionSubject:
    """
    更新或添加收藏
    
    统一的收藏操作业务逻辑：
    1. 检查subject是否存在，不存在则创建
    2. 使用batch_upsert方法更新或添加收藏
    
    Args:
        db: 数据库会话
        user_id: 用户ID
        sid: 条目ID，可选
        data: 收藏更新/添加数据，包含collection和subject字段
    
    Returns:
        统一视图模型对象
    
    Raises:
        ValueError: 必要参数缺失或格式错误
        SQLAlchemyError: 数据库操作异常
    """
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
        
        # 如果没有collection_data，使用默认值
        if not collection_data:
            collection_data = {
                'user_id': user_id,
                'source': subject.source,
                'source_id': subject.source_id,
                'type': CollectionStatus(2),  # 默认状态为"看过"
                'rate': None,
                'comment': None,
                'private': False,
                'tags': None
            }
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
    
    # 第二步：使用batch_upsert方法更新或添加收藏
    from app.schemas.collection import CollectionUpsert, CollectionUpsertList
    
    # 构建CollectionUpsert对象
    if isinstance(collection_data, dict):
        # 从字典构建
        upsert_data = CollectionUpsert(
            user_id=user_id,
            source=collection_search_data.source,
            source_id=collection_search_data.source_id,
            **collection_data
        )
    else:
        # 从对象构建
        upsert_dict = collection_data.model_dump(exclude_unset=True)
        upsert_data = CollectionUpsert(
            user_id=user_id,
            source=collection_search_data.source,
            source_id=collection_search_data.source_id,
            **upsert_dict
        )
    
    # 构建CollectionUpsertList对象
    upsert_list = CollectionUpsertList(
        collections=[upsert_data]
    )
    
    # 调用batch_upsert方法
    logger.info(f"Upsert collection: user_id={user_id}, source={collection_search_data.source}, source_id={collection_search_data.source_id}")
    await CollectionRepo.batch_upsert(db, upsert_list)
    
    # 重新获取完整的收藏和关联条目信息
    final_result = await CollectionRepo.get_by_user_and_subject(db, collection_search_data)
    if not final_result:
        raise ValueError("Failed to get updated collection")
    
    # 使用转换函数转换为统一视图模型
    return collection_with_subject_to_unified(final_result)


async def batch_upsert_collections(
    db: AsyncSession,
    collections: CollectionUpsertList,
    user_id: int
) -> int:
    """
    批量更新或添加收藏
    
    使用CollectionRepo的batch_upsert方法实现批量操作
    
    Args:
        db: 数据库会话
        collections: 收藏列表数据，使用 CollectionUpsertList schema
        user_id: 用户ID
    
    Returns:
        成功处理的收藏数量
    
    Raises:
        ValueError: 必要参数缺失或格式错误
        SQLAlchemyError: 数据库操作异常
    """
    try:
        if not collections.collections:
            return 0
        
        # 直接传递 CollectionUpsertList 对象给 CollectionRepo.batch_upsert 方法
        await CollectionRepo.batch_upsert(db, collections)
        
        logger.info(f"批量 Upsert 收藏记录成功，处理了 {len(collections.collections)} 条记录")
        
        # 清除用户的统计数据缓存
        await FastAPICache.clear(key=f'dashboard:stats:{user_id}')
        logger.info(f"Cleared stats cache for user_id: {user_id}")
        
        return len(collections.collections)
    except Exception as e:
        logger.error(f"批量 Upsert 收藏记录失败: {e}")
        raise


async def import_json_collections(
    db: AsyncSession,
    json_data: dict,
    user_id: int
) -> int:
    """
    导入JSON格式的收藏数据到数据库
    
    参考sync_user_collections函数的逻辑，将接收到的JSON数据插入到数据库中
    
    Args:
        db: 数据库会话
        json_data: JSON格式的收藏数据，格式类似于Bangumi API返回的收藏数据
        user_id: 用户ID
    
    Returns:
        成功导入的收藏数量
    
    Raises:
        ValueError: 必要参数缺失或格式错误
        SQLAlchemyError: 数据库操作异常
    """
    from app.services.subject_service import batch_upsert_subjects
    from app.schemas.adaptersV2 import bangumi_subject_to_subjectlist, bangumi_collection_to_collectionlist
    
    try:
        # 验证输入数据格式
        if not isinstance(json_data, dict):
            raise ValueError("Input data must be a dictionary")
        
        total_success = 0
        
        # 第一步：导入条目数据
        logger.info(f"开始导入条目数据...")
        subjects_list = bangumi_subject_to_subjectlist(json_data)
        subject_success_count = await batch_upsert_subjects(db, subjects_list, user_id)
        total_success += subject_success_count
        logger.info(f"条目数据导入完成: {subject_success_count}/{subjects_list.total} 条成功")
        
        # 第二步：导入收藏数据
        logger.info(f"开始导入收藏数据...")
        collections_list = bangumi_collection_to_collectionlist(json_data, user_id)
        collection_success_count = await batch_upsert_collections(db, collections_list, user_id)
        total_success += collection_success_count
        logger.info(f"收藏数据导入完成: {collection_success_count}/{collections_list.total} 条成功")
        
        # 清除用户的统计数据缓存
        await FastAPICache.clear(key=f'dashboard:stats:{user_id}')
        logger.info(f"Cleared stats cache for user_id: {user_id}")
        
        logger.info(f"成功导入 {total_success} 条数据")
        
        return total_success
        
    except Exception as e:
        import traceback
        logger.error(f"导入JSON收藏数据失败: {e}")
        logger.error(f"错误详情: {traceback.format_exc()}")
        # 回滚事务
        await db.rollback()
        raise


