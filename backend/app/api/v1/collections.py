from fastapi import APIRouter, Depends, HTTPException, Path, Query
from typing import Optional, List
from datetime import datetime
import logging
import json
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_session
from app.services.collection_service import get_user_collections, update_collection, upsert_collection, get_collection, delete_collection, batch_upsert_collections
from app.services.bangumi_service import sync_user_collections
from app.services.douban_service import sync_user_collections_douban
from app.schemas.collection import CollectionRead, CollectionList, CollectionSyncRequest, CollectionUpsertRequest, CollectionSearchByName, CollectionUpdate, CollectionSearchBase
from app.schemas.adaptersV2 import UnifiedList
from app.models.user import User
from app.models.subject import Subject
from app.models.collection import Collection
from app.api.deps import get_current_user
from app.repositories import CollectionRepo, SubjectRepo
import httpx

from app.core.logging import get_logger

logger = get_logger(__name__)

from fastapi_cache.decorator import cache
from fastapi_cache import FastAPICache

router = APIRouter(prefix="/collections", tags=["Collections"])


@router.get("/", response_model=UnifiedList)
@cache(expire=60)
async def get_user_collect(
    current_user = Depends(get_current_user),
    subject_type: Optional[int] = Query(None, description="条目类型 (1=书籍/2=动画/3=音乐/4=游戏/6=三次元)"),
    status: Optional[int] = Query(None, description="收藏状态 (1=想看/2=看过/3在看/4搁置/5抛弃)"),
    keyword: Optional[str] = Query(None, description="搜索关键词"),
    limit: int = Query(20, description="分页大小，默认 20"),
    offset: int = Query(0, description="分页偏移，默认 0"),
    sort_by: str = Query("updated_at", description="排序字段 (updated_at, rate, score, rank, date)"),
    db: AsyncSession = Depends(get_session)
):
    """
    获取用户的收藏列表，支持多种筛选和排序
    
    Args:
        current_user: 当前认证用户
        subject_type: 条目类型 (可选)
        status: 收藏状态 (可选)
        keyword: 搜索关键词 (可选)
        limit: 分页大小
        offset: 分页偏移
        sort_by: 排序字段
    
    Returns:
        统一视图模型列表
    """
    from app.models.enums import CollectionStatus
    from app.services.collection_service import get_user_collections, search_collections
    
    status_enum = CollectionStatus(status) if status is not None else None
    
    # 根据keyword是否存在使用不同的搜索方法
    if keyword:
        # 有关键词，使用search_collections
        search_data = CollectionSearchByName(
            user_id=current_user.id,
            status=status_enum,
            type=subject_type,
            keyword=keyword,
            sort_by=sort_by,
            limit=limit,
            skip=offset
        )
        # 调用search_collections进行关键词搜索
        collections_data = await search_collections(db, search_data)
    else:
        # 无关键词，使用get_user_collections
        search_data = CollectionSearchBase(
            user_id=current_user.id,
            status=status_enum,
            type=subject_type,
            limit=limit,
            skip=offset,
            sort_by=sort_by
        )
        # 调用get_user_collections获取收藏列表
        collections_data = await get_user_collections(db, search_data)
    
    return collections_data


@router.post("/", response_model=CollectionRead)
async def create_collection(
    sid: Optional[int] = Query(None, description="条目ID，提供则更新，不提供则创建"),
    data: CollectionUpsertRequest = ...,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """
    创建新收藏
    
    统一的收藏操作接口：
    - 当提供sid查询参数时：更新现有收藏（使用 data.collection 字段）
    - 当不提供sid查询参数时：创建新收藏（需要提供 data.subject 字段）
    - 如果提供sid但收藏不存在，则创建新收藏
    
    Args:
        sid: 条目ID，可选，查询参数，提供则更新，不提供则创建
        data: 收藏更新/添加数据
        current_user: 当前认证用户
        db: 数据库会话
    
    Returns:
        更新或创建后的 Collection 对象
    """
    try:
        # 调用Service层处理业务逻辑
        collection = await upsert_collection(db, current_user.id, sid, data)
        
        # 清除缓存，防止数据不一致
        try:
            await FastAPICache.clear()
        except Exception as e:
            import logging
            logging.error(f"Failed to clear cache: {e}")
        
        # 调用get_collection获取完整的CollectionRead对象
        from app.schemas.collection import CollectionSearchByID
        search_data = CollectionSearchByID(
            user_id=current_user.id,
            source=collection.source,
            source_id=collection.source_id
        )
        collection_read = await get_collection(db, search_data)
        
        return collection_read
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        import traceback
        print(f"[收藏更新/添加] 错误: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to create collection: {str(e)}")


@router.get("/{source}/{source_id}", response_model=CollectionRead)
async def get_collection_endpoint(
    source: str = Path(..., description="数据来源"),
    source_id: str = Path(..., description="原站ID"),
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """
    获取单个收藏
    
    Args:
        source: 数据来源
        source_id: 原站ID
        current_user: 当前认证用户
        db: 数据库会话
    
    Returns:
        收藏对象
    """
    try:
        from app.schemas.collection import CollectionSearchByID
        search_data = CollectionSearchByID(
            user_id=current_user.id,
            source=source,
            source_id=source_id
        )
        collection_read = await get_collection(db, search_data)
        if not collection_read:
            raise HTTPException(status_code=404, detail="Collection not found")
        return collection_read
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        import traceback
        print(f"[获取收藏] 错误: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to get collection: {str(e)}")


@router.put("/{source}/{source_id}", response_model=CollectionRead)
async def update_collection_endpoint(
    source: str = Path(..., description="数据来源"),
    source_id: str = Path(..., description="原站ID"),
    data: CollectionUpdate = ...,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """
    更新收藏
    
    Args:
        source: 数据来源
        source_id: 原站ID
        data: 收藏更新数据
        current_user: 当前认证用户
        db: 数据库会话
    
    Returns:
        更新后的收藏对象
    """
    try:
        # 设置source和source_id
        data.source = source
        data.source_id = source_id
        data.user_id = current_user.id
        
        # 调用Service层处理业务逻辑
        collection = await update_collection(db, data)
        if not collection:
            raise HTTPException(status_code=404, detail="Collection not found")
        
        # 清除缓存，防止数据不一致
        try:
            await FastAPICache.clear()
        except Exception as e:
            import logging
            logging.error(f"Failed to clear cache: {e}")
        
        # 调用get_collection获取完整的CollectionRead对象
        from app.schemas.collection import CollectionSearchByID
        search_data = CollectionSearchByID(
            user_id=current_user.id,
            source=source,
            source_id=source_id
        )
        collection_read = await get_collection(db, search_data)
        
        return collection_read
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        import traceback
        print(f"[更新收藏] 错误: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to update collection: {str(e)}")


@router.delete("/{source}/{source_id}", response_model=dict)
async def delete_collection_endpoint(
    source: str = Path(..., description="数据来源"),
    source_id: str = Path(..., description="原站ID"),
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """
    删除收藏
    
    Args:
        source: 数据来源
        source_id: 原站ID
        current_user: 当前认证用户
        db: 数据库会话
    
    Returns:
        删除结果
    """
    try:
        from app.schemas.collection import CollectionSearchByID
        search_data = CollectionSearchByID(
            user_id=current_user.id,
            source=source,
            source_id=source_id
        )
        deleted = await delete_collection(db, search_data)
        if not deleted:
            raise HTTPException(status_code=404, detail="Collection not found")
        
        # 清除缓存，防止数据不一致
        try:
            await FastAPICache.clear()
        except Exception as e:
            import logging
            logging.error(f"Failed to clear cache: {e}")
        
        return {"status": "success", "message": f"Collection {source_id} deleted successfully"}
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        import traceback
        print(f"[删除收藏] 错误: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to delete collection: {str(e)}")


@router.post("/batch", response_model=dict)
async def batch_upsert_collections_endpoint(
    data: CollectionList = ...,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """
    批量创建/更新收藏
    
    Args:
        data: 收藏列表数据
        current_user: 当前认证用户
        db: 数据库会话
    
    Returns:
        批量操作结果
    """
    try:
        # 调用Service层处理业务逻辑
        success_count = await batch_upsert_collections(db, data, current_user.id)
        
        # 清除缓存，防止数据不一致
        try:
            await FastAPICache.clear()
        except Exception as e:
            import logging
            logging.error(f"Failed to clear cache: {e}")
        
        return {
            "status": "success",
            "message": f"Successfully upserted {success_count}/{data.total} collections",
            "success_count": success_count,
            "total_count": data.total
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        import traceback
        print(f"[批量更新收藏] 错误: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to batch upsert collections: {str(e)}")





@router.post("/sync/bgm")
async def sync_bgm(
    data: CollectionSyncRequest,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """
    同步用户的 Bangumi 收藏数据到本地数据库
    
    Args:
        data: 同步请求数据，包含 subject_type、limit、offset 等参数
        current_user: 当前认证用户
        db: 数据库会话
        
    Returns:
        同步结果
    """
    try:
        # 使用'hacci'作为Bangumi用户名进行同步
        sync_count = await sync_user_collections(current_user, db, data)
        
        return {
            "message": f"Successfully synced {sync_count} collections for user {current_user.username}",
            "username": current_user.username,
            "sync_count": sync_count,
            "import_count": sync_count,
            "subject_type": data.subject_type,
            "source": "bgm"
        }
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"User '{current_user.username}' not found")
        raise HTTPException(status_code=500, detail=f"Bangumi API error: {str(e)}")
    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail=f"Network error: {str(e)}")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Data validation failed: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


@router.post("/upload/douban")
async def upload_douban(
    data: dict,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """
    上传用户的豆瓣收藏数据到本地数据库
    
    Args:
        data: 包含豆瓣数据列表的字典，格式为 { "data": [...] }
        current_user: 当前认证用户
        db: 数据库会话
        
    Returns:
        同步结果
    """
    try:
        logger.info(f"--- Starting Douban upload for user {current_user.username} (ID: {current_user.id}) ---)")
        
        # 提取豆瓣数据列表，兼容多种格式
        douban_data = []
        if 'data' in data:
            # 格式1: { "data": [...] }
            douban_data = data.get('data', [])
        elif 'interest' in data:
            # 格式2: { "interest": [...] } (直接上传的 JSON 文件格式)
            douban_data = data.get('interest', [])
        else:
            # 格式3: [...] (直接的列表格式)
            if isinstance(data, list):
                douban_data = data
        
        if not douban_data:
            logger.warning(f"User {current_user.username} attempted to upload empty Douban data")
            raise HTTPException(status_code=400, detail="Douban data is required")
        
        logger.info(f"Received {len(douban_data)} Douban items for upload")
        
        # 直接调用豆瓣数据同步函数，传递 JSON 数据
        logger.info("Calling sync_user_collections_douban function")
        import_count = await sync_user_collections_douban(current_user.id, db, douban_data)
        logger.info(f"sync_user_collections_douban completed successfully, imported {import_count} items")
        
        logger.info(f"--- Douban upload completed successfully for user {current_user.username}, imported {import_count} items ---)")
        
        return {
            "message": f"Successfully imported {import_count} Douban items for user {current_user.username}",
            "username": current_user.username,
            "sync_count": import_count,
            "import_count": import_count,
            "subject_type": data.get('subject_type'),
            "source": "douban"
        }
    except json.JSONDecodeError as e:
        logger.error(f"JSON decode error during Douban upload: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Invalid JSON data: {str(e)}")
    except ValueError as e:
        logger.error(f"Value error during Douban upload: {str(e)}")
        raise HTTPException(status_code=400, detail=f"Data validation failed: {str(e)}")
    except Exception as e:
        logger.error(f"Unexpected error during Douban upload: {str(e)}")
        import traceback
        logger.error(f"Error traceback: {traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=f"Upload failed: {str(e)}")


@router.post("/sync/manual")
async def sync_manual(
    data: CollectionSyncRequest,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """
    手动批量导入收藏数据
    
    Args:
        data: 同步请求数据，包含 data 字段（手动导入数据列表）
        current_user: 当前认证用户
        db: 数据库会话
        
    Returns:
        同步结果
    """
    try:
        if not data.data:
            raise HTTPException(status_code=400, detail="Data is required when source is 'manual'")
        
        from app.services.collection_service import import_json_collections
        
        # 包装数据为 import_json_collections 函数期望的格式
        json_data = {
            "data": data.data
        }
        
        user_id = current_user.id
        
        # 调用 import_json_collections 函数处理导入
        sync_count = await import_json_collections(db, json_data, user_id)
        
        return {
            "message": f"Successfully imported {sync_count} items manually for user {current_user.username}",
            "username": current_user.username,
            "sync_count": sync_count,
            "subject_type": data.subject_type,
            "source": "manual"
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"Data validation failed: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Manual sync failed: {str(e)}")


