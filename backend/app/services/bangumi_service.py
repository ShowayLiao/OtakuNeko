import asyncio
from typing import Any, Dict, Optional, List

from fastapi_cache import FastAPICache
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from ..models import Subject, SubjectType, User
from ..repositories import CollectionRepo, SubjectRepo
from ..schemas.adaptersV2 import bangumi_subject_to_subjectlist
from ..schemas.user import UserRead
from ..schemas.bangumi import StaffInfo, SubjectDetail
from .bangumi_client import fetch_subject_detail, fetch_user_collections, fetch_user_info, bangumi_client, fetch_calendar
from app.schemas.bangumi import BangumiCalendar, BangumiCalendarDay, BangumiCalendarItem, BangumiCalendarRating, BangumiCalendarCollection, BangumiCalendarImage
from app.core.logging import get_logger
from app.schemas.collection import CollectionList, CollectionSyncRequest

logger = get_logger(__name__)

# === 核心映射表 (The Magic) ===
# 将 Bangumi 的非标准叫法映射为 AI 易读的叫法
ROLE_MAPPING = {
    "导演": "Director (监督)",
    "总导演": "Chief Director (总监督)",
    "脚本": "Script (脚本)",
    "系列构成": "Series Composition (系构)",
    "原作": "Original Creator (原作)",
    "人物设定": "Character Design (人设)",
    "动画制作": "Studio (制作公司)",  # 关键：把公司提取出来
    "音乐": "Music (音乐)",
    "美术监督": "Art Director (美监)",
    "作画监督": "Animation Director (作监)",
    "总作画监督": "Chief Animation Director (总作监)"
}

async def fetch_subject_by_id(subject_id: int) -> SubjectDetail:
    """
    获取条目详情，并自动清洗 Staff 数据。
    """
    try:
        # 并行请求：同时获取"详情"和"角色/制作人员"
        # 获取条目详情
        subject_data = await fetch_subject_detail(subject_id)
        
        # 获取人员信息
        persons_data = await bangumi_client.get_persons_raw(subject_id)
        
        # 处理 Staff 数据
        raw_staff = []
        
        # 从 persons_data 中提取 staff 信息
        for person in persons_data:
            for relation in person.get('relations', []):
                raw_staff.append({
                    "name": person.get('name', ''),
                    "relation": relation.get('name', '')
                })
        
        # 清洗 staff 数据
        cleaned_staff = _clean_staff_data(raw_staff)
        
        return SubjectDetail(
            id=subject_data.get("id", subject_id),
            name=subject_data.get("name", ""),
            name_cn=subject_data.get("name_cn"),
            summary=subject_data.get("summary", ""),
            score=subject_data.get("rating", {}).get("score", 0.0),
            rank=subject_data.get("rating", {}).get("rank", 0),
            core_staff=cleaned_staff
        )
    except Exception as e:
        logger.error(f"获取条目详情失败: {e}")
        raise

def _clean_staff_data(raw_staff_list: List[Dict[str, Any]]) -> List[StaffInfo]:
    """
    私有辅助函数：清洗 Staff 列表，过滤噪音，标准化职位。
    """
    cleaned = []
    seen = set() # 用于去重

    for person in raw_staff_list:
        # API 返回的 relation 可能是 "动画制作" 或者 "CV"
        raw_relation = person.get("relation", "")
        name = person.get("name", "")
        
        # 1. 检查是否在我们的白名单里
        if raw_relation in ROLE_MAPPING:
            standardized_role = ROLE_MAPPING[raw_relation]
            
            # 2. 去重 (防止同一个人同一个职位出现两次)
            identifier = f"{name}-{standardized_role}"
            if identifier not in seen:
                cleaned.append(StaffInfo(name=name, role=standardized_role))
                seen.add(identifier)
    
    return cleaned

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


async def get_bangumi_calendar() -> BangumiCalendar:
    """
    获取 Bangumi 每日放送信息
    
    Returns:
        Bangumi 每日放送信息
        
    Raises:
        Exception: 获取日历信息过程中发生错误时抛出
    """
    try:
        logger.info("获取 Bangumi 每日放送信息")
        
        # 调用 bangumi_client.py 中的 fetch_calendar 函数获取日历信息
        calendar_info = await fetch_calendar()
        
        logger.info("成功获取 Bangumi 每日放送信息")
        
        # 转换数据结构以匹配 schema
        calendar_days = []
        for day_data in calendar_info:
            # 转换 items
            items = []
            for item in day_data.get('items', []):
                # 转换 rating
                rating_data = item.get('rating', {})
                rating = BangumiCalendarRating(
                    score=rating_data.get('score'),
                    total=rating_data.get('total'),
                    rank=item.get('rank'),
                    count=rating_data.get('count')
                )
                
                # 转换 collection
                collection_data = item.get('collection', {})
                collection = BangumiCalendarCollection(
                    wish=collection_data.get('wish'),
                    collect=collection_data.get('collect'),
                    doing=collection_data.get('doing'),
                    done=collection_data.get('done'),
                    on_hold=collection_data.get('on_hold'),
                    dropped=collection_data.get('dropped')
                )
                
                # 转换 images
                images_data = item.get('images', {})
                images = BangumiCalendarImage(
                    large=images_data.get('large'),
                    common=images_data.get('common'),
                    medium=images_data.get('medium'),
                    small=images_data.get('small')
                )
                
                # 创建 item
                calendar_item = BangumiCalendarItem(
                    id=item.get('id'),
                    url=item.get('url'),
                    type=item.get('type'),
                    name=item.get('name'),
                    name_cn=item.get('name_cn'),
                    summary=item.get('summary', ''),
                    air_date=item.get('air_date'),
                    air_weekday=item.get('air_weekday'),
                    images=images,
                    rating=rating,
                    collection=collection
                )
                items.append(calendar_item)
            
            # 创建 day
            calendar_day = BangumiCalendarDay(
                weekday=day_data.get('weekday', {}),
                items=items
            )
            calendar_days.append(calendar_day)
        
        # 创建并返回 BangumiCalendar
        return BangumiCalendar(root=calendar_days)
        
    except Exception as e:
        import traceback
        logger.error(f"获取 Bangumi 每日放送信息失败: {e}")
        logger.error(f"错误详情: {traceback.format_exc()}")
        raise
