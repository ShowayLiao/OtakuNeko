from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_session
from app.services.subject_service import (
    search_mixed, search_subject_by_name, search_subject_cloud,
    create_subject, delete_subject, update_subject as update_subject_service,
    get_subject_by_source
)
from app.services.bangumi_service import sync_subject_detail
from app.schemas.adapters import adapt_bangumi_subject
from app.models import Subject, Collection
from app.schemas.subject import (
    SubjectRead, SubjectUpdate, SubjectCreate, 
    SubjectSearchByName, SubjectSearchCloud, SubjectSearchBase,
    SubjectSearchByID
)
from app.schemas.collection import CollectionList, CollectionRead
from app.api.deps import get_current_user
import httpx

from fastapi_cache.decorator import cache

router = APIRouter(prefix="/subjects", tags=["Subjects"])

BANGUMI_API_BASE = "https://api.bgm.tv"


@router.get("/", response_model=CollectionList)
@cache(expire=60)
async def search_subjects_endpoint(
    q: Optional[str] = Query(None, description="搜索关键词"),
    type: Optional[int] = Query(None, description="条目类型 (1=书籍/2=动画/3=音乐/4=游戏/6=三次元)"),
    current_user = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=100, description="返回结果数量"),
    offset: int = Query(0, ge=0, description="结果偏移量"),
    db: AsyncSession = Depends(get_session)
):
    """
    统一搜索接口，使用混合搜索策略：本地优先，远程回退
    
    Args:
        q: 搜索关键词 (可选)
        type: 条目类型 (1=书籍/2=动画/3=音乐/4=游戏/6=三次元) (可选)
        current_user: 当前认证用户，用于查询收藏状态
        limit: 返回结果数量限制
        offset: 结果偏移量
        db: 数据库会话
    
    Returns:
        统一格式的 CollectionList 对象
    """
    user_id = current_user.id if current_user else None
    
    # 使用search_mixed函数进行混合搜索
    search_data = SubjectSearchBase(
        keyword=q or "",
        type=type,
        skip=offset,
        limit=limit,
        user_id=user_id
    )
    
    return await search_mixed(db, search_data)


@router.get("/{subject_id}", response_model=CollectionRead)
async def get_subject(
    subject_id: int,
    source: str = Query("bangumi", description="数据来源: bangumi/douban"),
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """
    根据数据源和ID获取单个条目的详细信息
    
    Args:
        subject_id: 条目ID
        source: 数据来源，默认为 "bangumi"
        current_user: 当前认证用户，用于查询收藏状态
        db: 数据库会话
        
    Returns:
        CollectionRead 对象，包含条目信息和收藏状态
        
    Raises:
        HTTPException: 当条目不存在时返回404错误
    """
    user_id = current_user.id if current_user else None
    
    # 使用get_subject_by_source函数获取条目
    search_data = SubjectSearchByID(
        source=source,
        source_id=str(subject_id),
        user_id=user_id
    )
    collection_read = await get_subject_by_source(db, search_data)
    if not collection_read:
        raise HTTPException(status_code=404, detail="Subject not found")
    return collection_read


@router.put("/{subject_id}", response_model=CollectionRead)
async def update_subject(
    subject_id: int,
    data: SubjectUpdate,
    source: str = Query("bangumi", description="数据来源: bangumi/douban"),
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """
    修改条目信息
    
    此接口用于手动修正条目数据。
    
    Args:
        subject_id: 条目ID
        data: 要更新的字段，使用SubjectUpdate schema
        source: 数据来源，默认为 "bangumi"
        current_user: 当前认证用户
        db: 数据库会话
        
    Returns:
        更新后的 CollectionRead 对象，包含条目信息和收藏状态
        
    Raises:
        HTTPException: 当条目不存在时返回404
    """
    # 设置source和source_id
    data.source = source
    data.source_id = str(subject_id)
    
    # 调用服务层的update_subject函数
    updated_subject = await update_subject_service(db, data)
    
    if not updated_subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    
    # 使用get_subject_by_source获取完整的CollectionRead对象
    user_id = current_user.id if current_user else None
    search_data = SubjectSearchByID(
        source=source,
        source_id=str(subject_id),
        user_id=user_id
    )
    collection_read = await get_subject_by_source(db, search_data)
    if not collection_read:
        raise HTTPException(status_code=404, detail="Subject not found after update")
    
    return collection_read


@router.post("/", response_model=CollectionRead)
async def create_subject_endpoint(
    data: SubjectCreate,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """
    创建新条目
    
    Args:
        data: 条目数据，使用SubjectCreate schema
        current_user: 当前认证用户
        db: 数据库会话
        
    Returns:
        创建后的 CollectionRead 对象，包含条目信息和收藏状态
        
    Raises:
        HTTPException: 当创建失败时返回错误
    """
    try:
        # 调用服务层的create_subject函数
        created_subject = await create_subject(db, data)
        
        # 转换为CollectionRead格式
        from app.schemas.adapters import adapt_to_collection_read
        collection_read = adapt_to_collection_read(created_subject)
        return collection_read
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建条目失败: {str(e)}")


@router.delete("/{subject_id}", response_model=dict)
async def delete_subject_endpoint(
    subject_id: int,
    source: str = Query("bangumi", description="数据来源: bangumi/douban"),
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """
    删除条目
    
    Args:
        subject_id: 条目ID
        source: 数据来源，默认为 "bangumi"
        current_user: 当前认证用户
        db: 数据库会话
        
    Returns:
        删除结果，包含成功状态和消息
        
    Raises:
        HTTPException: 当删除失败时返回错误
    """
    # 创建SubjectSearchByID对象
    search_data = SubjectSearchByID(
        source=source,
        source_id=str(subject_id)
    )
    
    # 调用服务层的delete_subject函数
    deleted = await delete_subject(db, search_data)
    
    if deleted:
        return {"status": "success", "message": f"条目 {subject_id} 删除成功"}
    else:
        raise HTTPException(status_code=404, detail=f"条目 {subject_id} 不存在")
