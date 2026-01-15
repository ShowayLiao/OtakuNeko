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
                        
                    # 调用 SubjectRepo.save() 处理 Subject 入库
                    # 这个函数负责：查询 DB -> 不存在则 create -> 存在则 update -> session.commit()
                    current_subject = await SubjectRepo.save(db, subject_data)
                    
                    # --- 步骤 B: 再处理 Collection (只引用 ID) ---
                    # 此时我们只用 subject_id，不再传递整个 Subject 对象，彻底切断 ORM 写入时的纠缠
                    await CollectionRepo.save(db, user_id, current_subject.id, item)
                    
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
        
        logger.info(f"成功同步 {sync_count} 条收藏记录")
        
        # 清理用户统计数据缓存，确保首页统计数据即时刷新
        try:
            await FastAPICache.clear(key=f'dashboard:stats:{user_id}')
            logger.info(f"已清理用户 {user_id} 的统计数据缓存")
        except Exception as e:
            logger.warning(f"清理缓存失败: {e}")
        
        return sync_count
        
    except Exception as e:
        logger.error(f"同步用户收藏失败: {e}")
        # 回滚事务
        await db.rollback()
        raise


async def sync_subject_detail(subject_id: int, db: AsyncSession) -> Subject:
    """
    从 Bangumi API 同步单个条目的详细信息到本地数据库
    
    Args:
        subject_id: Bangumi 条目 ID
        db: 数据库会话
        
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
    
    # 使用 SubjectRepo.save() 写入数据库
    subject = await SubjectRepo.save(db, adapted_data, source="bangumi", source_id=str(subject_id))
    
    return subject
