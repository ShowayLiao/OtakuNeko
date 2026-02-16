from typing import Any, Dict, List, Optional
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, or_

from fastapi_cache import FastAPICache
from app.core.logging import get_logger

from app.models import Collection, Subject, SubjectType, User
from app.schemas.collection import CollectionList, CollectionRead
from app.schemas.subject import (
    SubjectCreate, SubjectUpdate, SubjectUpdateList, SubjectUpsertList,
    SubjectSearchByID, SubjectSearchBase, SubjectSearchCloud, SubjectSearchByName,
    SubjectWithCollection, SubjectWithCollectionList
)
from app.services.bangumi_client import search_subjects as search_bangumi_subjects
from app.repositories.subject_repo import SubjectRepo
from app.schemas.adaptersV2 import (
    UnifiedList,
    subject_with_collection_list_to_unified_list,
    UnifiedCollectionSubject
)

import httpx

logger = get_logger(__name__)


async def create_subject(
    db: AsyncSession,
    subject_data: SubjectCreate,
    user_id: Optional[int] = None
) -> Subject:
    """
    创建新条目，使用SubjectCreate格式
    
    Args:
        db: 数据库会话
        subject_data: 条目数据，使用SubjectCreate schema
        user_id: 用户ID，可选
    
    Returns:
        创建的Subject对象
    """
    try:
        # 直接创建subject，不需要转换数据类型
        created_subject = await SubjectRepo.create(db, subject_data)
        logger.info(f"创建条目成功: {created_subject.name} (ID: {created_subject.id})")
        
        # 清除用户的统计数据缓存
        if user_id:
            await FastAPICache.clear(key=f'dashboard:stats:{user_id}')
            logger.info(f"Cleared stats cache for user_id: {user_id}")
        
        return created_subject
    except Exception as e:
        logger.error(f"创建条目失败: {e}")
        raise


async def get_subject_by_source(
    db: AsyncSession,
    search_data: SubjectSearchByID
) -> Optional[UnifiedCollectionSubject]:
    """
    根据数据源和ID获取条目
    
    Args:
        db: 数据库会话
        search_data: 搜索条件，使用SubjectSearchByID schema
    
    Returns:
        统一视图模型对象
    """
    try:
        from app.schemas.adaptersV2 import subject_with_collection_to_unified
        from app.schemas.adaptersV2 import UnifiedCollectionSubject
        from app.schemas.subject import SubjectWithCollection
        
        subject, collection = await SubjectRepo.get_by_source(db, search_data)
        if not subject:
            return None
        
        # 构建SubjectWithCollection对象
        subject_with_collection = SubjectWithCollection(
            subject=subject,
            collection=collection
        )
        
        # 转换为UnifiedCollectionSubject格式
        return subject_with_collection_to_unified(subject_with_collection)
    except Exception as e:
        logger.error(f"获取条目失败: {e}")
        raise


async def update_subject(
    db: AsyncSession,
    subject_data: SubjectUpdate,
    user_id: Optional[int] = None
) -> Optional[Subject]:
    """
    更新条目，使用SubjectUpdate schema
    
    Args:
        db: 数据库会话
        subject_data: 更新的条目数据，使用SubjectUpdate schema
        user_id: 用户ID，可选
    
    Returns:
        更新后的Subject对象或None
    """
    try:
        # 调用仓库方法更新subject，直接使用SubjectUpdate schema
        updated_subject = await SubjectRepo.update(db, subject_data)
        
        if updated_subject:
            logger.info(f"更新条目成功: {updated_subject.name} (ID: {updated_subject.id})")
            
            # 清除用户的统计数据缓存
            if user_id:
                await FastAPICache.clear(key=f'dashboard:stats:{user_id}')
                logger.info(f"Cleared stats cache for user_id: {user_id}")
        return updated_subject
    except Exception as e:
        logger.error(f"更新条目失败: {e}")
        raise


async def batch_update_subjects(
    db: AsyncSession,
    subject_list: SubjectUpdateList,
    user_id: Optional[int] = None
) -> int:
    """
    批量更新条目，使用SubjectUpdateList schema
    
    Args:
        db: 数据库会话
        subject_list: 更新的条目列表数据，使用SubjectUpdateList schema
        user_id: 用户ID，可选
    
    Returns:
        成功更新的条目数量
    """
    success_count = 0
    
    for subject_data in subject_list.items:
        try:
            # 调用单个更新方法
            result = await update_subject(db, subject_data, user_id)
            if result:
                success_count += 1
        except Exception as e:
            logger.error(f"批量更新条目失败: {e}, 数据: {subject_data.model_dump()}")
            # 继续处理下一个条目，不中断整个批量操作
            continue
    
    logger.info(f"批量更新完成，成功更新 {success_count}/{subject_list.total} 个条目")
    
    # 清除用户的统计数据缓存
    if user_id and success_count > 0:
        await FastAPICache.clear(key=f'dashboard:stats:{user_id}')
        logger.info(f"Cleared stats cache for user_id: {user_id}")
    
    return success_count


async def batch_upsert_subjects(
    db: AsyncSession,
    subject_list: SubjectUpsertList,
    user_id: Optional[int] = None
) -> int:
    """
    批量 Upsert 条目，使用SubjectUpsertList schema
    
    Args:
        db: 数据库会话
        subject_list: 条目列表数据，使用SubjectUpsertList schema
        user_id: 用户ID，可选
    
    Returns:
        处理的条目数量
    
    Raises:
        SQLAlchemyError: 数据库操作异常
    """
    try:
        # 调用 SubjectRepo 的 batch_upsert 方法
        processed_count = await SubjectRepo.batch_upsert(db, subject_list)
        logger.info(f"批量 Upsert 完成，处理了 {processed_count} 个条目")
        
        # 清除用户的统计数据缓存
        if user_id and processed_count > 0:
            await FastAPICache.clear(key=f'dashboard:stats:{user_id}')
            logger.info(f"Cleared stats cache for user_id: {user_id}")
        
        return processed_count
    except Exception as e:
        logger.error(f"批量 Upsert 条目失败: {e}")
        raise


async def delete_subject(
    db: AsyncSession,
    search_data: SubjectSearchByID,
    user_id: Optional[int] = None
) -> bool:
    """
    删除条目，使用SubjectSearchByID schema
    
    Args:
        db: 数据库会话
        search_data: 搜索条件，使用SubjectSearchByID schema
        user_id: 用户ID，可选
    
    Returns:
        删除成功返回True，条目不存在返回False
    """
    try:
        # 直接使用 SubjectSearchByID schema 删除条目
        deleted = await SubjectRepo.delete(db, search_data)
        if deleted:
            logger.info(f"删除条目成功: source={search_data.source}, source_id={search_data.source_id}")
            
            # 清除用户的统计数据缓存
            if user_id:
                await FastAPICache.clear(key=f'dashboard:stats:{user_id}')
                logger.info(f"Cleared stats cache for user_id: {user_id}")
        return deleted
    except Exception as e:
        logger.error(f"删除条目失败: {e}")
        raise

async def get_all_subjects(
    db: AsyncSession,
    search_data: SubjectSearchBase
) -> UnifiedList:
    """
    获取所有条目，使用SubjectSearchBase schema
    
    Args:
        db: 数据库会话
        search_data: 搜索条件，使用SubjectSearchBase schema
    
    Returns:
        统一视图模型列表
    """
    try:
        # SubjectRepo.get_all 现在返回 SubjectWithCollectionList 对象
        subject_with_collection_list = await SubjectRepo.get_all(db, search_data)
        
        # 转换为UnifiedList格式
        return subject_with_collection_list_to_unified_list(subject_with_collection_list)
    except Exception as e:
        logger.error(f"获取条目列表失败: {e}")
        raise




async def search_subject_by_name(
    db: AsyncSession,
    search_data: SubjectSearchByName
) -> UnifiedList:
    """
    基于名称的宽泛搜索，使用SubjectSearchByName schema
    
    Args:
        db: 数据库会话
        search_data: 搜索条件，使用SubjectSearchByName schema
    
    Returns:
        统一视图模型列表
    """
    try:
        # SubjectRepo.search_by_name 现在返回 SubjectWithCollectionList 对象
        subject_with_collection_list = await SubjectRepo.search_by_name(db, search_data)
        
        # 转换为UnifiedList格式
        return subject_with_collection_list_to_unified_list(subject_with_collection_list)
    except Exception as e:
        logger.error(f"搜索条目失败: {e}")
        raise

async def search_subject_cloud(
    db: AsyncSession,
    search_data: SubjectSearchCloud
) -> UnifiedList:
    """
    调用 Bangumi API 进行搜索，使用SubjectSearchCloud schema
    
    Args:
        db: 数据库会话
        search_data: 搜索条件，使用SubjectSearchCloud schema
    
    Returns:
        统一视图模型列表
    """
    try:
        from app.schemas.adaptersV2 import bangumi_search_to_unified_list
        
        logger.info(f"从 Bangumi API 搜索: {search_data.keyword}")
        remote_response = await search_bangumi_subjects(search_data.keyword, search_data.type, search_data.limit, search_data.offset)
        
        # 直接使用 bangumi_search_to_unified_list 函数转换为 UnifiedList 格式
        return bangumi_search_to_unified_list(remote_response)
        
    except Exception as e:
        logger.error(f"远程搜索失败: {e}")
        # 返回空结果列表
        return UnifiedList(
            total=0,
            items=[]
        )


async def search_mixed(
    db: AsyncSession,
    search_data: SubjectSearchBase
) -> UnifiedList:
    """
    混合搜索服务：并行搜索 + 结果合并
    
    实现策略：
    1. 同时执行本地搜索和云端搜索
    2. 合并两个搜索结果
    3. 根据 source 和 source_id 去重
    4. 优先展示本地条目，补充展示云端条目
    
    Args:
        db: 数据库会话
        search_data: 搜索条件，使用 SubjectSearchBase schema
    
    Returns:
        统一视图模型列表
    """
    import asyncio
    
    # 创建云端搜索数据
    cloud_search_data = SubjectSearchCloud(
        keyword=search_data.keyword if hasattr(search_data, 'keyword') else '',
        type=search_data.type,
        limit=search_data.limit,
        offset=search_data.skip,
        user_id=search_data.user_id
    )
    
    # 并行执行本地搜索和云端搜索
    if hasattr(search_data, 'keyword') and search_data.keyword:
        # 有关键词，使用 search_subject_by_name
        local_task = search_subject_by_name(db, search_data)
    else:
        # 无关键词时使用 get_all_subjects
        local_task = get_all_subjects(db, search_data)
    
    # 云端搜索任务
    remote_task = search_subject_cloud(db, cloud_search_data)
    
    # 并行执行
    local_results, remote_results = await asyncio.gather(local_task, remote_task, return_exceptions=True)
    
    # 处理异常情况
    if isinstance(local_results, Exception):
        logger.error(f"本地搜索失败: {local_results}")
        local_results = UnifiedList(total=0, items=[])
    
    if isinstance(remote_results, Exception):
        logger.error(f"云端搜索失败: {remote_results}")
        remote_results = UnifiedList(total=0, items=[])
    
    logger.info(f"本地搜索结果: {len(local_results.items)} 条记录")
    logger.info(f"云端搜索结果: {len(remote_results.items)} 条记录")
    
    # 合并结果：优先保留本地条目，补充云端独有的条目
    # 创建本地结果的唯一标识集合，用于去重
    local_identifiers = set()
    for item in local_results.items:
        # 确保 item 有 subject 属性，且 subject 有 source 和 source_id 属性
        if hasattr(item, 'subject') and item.subject and hasattr(item.subject, 'source') and hasattr(item.subject, 'source_id'):
            local_identifiers.add((item.subject.source, item.subject.source_id))
    
    # 合并结果列表
    merged_items = list(local_results.items)
    
    # 补充云端独有的条目
    for item in remote_results.items:
        if hasattr(item, 'subject') and item.subject and hasattr(item.subject, 'source') and hasattr(item.subject, 'source_id'):
            item_identifier = (item.subject.source, item.subject.source_id)
            if item_identifier not in local_identifiers:
                merged_items.append(item)
                local_identifiers.add(item_identifier)  # 避免重复添加
    
    # 构建合并后的结果
    merged_result = UnifiedList(
        total=len(merged_items),
        items=merged_items
    )
    
    logger.info(f"合并后搜索结果: {len(merged_items)} 条记录")

    return merged_result


async def sync_subject_air_time(db: AsyncSession, subject_id: str) -> bool:
    """
    同步番剧放送时间

    Args:
        db: 数据库会话
        subject_id: Bangumi 番剧ID

    Returns:
        同步是否成功

    Raises:
        Exception: 同步过程中的异常
    """
    try:
        # 构建搜索数据，查找对应的 Subject
        search_data = SubjectSearchByID(source="bangumi", source_id=subject_id)
        subject_result = await SubjectRepo.get_by_source(db, search_data)
        
        if not subject_result:
            logger.error(f"Subject not found: bangumi/{subject_id}")
            return False
        
        # 解包获取 Subject 对象
        subject, _ = subject_result
        
        # 获取 bangumi-data JSON 数据
        bangumi_data_url = "https://cdn.jsdelivr.net/npm/bangumi-data/dist/data.json"
        async with httpx.AsyncClient() as client:
            response = await client.get(bangumi_data_url)
            response.raise_for_status()
            data = response.json()
        
        # 在 items 中匹配对应的条目
        matched_item = None
        for item in data.get("items", []):
            sites = item.get("sites", [])
            for site in sites:
                if site.get("site") == "bangumi" and site.get("id") == subject_id:
                    matched_item = item
                    break
            if matched_item:
                break
        
        # 更新字段
        subject.last_sync = datetime.now(timezone.utc)
        
        if matched_item and "begin" in matched_item:
            # 解析 begin 字段
            begin_str = matched_item["begin"]
            try:
                begin_dt = datetime.fromisoformat(begin_str)
                # 提取 time 和 weekday
                subject.air_time = begin_dt.time()
                # 注意：Python 的 weekday() 返回 0-6，而要求的是 1-7，所以需要 +1
                subject.air_weekday = begin_dt.weekday() + 1
                logger.info(f"Synced air time for subject {subject_id}: {subject.air_time}, weekday: {subject.air_weekday}")
            except Exception as e:
                logger.error(f"Failed to parse begin field: {e}")
        else:
            logger.info(f"No begin field found for subject {subject_id}, only updating last_sync")
        
        # 提交更新
        await db.commit()
        await db.refresh(subject)
        
        return True
    except Exception as e:
        logger.error(f"Failed to sync subject air time: {e}")
        await db.rollback()
        return False


