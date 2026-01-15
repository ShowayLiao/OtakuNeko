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
            item = convert_douban_to_bangumi(item_origin)

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

                current_subject = await SubjectRepo.save(db, subject_data, source="douban")
                await CollectionRepo.save(db, user_id, current_subject.id, item)

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
