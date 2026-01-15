from fastapi import APIRouter, Depends, HTTPException, Path, Query
from typing import Optional, List
from datetime import datetime
import logging
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_session
from app.services.collection_service import get_my_collections, update_collection, upsert_collection
from app.services.bangumi_service import sync_user_collections
from app.services.douban_importer import sync_user_collections_db
from app.schemas.collection import CollectionRead, CollectionList, CollectionSyncRequest, CollectionUpsertRequest
from app.models.user import User
from app.models.subject import Subject
from app.models.collection import Collection
from app.api.deps import get_current_user
from app.repositories import CollectionRepo, SubjectRepo
import httpx

from fastapi_cache.decorator import cache
from fastapi_cache import FastAPICache

router = APIRouter(prefix="/collections", tags=["Collections"])


@router.get("/", response_model=CollectionList)
@cache(expire=60)
async def get_my_collections_endpoint(
    current_user = Depends(get_current_user),
    subject_type: Optional[int] = Query(None, description="条目类型 (1=书籍/2=动画/3=音乐/4=游戏/6=三次元)"),
    status: Optional[int] = Query(None, description="收藏状态 (1=想看/2=看过/3=在看/4=搁置/5=抛弃)"),
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
        包含 Subject 信息的聚合对象列表
    """
    from app.models.enums import CollectionStatus
    
    status_enum = CollectionStatus(status) if status is not None else None
    
    collections_data = await get_my_collections(
        db, current_user.id, status_enum, subject_type, keyword, sort_by, limit, offset
    )
    
    # 转换为符合响应模型的格式
    items = []
    for item in collections_data["items"]:
        collection = item["collection"]
        subject = item["subject"]
        
        # 转换为 CollectionRead 格式
        collection_item = {
            "subject_id": collection.subject_id,
            "updated_at": collection.updated_at,
            "status": collection.type,
            "rate": collection.rate,
            "comment": collection.comment,
            "private": collection.private,
            "tags": collection.tags or [],
            "subject": subject
        }
        items.append(collection_item)
    
    return {
        "total": collections_data["total"],
        "items": items
    }


@router.post("/", response_model=CollectionRead)
async def upsert_collection_endpoint(
    sid: Optional[int] = Query(None, description="条目ID，提供则更新，不提供则创建"),
    data: CollectionUpsertRequest = ...,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """
    更新或添加收藏
    
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
        
        return {
            "subject_id": collection.subject_id,
            "updated_at": collection.updated_at,
            "status": collection.type,
            "rate": collection.rate,
            "comment": collection.comment,
            "private": collection.private,
            "tags": collection.tags or [],
            "subject": None
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        import traceback
        print(f"[收藏更新/添加] 错误: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"Failed to upsert collection: {str(e)}")





@router.post("/sync")
async def sync_collections_endpoint(
    data: CollectionSyncRequest,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """
    统一同步接口，支持 BGM 和 豆瓣两种数据源
    
    Args:
        data: 同步请求数据，包含 source、subject_type 和 data 字段
              - source: "bgm" 或 "douban"
              - subject_type: 可选的条目类型
              - data: 豆瓣数据列表 (仅当source=douban时需要)
        current_user: 当前认证用户
        db: 数据库会话
        
    Returns:
        同步结果
    """
    try:
        if data.source == "bgm":
            sync_count = await sync_user_collections(current_user.username, db, data.subject_type)
            
            return {
                "message": f"Successfully synced {sync_count} collections for user {current_user.username}",
                "username": current_user.username,
                "sync_count": sync_count,
                "import_count": sync_count,
                "subject_type": data.subject_type,
                "source": "bgm"
            }
        elif data.source == "douban":
            if not data.data:
                raise HTTPException(status_code=400, detail="Douban data is required when source is 'douban'")
            
            import_count = await sync_user_collections_db(current_user.username, db, data.data, data.subject_type)
            
            return {
                "message": f"Successfully imported {import_count} Douban items for user {current_user.username}",
                "username": current_user.username,
                "sync_count": import_count,
                "import_count": import_count,
                "subject_type": data.subject_type,
                "source": "douban"
            }
        elif data.source == "manual":
            # 处理手动批量导入
            if not data.data:
                raise HTTPException(status_code=400, detail="Data is required when source is 'manual'")
            
            from app.repositories import SubjectRepo
            
            sync_count = 0
            user_id = current_user.id
            
            for import_item in data.data:
                try:
                    # 提取subject数据和collection数据
                    subject_data = import_item.get("subject", {})
                    collection_data = import_item.get("collection", {})
                    
                    if not subject_data:
                        continue
                    
                    # 保存或更新Subject
                    subject = await SubjectRepo.save(db, subject_data, source="manual")
                    
                    # 准备collection数据，添加必要的字段
                    collection_data = {
                        **collection_data,
                        "updated_at": datetime.now().isoformat() + "Z",  # 添加当前时间
                        "type": collection_data.get("status", 2),  # 确保type字段存在（status是前端传递的字段名）
                        "subject_id": subject.id
                    }
                    
                    # 保存或更新Collection
                    await CollectionRepo.save(db, user_id, subject.id, collection_data)
                    
                    sync_count += 1
                    
                except Exception as e:
                    logging.error(f"处理手动导入项失败: {e}, 数据: {import_item}")
                    continue
            
            return {
                "message": f"Successfully imported {sync_count} items manually for user {current_user.username}",
                "username": current_user.username,
                "sync_count": sync_count,
                "subject_type": data.subject_type,
                "source": "manual"
            }
        else:
            raise HTTPException(status_code=400, detail=f"Invalid source: {data.source}. Must be 'bgm', 'douban' or 'manual'")
            
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


