import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from sqlmodel import select

from ..models import Collection, CollectionStatus, Subject, SubjectType, User
from .bangumi_service import _upsert_collection, upsert_subject

logger = logging.getLogger(__name__)

async def sync_user_collections_db(
    username: str,
    db: AsyncSession,
    DBFile: list,
    subject_type: Optional[int] = None
) -> int:
    """
    同步用户的 Bangumi 收藏数据到本地数据库

    Args:
        username: Bangumi 用户名
        db: 数据库会话
        DBFile: 豆瓣数据列表
        subject_type: 可选，条目类型 (1=书籍/2=动画/3=音乐/4=游戏/6=三次元)

    Returns:
        成功同步的收藏数量

    Raises:
        Exception: 同步过程中发生错误时抛出
    """
    try:
        result = await db.execute(select(User).where(User.username == username))
        user = result.scalars().first()

        if not user:
            logger.info(f"User {username} not found, creating new user...")
            user = User(
                username=username,
                nickname=username,
                email=f"{username}@placeholder.com"
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)

        user_id = user.id
        logger.info(f"--- Syncing for User ID: {user_id} ---")

        sync_count = 0
        items = DBFile

        if not isinstance(items, list):
            logger.error(f"ERROR: Expected list but got {type(items)}")
            return 0

        if not items:
            logger.info("No data to process.")
            return 0

        for item_origin in items:
            item = await convert_douban_to_bangumi(item_origin)

            if not isinstance(item, dict):
                continue

            try:
                subject_data = item.get("subject")
                if not subject_data:
                    logger.warning(f"收藏项缺少subject数据，跳过: {item}")
                    continue

                if subject_type is not None:
                    original_type = subject_data.get("type")
                    subject_data["type"] = subject_type
                    logger.info(f"API 参数强制覆盖类型: 条目 '{subject_data.get('name', '')}' 从类型 {original_type} 覆盖为 {subject_type}")

                current_subject = await upsert_subject(db, subject_data,source="douban")
                await _upsert_collection(db, user_id, current_subject.id, item)

                sync_count += 1
                type_name = SubjectType(current_subject.type).name if current_subject.type else "未知"
                logger.info(f"同步收藏: {current_subject.name} (ID: {current_subject.id}) [类型: {type_name}]")

            except SQLAlchemyError as e:
                logger.error(f"数据库操作失败: {e}")
                await db.rollback()
                continue
            except ValueError as e:
                logger.error(f"数据验证失败: {e}")
                await db.rollback()
                continue
            except Exception as e:
                logger.error(f"处理收藏项失败: {e}")
                await db.rollback()
                continue

        logger.info(f"成功同步 {sync_count} 条收藏记录")
        return sync_count

    except Exception as e:
        logger.error(f"同步用户收藏失败: {e}")
        await db.rollback()
        raise


async def convert_douban_to_bangumi(douban_item: Dict[str, Any]) -> Dict[str, Any]:
    """
    将豆瓣数据转换为 Bangumi 收藏格式

    Args:
        douban_item: 豆瓣收藏项（字典格式）

    Returns:
        Bangumi 收藏格式的 JSON 数据
    """
    status_map = {
        "mark": 1,
        "done": 2,
        "doing": 3,
    }

    subject_type_map = {
        "book": 1,
        "movie": 6,
        "tv": 6,
        "music": 3,
        "game": 4
    }

    db_status = douban_item.get("status", "")
    bgm_type = status_map.get(db_status, 2)

    db_subject_type = douban_item.get("type", "")
    bgm_subject_type = subject_type_map.get(db_subject_type, 1)

    if db_subject_type not in subject_type_map:
        logger.warning(f"无法识别的豆瓣类型: '{db_subject_type}'，使用默认值 1 (书籍)")

    db_interest = douban_item.get("interest", {})
    db_subject = db_interest.get("subject", {})

    pic = db_subject.get("pic", {})
    large_url = pic.get("large", "")
    normal_url = pic.get("normal", "")
    small_url = pic.get("small", "")
    medium_url = pic.get("medium", "")
    grid_url = pic.get("grid", "")
    
    cover_url = large_url or normal_url or ""

    rating = db_interest.get("rating", {})
    rate = rating.get("value", 0) if rating else 0

    db_tags = db_subject.get("genres", [])
    bangumi_tags = []
    for tag in db_tags:
        if isinstance(tag, str):
            bangumi_tags.append({
                "name": tag,
                "count": 0,
                "total_cont": 0
            })
        elif isinstance(tag, dict):
            bangumi_tags.append({
                "name": tag.get("name", ""),
                "count": tag.get("count", 0),
                "total_cont": tag.get("total_cont", 0)
            })


    bangumi_data = {
        "updated_at": db_interest.get("create_time", ""),
        "comment": db_interest.get("comment", "") or None,
        "tags": db_interest.get("tags", []),
        "subject": {
            "date": db_subject.get("pubdate", [""])[0],
            "images": {
                "large": large_url,
                "common": normal_url,
                "medium": medium_url,
                "small": small_url,
                "grid": grid_url
            },
            "name": db_subject.get("title", ""),
            "name_cn": db_subject.get("title", ""),
            "short_summary": db_subject.get("intro", ""),
            "tags": bangumi_tags,
            "score": db_subject.get("rating", {}).get("value", 0),
            "id": int(db_subject.get("id", 0)),
            "type": bgm_subject_type,
            "eps": 0,
            "volumes": 0,
            "collection_total": 0,
            "rank": 0
        },
        "subject_id": int(db_subject.get("id", 0)),
        "vol_status": 0,
        "ep_status": 0,
        "subject_type": bgm_subject_type,
        "type": bgm_type,
        "rate": rate*2,
        "private": db_interest.get("is_private", False)
    }

    return bangumi_data
