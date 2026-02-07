import asyncio
from typing import Any, Dict, Optional

from fastapi_cache import FastAPICache
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..models import Subject, SubjectType, User
from ..repositories import CollectionRepo, SubjectRepo
from ..schemas.adaptersV2 import bangumi_subject_to_subjectlist
from ..schemas.user import UserRead
from .bangumi_client import fetch_subject_detail, fetch_user_collections, fetch_user_info
from app.core.logging import get_logger

logger = get_logger(__name__)


from app.schemas.collection import CollectionList, CollectionSyncRequest

async def sync_user_collections(
    user: UserRead, 
    db: AsyncSession, 
    request_data: Optional[CollectionSyncRequest] = None
) -> int:
    """
    同步用户的 Bangumi 收藏数据到本地数据库
    
    Args:
        user: 用户信息（UserRead schema）
        db: 数据库会话
        request_data: 同步请求数据，包含limit、offset、subject_type等参数
        
    Returns:
        成功同步的收藏数量
        
    Raises:
        Exception: 同步过程中发生错误时抛出
    """
    username = user.username
    from app.services.collection_service import batch_upsert_collections
    from app.schemas.adaptersV2 import bangumi_subject_to_subjectlist
    from app.services.subject_service import batch_upsert_subjects
    
    try:
        # --- 获取或创建用户 Start ---
        # 1. 先查数据库里有没有这个用户（使用 id 字段查询，更高效）
        result = await db.execute(select(User).where(User.id == user.id))
        db_user = result.scalars().first()
        
        # 2. 如果没有，就现场创建一个（为了防止同步失败）
        if not db_user:
            logger.info(f"User {user.username} not found, creating new user...")
            db_user = User(
                id=user.id,
                username=user.username,
                nickname=user.username,
                email=f"{user.username}@placeholder.com"
            )
            db.add(db_user)
            await db.commit()
            await db.refresh(db_user)
        
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
            # 优先使用 bangumi_id，如果没有则使用 username
            bangumi_name = user.bangumi_name
            api_username = bangumi_name if bangumi_name else username
            logger.info(f"准备请求Bangumi API: username={api_username}, subject_type={subject_type}, limit={limit}, offset={offset}")
            response_json = await fetch_user_collections(api_username, subject_type, limit=limit, offset=offset)
            logger.info(f"Bangumi API response received, data count: {len(response_json.get('data', []))}, total: {response_json.get('total', 0)}")
            
            # 调用适配器转换为SubjectUpsertList格式
            subjects_list = bangumi_subject_to_subjectlist(response_json)

            # 调用批量插入函数，实际执行数据库操作
            subject_success_count = await batch_upsert_subjects(db, subjects_list)
            total_success += subject_success_count
            logger.info(f"--- Page processed: {subject_success_count}/{subjects_list.total} items successfully synced --- ")

            # 调用适配器转换为CollectionUpsertList格式
            from app.schemas.adaptersV2 import bangumi_collection_to_collectionlist
            collections_list = bangumi_collection_to_collectionlist(response_json, user_id)
            
            # 调用批量插入函数，实际执行数据库操作
            collection_success_count = await batch_upsert_collections(db, collections_list, user_id)
            total_success += collection_success_count
            logger.info(f"--- Page processed: {collection_success_count}/{collections_list.total} items successfully synced --- ")
            
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
    from app.schemas.subject import SubjectUpdate, SubjectUpdateList
    # 构造符合 bangumi_subject_to_subjectlist 接口的数据结构
    bangumi_data_with_data = {"data": [bangumi_data]}
    subject_upsert_list = bangumi_subject_to_subjectlist(bangumi_data_with_data)
    
    # 提取第一个条目数据
    if subject_upsert_list.items:
        adapted_data = subject_upsert_list.items[0]
        # 转换为 SubjectUpdate 对象
        subject_update = SubjectUpdate(
            source=source,
            source_id=str(subject_id),
            name=adapted_data.name,
            name_cn=adapted_data.name_cn,
            type=adapted_data.type,
            summary=adapted_data.summary,
            date=adapted_data.date,
            platform=adapted_data.platform,
            eps=adapted_data.eps,
            volumes=adapted_data.volumes,
            images=adapted_data.images,
            image=adapted_data.image,
            tags=adapted_data.tags,
            meta_tags=adapted_data.meta_tags,
            infobox=adapted_data.infobox,
            rating=adapted_data.rating,
            collection=adapted_data.collection,
            series=adapted_data.series,
            locked=adapted_data.locked,
            nsfw=adapted_data.nsfw
        )
        
        # 创建 SubjectUpdateList
        subject_update_list = SubjectUpdateList(
            total=1,
            items=[subject_update]
        )
    else:
        # 如果转换失败，创建一个空的 SubjectUpdateList
        subject_update_list = SubjectUpdateList(
            total=0,
            items=[]
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


async def get_bangumi_user_info(username: str) -> Dict:
    """
    获取 Bangumi 用户信息
    
    Args:
        username: Bangumi 用户名
        
    Returns:
        包含用户信息的字典
        
    Raises:
        Exception: 获取用户信息过程中发生错误时抛出
    """
    try:
        logger.info(f"获取 Bangumi 用户信息: {username}")
        
        # 调用 bangumi_client.py 中的 fetch_user_info 函数获取用户信息
        user_info = await fetch_user_info(username)
        
        logger.info(f"成功获取 Bangumi 用户信息: {username}")
        
        return user_info
        
    except Exception as e:
        import traceback
        logger.error(f"获取 Bangumi 用户信息失败: {e}")
        logger.error(f"错误详情: {traceback.format_exc()}")
        raise
