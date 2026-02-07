import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from fastapi_cache import FastAPICache
from app.core.logging import get_logger

from ..models import Collection, CollectionStatus, Subject, SubjectType, User
from ..repositories import CollectionRepo, SubjectRepo
from ..schemas.adaptersV2 import douban_to_bangumi_list

logger = get_logger(__name__)

async def sync_user_collections_douban(
    user_id: int,
    db: AsyncSession,
    douban_data: list[dict]
) -> int:
    """
    同步用户的豆瓣收藏数据到本地数据库

    Args:
        user_id: 用户ID
        db: 数据库会话
        douban_data: 豆瓣数据列表

    Returns:
        成功同步的收藏数量

    Raises:
        Exception: 同步过程中发生错误时抛出
    """
    from app.schemas.adaptersV2 import douban_to_bangumi_list, douban_to_collectionlist
    from app.services.collection_service import batch_upsert_collections
    
    try:
        logger.info(f"--- Syncing Douban collections for User ID: {user_id} ---)")
        
        # 确保加载的数据是列表
        if not isinstance(douban_data, list):
            logger.error(f"ERROR: Expected list but got {type(douban_data)}")
            return 0
        
        if not douban_data:
            logger.info("No data to process.")
            return 0
        
        logger.info(f"Processing {len(douban_data)} Douban items")
        
        # 将豆瓣数据转换为Bangumi格式
        logger.info("Converting Douban data to Bangumi format...")
        # 构造符合 douban_to_bangumi_list 接口的数据结构
        douban_data_with_interest = {"interest": douban_data}
        bangumi_data = douban_to_bangumi_list(douban_data_with_interest)
        logger.info(f"Converted {len(bangumi_data.get('data', []))} Douban items to Bangumi format")
        
        # 导入必要的模块
        from app.services.subject_service import batch_upsert_subjects
        from app.schemas.adaptersV2 import bangumi_subject_to_subjectlist, bangumi_collection_to_collectionlist
        
        # 调用适配器转换为SubjectUpsertList格式
        logger.info("Converting Bangumi data to SubjectUpsertList format...")
        subjects_list = bangumi_subject_to_subjectlist(bangumi_data, source="douban")
        logger.info(f"Converted {subjects_list.total} items to SubjectUpsertList format")

        # 调用批量插入函数，实际执行数据库操作
        logger.info("Calling batch_upsert_subjects...")
        subject_success_count = await batch_upsert_subjects(db, subjects_list, user_id)
        logger.info(f"Subjects batch insert completed: {subject_success_count}/{subjects_list.total} items successfully synced")

        # 调用适配器转换为CollectionUpsertList格式
        logger.info("Converting Bangumi data to CollectionUpsertList format...")
        collections_list = bangumi_collection_to_collectionlist(bangumi_data, user_id, source="douban")
        logger.info(f"Converted {collections_list.total} items to CollectionUpsertList format")
        
        # 调用批量插入函数，实际执行数据库操作
        logger.info("Calling batch_upsert_collections...")
        collection_success_count = await batch_upsert_collections(db, collections_list, user_id)
        logger.info(f"Collections batch insert completed: {collection_success_count}/{collections_list.total} items successfully synced")
        
        total_success = subject_success_count + collection_success_count
        logger.info(f"成功同步 {total_success} 条豆瓣收藏记录")
        
        # 清除用户的统计数据缓存
        await FastAPICache.clear(key=f'dashboard:stats:{user_id}')
        logger.info(f"Cleared stats cache for user_id: {user_id}")
        
        return total_success
        
    except FileNotFoundError as e:
        logger.error(f"文件未找到: {e}")
        raise
    except json.JSONDecodeError as e:
        logger.error(f"JSON解析失败: {e}")
        raise
    except Exception as e:
        logger.error(f"同步用户收藏失败: {e}")
        await db.rollback()
        raise
