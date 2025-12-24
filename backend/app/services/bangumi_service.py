from typing import Dict, Any, Optional, List
import logging
import asyncio
from datetime import datetime
from sqlmodel import select, Session
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError

from ..models import Subject, SubjectType, Collection, CollectionStatus, User
from .bangumi_client import fetch_user_collections

logger = logging.getLogger(__name__)

async def upsert_subject(db: AsyncSession, subject_data: Dict[str, Any]) -> Subject:
    """智能映射并清洗Subject数据，支持Type A (Nested) 和 Type B (Full) 两种格式
    
    Args:
        db: 数据库会话
        subject_data: Subject数据，可以是嵌套的(收藏列表中的)或完整的(详情接口)
    
    Returns:
        更新或创建的Subject对象
    """
    # 处理Type A (嵌套在收藏数据中的Subject)
    if "subject" in subject_data:
        subject_data = subject_data["subject"]
    
    subject_id = subject_data.get("id")
    if not subject_id:
        raise ValueError("Subject ID is required")
    
    # 查询数据库中是否已存在该Subject
    result = await db.execute(select(Subject).where(Subject.id == subject_id))
    existing_subject = result.scalar_one_or_none()
    
    # 处理Subject类型
    subject_type = subject_data.get("type")
    try:
        type_enum = SubjectType(subject_type) if subject_type else None
    except ValueError:
        logger.warning(f"未知的Subject类型: {subject_type}, 将使用None")
        type_enum = None
    
    # 处理summary和short_summary
    summary = subject_data.get("summary")
    short_summary = subject_data.get("short_summary")
    
    # 优先使用summary，如果没有且数据库中也没有，则使用short_summary
    final_summary = None
    if summary:
        final_summary = summary
    elif short_summary and not (existing_subject and existing_subject.summary):
        final_summary = short_summary
    elif existing_subject and existing_subject.summary:
        final_summary = existing_subject.summary
    
    # 处理封面图片
    cover_url = ""
    images = subject_data.get("images", {})
    if images:
        cover_url = images.get("large", images.get("common", ""))
    
    # 处理评分信息 (Type A扁平格式 vs Type B嵌套格式)
    score = None
    rank = None
    rating_details = {}
    
    if "rating" in subject_data:
        # Type B格式
        rating = subject_data["rating"]
        score = rating.get("score")
        rank = rating.get("rank")
        rating_details = rating.copy()
    else:
        # Type A格式
        score = subject_data.get("score")
        rank = subject_data.get("rank")
        if score is not None or rank is not None:
            rating_details = {"score": score, "rank": rank}
    
    # 处理集数/卷数
    eps = subject_data.get("eps")
    total_episodes = subject_data.get("total_episodes")
    # 如果有total_episodes则优先使用，否则使用eps
    final_eps = total_episodes if total_episodes is not None else eps
    
    volumes = subject_data.get("volumes")
    
    # 处理标签
    tags = []
    raw_tags = subject_data.get("tags", [])
    if raw_tags:
        if isinstance(raw_tags[0], dict):
            # Type A格式: [{'name': '标签名', 'count': 123}]
            tags = [tag["name"] for tag in raw_tags]
        elif isinstance(raw_tags[0], str):
            # Type B格式: ['标签名1', '标签名2']
            tags = raw_tags
    
    meta_tags = subject_data.get("meta_tags", [])
    
    # 处理其他字段
    name = subject_data.get("name", "")
    name_cn = subject_data.get("name_cn", "")
    date = subject_data.get("date")
    platform = subject_data.get("platform")
    infobox = subject_data.get("infobox", [])
    collection_total = subject_data.get("collection_total")
    
    if existing_subject:
        # 更新现有Subject
        existing_subject.type = type_enum
        existing_subject.name = name
        existing_subject.name_cn = name_cn
        existing_subject.summary = final_summary
        existing_subject.cover_url = cover_url
        existing_subject.date = date
        existing_subject.platform = platform
        existing_subject.score = score
        existing_subject.rank = rank
        existing_subject.eps = final_eps
        existing_subject.volumes = volumes
        existing_subject.collection_total = collection_total
        existing_subject.tags = tags
        existing_subject.meta_tags = meta_tags
        existing_subject.infobox = infobox
        existing_subject.rating_details = rating_details
        
        db.add(existing_subject)
        await db.commit()
        await db.refresh(existing_subject)
        return existing_subject
    else:
        # 创建新Subject
        new_subject = Subject(
            id=subject_id,
            type=type_enum,
            name=name,
            name_cn=name_cn,
            summary=final_summary,
            cover_url=cover_url,
            date=date,
            platform=platform,
            score=score,
            rank=rank,
            eps=final_eps,
            volumes=volumes,
            collection_total=collection_total,
            tags=tags,
            meta_tags=meta_tags,
            infobox=infobox,
            rating_details=rating_details
        )
        
        db.add(new_subject)
        await db.commit()
        await db.refresh(new_subject)
        return new_subject


async def _upsert_collection(db: AsyncSession, user_id: int, subject_id: int, collection_data: Dict[str, Any]) -> Collection:
    """
    更新或创建Collection记录
    
    Args:
        db: 数据库会话
        user_id: 用户ID
        subject_id: 条目ID
        collection_data: 收藏数据
    
    Returns:
        更新或创建的Collection对象
    """
    # 提取收藏状态
    collection_type = collection_data.get("type")
    try:
        collection_status = CollectionStatus(collection_type) if collection_type else None
    except ValueError:
        logger.warning(f"未知的收藏状态: {collection_type}，将使用None")
        collection_status = None
    
    # 提取其他收藏元数据
    rate = collection_data.get("rate")
    updated_at_str = collection_data.get("updated_at")
    
    if not updated_at_str:
        raise ValueError("Updated at time is required")
    
    # 转换更新时间字符串为 datetime 对象
    updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
    
    # 关键修改：如果有时区信息，将其移除 (Make it naive)
    if updated_at.tzinfo is not None:
        updated_at = updated_at.replace(tzinfo=None)
    
    private = collection_data.get("private", False)
    
    # 查询是否已存在收藏记录
    stmt = select(Collection).where(
        Collection.user_id == user_id,
        Collection.subject_id == subject_id
    )
    result = await db.execute(stmt)
    existing_collection = result.scalar_one_or_none()
    
    # 构造Collection数据
    collection_fields = {
        "user_id": user_id,
        "subject_id": subject_id,
        "type": collection_status,
        "rate": rate,
        "updated_at": updated_at,
        "private": private
    }
    
    if existing_collection:
        # 更新现有记录
        for field, value in collection_fields.items():
            setattr(existing_collection, field, value)
        db.add(existing_collection)
        await db.commit()
        await db.refresh(existing_collection)
        return existing_collection
    else:
        # 创建新记录
        new_collection = Collection(**collection_fields)
        db.add(new_collection)
        await db.commit()
        await db.refresh(new_collection)
        return new_collection


async def sync_user_collections(username: str, db: AsyncSession, subject_type: Optional[int] = None) -> int:
    """
    同步用户的 Bangumi 收藏数据到本地数据库
    
    Args:
        username: Bangumi 用户名
        db: 数据库会话
        subject_type: 可选，条目类型 (1=书籍/2=动画/3=音乐/4=游戏/6=三次元)
        
    Returns:
        成功同步的收藏数量
        
    Raises:
        Exception: 同步过程中发生错误时抛出
    """
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
        logger.info(f"--- Syncing for User ID: {user_id} ---")
        # --- 获取或创建用户 End ---
        
        # 初始化分页参数
        limit = 50
        offset = 0
        sync_count = 0
        
        while True:
            logger.info(f"--- Fetching page with offset: {offset}, limit: {limit} ---")
            
            # 获取用户收藏数据（带分页参数）
            response_json = await fetch_user_collections(username, subject_type, limit=limit, offset=offset)
            
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
            
            # 遍历当前页的收藏数据
            for item in items:
                # 确保item是字典
                if not isinstance(item, dict):
                    continue
                try:
                    # --- 步骤 A: 先处理 Subject (绝对优先) ---
                    subject_data = item.get("subject")
                    if not subject_data:
                        logger.warning(f"收藏项缺少subject数据，跳过: {item}")
                        continue
                        
                    # 调用专门的函数处理 Subject 入库
                    # 这个函数负责：查询 DB -> 不存在则 create -> 存在则 update -> session.commit()
                    current_subject = await upsert_subject(db, subject_data)
                    
                    # --- 步骤 B: 再处理 Collection (只引用 ID) ---
                    # 此时我们只用 subject_id，不再传递整个 Subject 对象，彻底切断 ORM 写入时的纠缠
                    await _upsert_collection(db, user_id, current_subject.id, item)
                    
                    sync_count += 1
                    logger.info(f"同步收藏: {current_subject.name} (ID: {current_subject.id}) [类型: {SubjectType(current_subject.type).name if current_subject.type else '未知'}]")
                    
                except SQLAlchemyError as e:
                    logger.error(f"数据库操作失败: {e}")
                    await db.rollback()  # 回滚当前事务
                    # 继续处理下一个条目，不中断整个同步过程
                    continue
                except ValueError as e:
                    logger.error(f"数据验证失败: {e}")
                    await db.rollback()  # 回滚当前事务
                    continue
                except Exception as e:
                    logger.error(f"处理收藏项失败: {e}")
                    await db.rollback()  # 回滚当前事务
                    continue
            
            # 检查是否已经获取了所有数据
            total_in_server = response_json.get('total', 0)
            if sync_count >= total_in_server:
                logger.info(f"All {total_in_server} items have been fetched.")
                break
            
            # 更新offset，准备获取下一页
            offset += limit
            
            # 防封禁延迟：非常重要，避免请求过快被Ban
            await asyncio.sleep(0.5)
        
        logger.info(f"成功同步 {sync_count} 条收藏记录")
        return sync_count
        
    except Exception as e:
        logger.error(f"同步用户收藏失败: {e}")
        # 回滚事务
        await db.rollback()
        raise
