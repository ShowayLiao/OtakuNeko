import logging
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, or_

from app.models import Collection, Subject, SubjectType, User
from app.schemas.collection import CollectionRead, CollectionList
from app.schemas.subject import (
    SubjectCreate, SubjectUpdate, SubjectUpdateList, 
    SubjectSearchByID, SubjectSearchBase, SubjectSearchCloud, SubjectSearchByName
)
from app.services.bangumi_client import search_subjects as search_bangumi_subjects
from app.repositories.subject_repo import SubjectRepo

logger = logging.getLogger(__name__)


async def create_subject(
    db: AsyncSession,
    subject_data: SubjectCreate,
) -> Subject:
    """
    创建新条目，使用SubjectCreate格式
    
    Args:
        db: 数据库会话
        subject_data: 条目数据，使用SubjectCreate schema
    
    Returns:
        创建的Subject对象
    """
    try:
        # 直接创建subject，不需要转换数据类型
        created_subject = await SubjectRepo.create(db, subject_data)
        logger.info(f"创建条目成功: {created_subject.name} (ID: {created_subject.id})")
        return created_subject
    except Exception as e:
        logger.error(f"创建条目失败: {e}")
        raise



async def get_subject_by_source(
    db: AsyncSession,
    search_data: SubjectSearchByID
) -> Optional[CollectionRead]:
    """
    根据数据源和ID获取条目
    
    Args:
        db: 数据库会话
        search_data: 搜索条件，使用SubjectSearchByID schema
    
    Returns:
        包含条目信息的CollectionRead对象
    """
    try:
        from app.schemas.adapters import adapt_to_collection_read
        
        subject, collection = await SubjectRepo.get_by_source(db, search_data)
        if not subject:
            return None
        
        # 转换为CollectionRead格式
        return adapt_to_collection_read(subject, collection)
    except Exception as e:
        logger.error(f"获取条目失败: {e}")
        raise


async def update_subject(
    db: AsyncSession,
    subject_data: SubjectUpdate
) -> Optional[Subject]:
    """
    更新条目，使用SubjectUpdate schema
    
    Args:
        db: 数据库会话
        subject_data: 更新的条目数据，使用SubjectUpdate schema
    
    Returns:
        更新后的Subject对象或None
    """
    try:
        # 调用仓库方法更新subject，直接使用SubjectUpdate schema
        updated_subject = await SubjectRepo.update(db, subject_data)
        
        if updated_subject:
            logger.info(f"更新条目成功: {updated_subject.name} (ID: {updated_subject.id})")
        return updated_subject
    except Exception as e:
        logger.error(f"更新条目失败: {e}")
        raise


async def batch_update_subjects(
    db: AsyncSession,
    subject_list: SubjectUpdateList
) -> int:
    """
    批量更新条目，使用SubjectUpdateList schema
    
    Args:
        db: 数据库会话
        subject_list: 更新的条目列表数据，使用SubjectUpdateList schema
    
    Returns:
        成功更新的条目数量
    """
    success_count = 0
    
    for subject_data in subject_list.items:
        try:
            # 调用单个更新方法
            result = await update_subject(db, subject_data)
            if result:
                success_count += 1
        except Exception as e:
            logger.error(f"批量更新条目失败: {e}, 数据: {subject_data.model_dump()}")
            # 继续处理下一个条目，不中断整个批量操作
            continue
    
    logger.info(f"批量更新完成，成功更新 {success_count}/{subject_list.total} 个条目")
    return success_count


async def delete_subject(
    db: AsyncSession,
    search_data: SubjectSearchByID
) -> bool:
    """
    删除条目，使用SubjectSearchByID schema
    
    Args:
        db: 数据库会话
        search_data: 搜索条件，使用SubjectSearchByID schema
    
    Returns:
        删除成功返回True，条目不存在返回False
    """
    try:
        # 直接使用 SubjectSearchByID schema 删除条目
        deleted = await SubjectRepo.delete(db, search_data)
        if deleted:
            logger.info(f"删除条目成功: source={search_data.source}, source_id={search_data.source_id}")
        return deleted
    except Exception as e:
        logger.error(f"删除条目失败: {e}")
        raise


async def get_all_subjects(
    db: AsyncSession,
    search_data: SubjectSearchBase
) -> CollectionList:
    """
    获取所有条目，使用SubjectSearchBase schema
    
    Args:
        db: 数据库会话
        search_data: 搜索条件，使用SubjectSearchBase schema
    
    Returns:
        包含总记录数和条目列表的CollectionList对象
    """
    try:
        from app.schemas.adapters import adapt_to_collection_list
        
        subject_collection_tuples = await SubjectRepo.get_all(db, search_data)
        total = await SubjectRepo.count(db, search_data.type)
        
        # 分离subject和collection对象
        subjects = [subject for subject, _ in subject_collection_tuples]
        collections = [collection for _, collection in subject_collection_tuples]
        
        # 转换为CollectionList格式
        return adapt_to_collection_list(subjects, collections)
    except Exception as e:
        logger.error(f"获取条目列表失败: {e}")
        raise





async def search_subject_by_name(
    db: AsyncSession,
    search_data: SubjectSearchByName
) -> CollectionList:
    """
    基于名称的宽泛搜索，使用SubjectSearchByName schema
    
    Args:
        db: 数据库会话
        search_data: 搜索条件，使用SubjectSearchByName schema
    
    Returns:
        包含总记录数和搜索结果列表的CollectionList对象
    """
    try:
        from app.schemas.adapters import adapt_to_collection_list
        
        subject_collection_tuples = await SubjectRepo.search_by_name(db, search_data)
        total = await SubjectRepo.count_by_name(db, search_data.keyword)
        
        # 分离subject和collection对象
        subjects = [subject for subject, _ in subject_collection_tuples]
        collections = [collection for _, collection in subject_collection_tuples]
        
        # 转换为CollectionList格式
        return adapt_to_collection_list(subjects, collections)
    except Exception as e:
        logger.error(f"搜索条目失败: {e}")
        raise


async def search_subject_cloud(
    db: AsyncSession,
    search_data: SubjectSearchCloud
) -> CollectionList:
    """
    调用 Bangumi API 进行搜索，使用SubjectSearchCloud schema
    
    Args:
        db: 数据库会话
        search_data: 搜索条件，使用SubjectSearchCloud schema
    
    Returns:
        包含总记录数和远程搜索结果的CollectionList对象
    """
    try:
        from app.schemas.adapters import adapt_remote_data_to_collection_list
        
        logger.info(f"从 Bangumi API 搜索: {search_data.keyword}")
        remote_response = await search_bangumi_subjects(search_data.keyword, search_data.type, search_data.limit, search_data.offset)
        
        # 转换为CollectionList格式
        return adapt_remote_data_to_collection_list(remote_response)
        
    except Exception as e:
        logger.error(f"远程搜索失败: {e}")
        from app.schemas.collection import CollectionList
        # 返回空结果列表
        return CollectionList(
            total=0,
            items=[]
        )



async def search_mixed(
    db: AsyncSession,
    search_data: SubjectSearchBase
) -> CollectionList:
    """
    混合搜索服务：本地优先，远程回退
    
    实现策略：
    1. Step 1 (Local): 使用 SQL LIKE 查询本地 Subject 表
    2. Step 2 (Remote Check): 如果本地结果数量为 0，则调用 Bangumi API
    3. Step 3 (Adaptation): 如果数据来自 Remote，使用适配器模式转换为统一格式，但不入库
    
    Args:
        db: 数据库会话
        search_data: 搜索条件，使用 SubjectSearchBase schema
    
    Returns:
        包含总记录数和搜索结果列表的CollectionList对象
    """
    from app.schemas.subject import SubjectSearchByName
    
    # 根据是否有关键词创建相应的搜索数据
    if hasattr(search_data, 'keyword') and search_data.keyword:
        # 有关键词，使用 search_subject_by_name
        local_results = await search_subject_by_name(db, search_data)
    else:
        # 无关键词时使用 get_all_subjects
        local_results = await get_all_subjects(db, search_data)
    
    if local_results.items:
        # 本地有结果，记录日志并直接返回CollectionList
        logger.info(f"本地搜索结果: {len(local_results.items)} 条记录")
        return local_results
    
    # Step 2: 本地无结果，尝试远程搜索 - 使用 search_subject_cloud
    # 创建 SubjectSearchCloud 数据
    from app.schemas.subject import SubjectSearchCloud
    cloud_search_data = SubjectSearchCloud(
        keyword=search_data.keyword if hasattr(search_data, 'keyword') else '',
        type=search_data.type,
        limit=search_data.limit,
        offset=search_data.skip,
        user_id=search_data.user_id
    )
    remote_results = await search_subject_cloud(db, cloud_search_data)
    logger.info(f"远程搜索结果: {len(remote_results.items)} 条记录")
    
    # 远程搜索结果已为CollectionList，直接返回
    return remote_results


