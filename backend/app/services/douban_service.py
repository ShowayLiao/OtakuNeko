import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..models import Collection, CollectionStatus, Subject, SubjectType, User
from ..repositories import CollectionRepo, SubjectRepo
from ..schemas.adapters import convert_douban_to_bangumi

logger = logging.getLogger(__name__)

async def sync_user_collections_douban(
    user_id: int,
    db: AsyncSession,
    file_path: str
) -> int:
    """
    同步用户的豆瓣收藏数据到本地数据库

    Args:
        user_id: 用户ID
        db: 数据库会话
        file_path: 豆瓣数据JSON文件路径

    Returns:
        成功同步的收藏数量

    Raises:
        Exception: 同步过程中发生错误时抛出
    """
    import json
    from app.schemas.adapters import adapt_douban_data_to_collection_list
    from app.services.collection_service import batch_upsert_collections
    
    try:
        logger.info(f"--- Syncing Douban collections for User ID: {user_id} ---")
        
        # 加载JSON文件
        logger.info(f"Loading Douban data from file: {file_path}")
        with open(file_path, 'r', encoding='utf-8') as f:
            douban_data = json.load(f)
        
        # 确保加载的数据是列表
        if not isinstance(douban_data, list):
            logger.error(f"ERROR: Expected list but got {type(douban_data)}")
            return 0
        
        if not douban_data:
            logger.info("No data to process.")
            return 0
        
        logger.info(f"Loaded {len(douban_data)} Douban items")
        
        # 将豆瓣数据转换为CollectionList格式
        logger.info("Converting Douban data to CollectionList format...")
        collections_list = adapt_douban_data_to_collection_list(douban_data)
        logger.info(f"Converted {collections_list.total} items to CollectionList format")
        
        # 调用批量插入函数
        logger.info("Calling batch_upsert_collections...")
        success_count = await batch_upsert_collections(db, collections_list, user_id)
        logger.info(f"Batch insert completed: {success_count}/{collections_list.total} items successfully synced")
        
        logger.info(f"成功同步 {success_count} 条豆瓣收藏记录")
        return success_count
        
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
