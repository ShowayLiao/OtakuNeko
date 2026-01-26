import asyncio
import logging
from typing import Any, Dict, Optional

from fastapi_cache import FastAPICache
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..models import Subject, SubjectType, User
from ..repositories import CollectionRepo, SubjectRepo
from ..schemas.adapters import adapt_bangumi_subject
from .bangumi_client import fetch_subject_detail, fetch_user_collections

logger = logging.getLogger(__name__)


from app.schemas.collection import CollectionList, CollectionSyncRequest

async def sync_user_collections(
    username: str, 
    db: AsyncSession, 
    request_data: Optional[CollectionSyncRequest] = None
) -> int:
    """
    同步用户的 Bangumi 收藏数据到本地数据库
    
    Args:
        username: Bangumi 用户名
        db: 数据库会话
        request_data: 同步请求数据，包含limit、offset、subject_type等参数
        
    Returns:
        成功同步的收藏数量
        
    Raises:
        Exception: 同步过程中发生错误时抛出
    """
    from app.services.collection_service import batch_upsert_collections
    from app.schemas.adapters import adapt_bangumi_collection_to_list
    
    try:
        # --- 获取或创建用户 Start ---
        # 1. 先查数据库里有没有这个用户
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalars().first()
        
        # 2. 如果没有，就现场创建一个（为了防止同步失败）
        if not user:
            logger.info(f"User {username} not found, creating new user...")
            user = User(username=username, nickname=username, email=f"{username}@placeholder.com")
            db.add(user)
            await db.commit()
            await db.refresh(user)
        
        user_id = user.id
        logger.info(f"--- Syncing for User ID: {user_id} --- ")
        # --- 获取或创建用户 End ---
        
        # 初始化分页参数
        limit = request_data.limit if request_data and request_data.limit else 50
        offset = request_data.offset if request_data and request_data.offset else 0
        subject_type = request_data.subject_type if request_data and request_data.subject_type else None
        sync_count = 0
        total_success = 0
        
        while True:
            logger.info(f"--- Fetching page with offset: {offset}, limit: {limit} ---")
            
            # 获取用户收藏数据（带分页参数）
            logger.info(f"准备请求Bangumi API: username={username}, subject_type={subject_type}, limit={limit}, offset={offset}")
            response_json = await fetch_user_collections(username, subject_type, limit=limit, offset=offset)
            logger.info(f"Bangumi API response received, data count: {len(response_json.get('data', []))}, total: {response_json.get('total', 0)}")
            
            # 调用适配器转换为CollectionList格式
            collections_list = adapt_bangumi_collection_to_list(response_json)
            
            # 导入需要的模块
            from app.services.collection_service import batch_upsert_collections
            
            # 调用批量插入函数，实际执行数据库操作
            success_count = await batch_upsert_collections(db, collections_list, user_id)
            total_success += success_count
            logger.info(f"--- Page processed: {success_count}/{collections_list.total} items successfully synced --- ")
            
            # 提取真正的列表
            items = response_json.get("data", [])
            
            # 增加安全检查
            if not isinstance(items, list):
                logger.error(f"ERROR: Expected list but got {type(items)}")
                break
            
            # 检查是否没有数据了
            if not items:
                logger.info("No more data to fetch.")
                break
            
            # 检查是否已经获取了所有数据
            total_in_server = response_json.get('total', 0)
            # 计算是否还有下一页数据
            # 1. 如果当前页数据不足limit条，说明是最后一页
            # 2. 如果下一页的offset >= total_in_server，说明已经到了最后一页
            if len(items) < limit or (offset + limit) >= total_in_server:
                logger.info(f"All {total_in_server} items have been fetched.")
                break
            
            # 更新offset，准备获取下一页
            offset += limit
            
            # 防封禁延迟：非常重要，避免请求过快被Ban
            await asyncio.sleep(0.5)
        
        logger.info(f"成功同步 {total_success} 条收藏记录")
        
        # 清理用户统计数据缓存，确保首页统计数据即时刷新
        try:
            await FastAPICache.clear(key=f'dashboard:stats:{user_id}')
            logger.info(f"已清理用户 {user_id} 的统计数据缓存")
        except Exception as e:
            logger.warning(f"清理缓存失败: {e}")
        
        return total_success
        
    except Exception as e:
        import traceback
        logger.error(f"同步用户收藏失败: {e}")
        logger.error(f"错误详情: {traceback.format_exc()}")
        # 回滚事务
        await db.rollback()
        raise


async def sync_subject_detail(subject_id: int, db: AsyncSession, *, source: str = "bangumi") -> Subject:
    """
    从 Bangumi API 同步单个条目的详细信息到本地数据库
    
    Args:
        subject_id: Bangumi 条目 ID
        db: 数据库会话
        source: 数据来源，默认为 "bangumi"
        
    Returns:
        同步后的 Subject 对象
        
    Raises:
        httpx.HTTPStatusError: 请求失败时抛出
        httpx.RequestError: 网络错误时抛出
    """
    # 从 Bangumi API 获取条目详情
    bangumi_data = await fetch_subject_detail(subject_id)
    
    # 使用适配器转换数据格式
    adapted_data = adapt_bangumi_subject(bangumi_data)
    
    # 转换为 SubjectUpdate 对象
    from app.schemas.subject import SubjectUpdate, SubjectUpdateList
    subject_update = SubjectUpdate(
        source=source,
        source_id=str(subject_id),
        name=adapted_data.get("name"),
        name_cn=adapted_data.get("name_cn"),
        type=adapted_data.get("type"),
        summary=adapted_data.get("summary"),
        date=adapted_data.get("date"),
        platform=adapted_data.get("platform"),
        eps=adapted_data.get("eps"),
        volumes=adapted_data.get("volumes"),
        images=adapted_data.get("images"),
        image=adapted_data.get("image"),
        tags=adapted_data.get("tags"),
        meta_tags=adapted_data.get("meta_tags"),
        infobox=adapted_data.get("infobox"),
        rating=adapted_data.get("rating"),
        collection=adapted_data.get("collection"),
        series=adapted_data.get("series"),
        locked=adapted_data.get("locked"),
        nsfw=adapted_data.get("nsfw")
    )
    
    # 创建 SubjectUpdateList
    subject_update_list = SubjectUpdateList(
        total=1,
        items=[subject_update]
    )
    
    # 调用批量更新函数
    from app.services.subject_service import batch_update_subjects
    await batch_update_subjects(db, subject_update_list)
    
    # 从数据库中获取更新后的 Subject 对象
    from app.repositories.subject_repo import SubjectRepo
    from app.schemas.subject import SubjectSearchByID
    subject_search = SubjectSearchByID(source=source, source_id=str(subject_id))
    subject_result = await SubjectRepo.get_by_source(db, subject_search)
    
    return subject_result[0] if subject_result else None
