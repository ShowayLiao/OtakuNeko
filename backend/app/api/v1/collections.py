from fastapi import APIRouter, Depends, HTTPException, Path, Query
from typing import Optional, List, Dict, Any
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_session
from app.services.collection_service import get_my_collections, update_collection
from app.services.bangumi_service import sync_user_collections
from app.schemas.collection import CollectionUpdate, CollectionOut
from app.models.user import User
from app.models.subject import Subject
from app.models.collection import Collection
import httpx

# 缓存相关导入
from fastapi_cache.decorator import cache
from fastapi_cache import FastAPICache

router = APIRouter(prefix="/collections", tags=["Collections"])


@router.get("/", response_model=List[Dict[str, Any]])
@cache(expire=60)  # 添加缓存装饰器，过期时间为60秒
async def get_my_collections_endpoint(
    status: Optional[int] = Query(None, description="收藏状态 (1=想看/2=看过/3=在看/4=搁置/5=抛弃)"),
    type: Optional[int] = Query(None, description="条目类型 (1=书籍/2=动画/3=音乐/4=游戏/6=三次元)"),
    keyword: Optional[str] = Query(None, description="搜索关键词"),
    sort_by: str = Query("updated_at", description="排序字段 (updated_at 或 rate)"),
    db: AsyncSession = Depends(get_session)
):
    """
    获取用户的收藏列表，支持多种筛选和排序
    
    Args:
        status: 收藏状态 (可选)
        type: 条目类型 (可选)
        keyword: 搜索关键词 (可选)
        sort_by: 排序字段 ("updated_at" 或 "rate")
    
    Returns:
        包含 Subject 信息的聚合对象列表
    """
    # 这里应该从认证中间件获取用户ID
    # 暂时硬编码为 1，实际项目中应该替换为真实的用户ID获取逻辑
    user_id = 1
    
    collections = await get_my_collections(
        db, user_id, status, type, keyword, sort_by
    )
    return collections


@router.patch("/{subject_id}", response_model=CollectionOut)
async def update_collection_endpoint(
    subject_id: int = Path(..., description="条目ID"),
    update_data: CollectionUpdate = ...,
    db: AsyncSession = Depends(get_session)
):
    """
    更新用户的收藏信息
    
    Args:
        subject_id: 条目ID
        update_data: 更新数据
    
    Returns:
        更新后的 Collection 对象
    """
    # 这里应该从认证中间件获取用户ID
    # 暂时硬编码为 1，实际项目中应该替换为真实的用户ID获取逻辑
    user_id = 1
    
    updated_collection = await update_collection(
        db, user_id, subject_id, update_data
    )
    
    if not updated_collection:
        raise HTTPException(
            status_code=404,
            detail=f"收藏记录不存在 (user_id: {user_id}, subject_id: {subject_id})"
        )
    
    # 清除缓存，防止数据不一致
    try:
        await FastAPICache.clear()
    except Exception as e:
        # 缓存清除失败时，记录日志但不影响正常业务流程
        import logging
        logging.error(f"Failed to clear cache: {e}")
    
    return updated_collection


@router.post("/sync")
async def sync_user_collections_endpoint(
    username: str = Query(..., description="Bangumi 用户名"),
    subject_type: Optional[int] = Query(None, description="条目类型 (1=书籍/2=动画/3=音乐/4=游戏/6=三次元)"),
    db: AsyncSession = Depends(get_session)
):
    """
    同步指定用户的 Bangumi 收藏数据到本地数据库
    
    Args:
        username: Bangumi 用户名
        subject_type: 可选，条目类型
        db: 数据库会话
        
    Returns:
        同步结果
    """
    try:
        # 调用服务层同步数据
        sync_count = await sync_user_collections(username, db, subject_type)
        
        return {
            "message": f"Successfully synced {sync_count} collections for user {username}",
            "username": username,
            "sync_count": sync_count,
            "subject_type": subject_type
        }
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"User '{username}' not found")
        raise HTTPException(status_code=500, detail=f"Bangumi API error: {str(e)}")
    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail=f"Network error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


@router.get("/count")
async def get_user_collection_count(
    username: str,
    subject_type: int,
    db: AsyncSession = Depends(get_session)
):
    """
    获取指定用户、指定类型条目的收藏数量
    
    Args:
        username: Bangumi 用户名
        subject_type: 条目类型 (1=书籍/2=动画/3=音乐/4=游戏/6=三次元)
        db: 数据库会话
        
    Returns:
        包含收藏数量、用户名和条目类型的字典
    """
    # 1. 查 User ID
    user_res = await db.execute(select(User).where(User.username == username))
    user = user_res.scalars().first()
    if not user:
        return {"count": 0, "subject_type": subject_type, "username": username}

    # 2. 连表查询统计 (Collection Join Subject)
    # 逻辑: 统计 Collection 表，但条件限制在 Subject 表的 type 上
    from app.models.enums import SubjectType
    
    statement = (
        select(func.count())
        .select_from(Collection)
        .join(Subject, Collection.subject_id == Subject.id) # 显式连接
        .where(Collection.user_id == user.id)
        .where(Subject.type == SubjectType(subject_type)) # 使用枚举类型过滤
        # 可选: 如果只想统计 "看过/Collection" 的状态，可以加 .where(Collection.type == 2)
    )
    
    result = await db.execute(statement)
    count = result.scalar_one()
    
    return {"count": count, "subject_type": subject_type, "username": username}