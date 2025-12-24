from typing import Optional, List, Dict
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import SQLAlchemyError
from datetime import datetime
import logging
from app.models import Subject, Collection, CollectionStatus, SubjectType
from app.services.bangumi_client import fetch_user_collections, fetch_subject_detail
from app.services.bangumi_service import upsert_subject

# 配置日志
logger = logging.getLogger(__name__)


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
        # 获取用户收藏数据
        response_json = await fetch_user_collections(username, subject_type)
        sync_count = 0
        
        # 提取真正的列表
        collections = response_json.get("data", [])
        
        # 增加安全检查
        if not isinstance(collections, list):
            logger.error(f"ERROR: Expected list but got {type(collections)}")
            return sync_count
        
        # 遍历收藏数据
        for collection in collections:
            # 确保item是字典
            if not isinstance(collection, dict):
                continue
            try:
                # 开始事务
                async with db.begin_nested():
                    # 提取条目基本信息
                    subject_data = collection.get("subject", {})
                    
                    # 保存/更新条目信息
                    subject = await upsert_subject(db, subject_data)
                    
                    # 提取收藏元数据
                    rate = collection.get("rate")
                    collection_type = collection.get("type")
                    updated_at_str = collection.get("updated_at")
                    private = collection.get("private", False)
                    
                    # 转换更新时间字符串为 datetime 对象
                    updated_at = datetime.fromisoformat(updated_at_str.replace("Z", "+00:00"))
                    
                    # 验证收藏状态
                    try:
                        collection_status = CollectionStatus(collection_type) if collection_type else None
                    except ValueError:
                        logger.warning(f"未知的收藏状态: {collection_type}，将跳过该收藏项")
                        continue
                    
                    # 创建或更新收藏信息
                    collection_data = {
                        "subject_id": subject.id,
                        "type": collection_status,
                        "rate": rate,
                        "updated_at": updated_at,
                        "private": private
                    }
                    
                    # 查询是否已存在收藏记录
                    stmt = select(Collection).where(Collection.subject_id == subject.id)
                    result = await db.execute(stmt)
                    existing_collection = result.scalar_one_or_none()
                    
                    if existing_collection:
                        # 更新现有记录
                        for field, value in collection_data.items():
                            setattr(existing_collection, field, value)
                        db.add(existing_collection)
                    else:
                        # 创建新记录
                        new_collection = Collection(**collection_data)
                        db.add(new_collection)
                    
                    sync_count += 1
                    logger.info(f"同步收藏: {subject.name} (ID: {subject.id}) [类型: {SubjectType(subject.type).name if subject.type else '未知'}]")
                    
            except SQLAlchemyError as e:
                logger.error(f"数据库操作失败: {e}")
                continue
            except Exception as e:
                logger.error(f"处理收藏项失败: {e}")
                continue
        
        # 提交事务
        await db.commit()
        
        logger.info(f"成功同步 {sync_count} 条收藏记录")
        return sync_count
        
    except Exception as e:
        logger.error(f"同步用户收藏失败: {e}")
        # 回滚事务
        await db.rollback()
        raise


async def sync_subject_detail(subject_id: int, db: AsyncSession) -> Subject:
    """
    同步单个条目的详细信息
    
    Args:
        subject_id: Bangumi 条目 ID
        db: 数据库会话
        
    Returns:
        创建或更新后的 Subject 对象
        
    Raises:
        Exception: 同步过程中发生错误时抛出
    """
    try:
        # 获取条目详细信息
        subject_data = await fetch_subject_detail(subject_id)
        
        # 保存/更新条目信息
        subject = await upsert_subject(db, subject_data)
        
        logger.info(f"同步条目详情: {subject.name} (ID: {subject.id})")
        return subject
        
    except Exception as e:
        logger.error(f"同步条目详情失败: {e}")
        raise
