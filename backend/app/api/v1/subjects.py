from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_session
from app.services.subject_service import search_subjects, search_mixed
from app.services.bangumi_service import sync_subject_detail
from app.schemas.adapters import adapt_bangumi_subject
from app.models import Subject
from app.schemas.subject import SubjectRead, SubjectUpdate, SubjectWithUserStatus
from app.api.deps import get_current_user
import httpx

from fastapi_cache.decorator import cache

router = APIRouter(prefix="/subjects", tags=["Subjects"])

BANGUMI_API_BASE = "https://api.bgm.tv"


@router.get("/", response_model=List[SubjectWithUserStatus])
@cache(expire=60)
async def search_subjects_endpoint(
    q: Optional[str] = Query(None, description="搜索关键词"),
    source: str = Query("mixed", description="搜索来源: local=仅本地, remote=仅远程, mixed=混合(本地优先)"),
    type: Optional[int] = Query(None, description="条目类型 (1=书籍/2=动画/3=音乐/4=游戏/6=三次元)"),
    current_user = Depends(get_current_user),
    limit: int = Query(20, ge=1, le=100, description="返回结果数量"),
    offset: int = Query(0, ge=0, description="结果偏移量"),
    sort: str = Query("rank", description="排序方式 (rank/score/date) (仅remote模式有效)"),
    db: AsyncSession = Depends(get_session)
):
    """
    统一搜索接口，支持本地、远程和混合搜索
    
    Args:
        q: 搜索关键词 (可选)
        source: 搜索来源
            - local: 仅在本地数据库搜索
            - remote: 仅调用 Bangumi API 搜索
            - mixed: 混合搜索，本地优先，远程回退
        type: 条目类型 (1=书籍/2=动画/3=音乐/4=游戏/6=三次元) (可选)
        current_user: 当前认证用户，用于查询收藏状态 (仅mixed模式有效)
        limit: 返回结果数量限制
        offset: 结果偏移量
        sort: 排序方式 (仅remote模式有效)
        db: 数据库会话
    
    Returns:
        统一格式的 SubjectRead 列表
    """
    if source == "local":
        subjects = await search_subjects(db, q, type, limit, offset)
        user_id = current_user.id if current_user else None
        
        # 对于本地搜索结果，查询用户收藏状态
        if user_id:
            # 获取用户收藏的条目ID列表
            collected_subjects = await db.execute(
                select(Collections.subject_id).where(Collections.user_id == user_id)
            )
            collected_ids = {item[0] for item in collected_subjects.all()}
            
            # 更新每个条目的收藏状态
            for subject in subjects:
                subject.is_collected = subject.id in collected_ids
                subject.is_favorited = subject.is_collected
        
        return subjects
    
    elif source == "remote":
        try:
            request_body = {
                "keyword": q or "",
                "sort": sort,
                "filter": {}
            }
            
            if type is not None:
                request_body["filter"]["type"] = [type]
            
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    f"{BANGUMI_API_BASE}/v0/search/subjects",
                    json=request_body,
                    headers={
                        "User-Agent": "OtakuNeko/1.0 (https://github.com/yourusername/OtakuNeko)"
                    }
                )
                
                if response.status_code != 200:
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=f"Bangumi API error: {response.text}"
                    )
                
                remote_data = response.json()
                
                adapted_subjects = []
                for item in remote_data.get("data", [])[:limit]:
                    adapted_data = adapt_bangumi_subject(item)
                    # 远程搜索结果默认未收藏
                    adapted_subject = SubjectWithUserStatus(**adapted_data)
                    adapted_subject.is_collected = False
                    adapted_subject.is_favorited = False
                    adapted_subjects.append(adapted_subject)
                
                return adapted_subjects
                
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="Bangumi API timeout")
        except httpx.RequestError as e:
            raise HTTPException(status_code=500, detail=f"Network error: {str(e)}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")
    
    elif source == "mixed":
        user_id = current_user.id if current_user else None
        
        result = await search_mixed(db, q, type, user_id, limit, offset)
        
        subjects = []
        for item in result.get("data", []):
            # 检查item是否有id字段，如果没有，跳过或添加默认值
            if "id" not in item:
                # 为远程搜索结果添加一个临时id
                item["id"] = 0
            
            subject = SubjectWithUserStatus(**item)
            # 确保is_favorited字段与is_collected字段保持一致
            subject.is_favorited = subject.is_collected
            subjects.append(subject)
        
        return subjects
    
    else:
        raise HTTPException(status_code=400, detail=f"Invalid source: {source}. Must be one of: local, remote, mixed")


@router.get("/{subject_id}", response_model=SubjectRead)
async def get_subject(
    subject_id: int,
    refresh: bool = Query(False, description="是否从远程刷新数据"),
    db: AsyncSession = Depends(get_session)
):
    """
    获取单个条目的详细信息
    
    如果 refresh=true，会从 Bangumi API 同步最新数据；
    否则仅返回本地数据库中的数据。
    
    Args:
        subject_id: 条目ID
        refresh: 是否从远程刷新数据 (默认为 false)
        db: 数据库会话
        
    Returns:
        SubjectRead 对象
        
    Raises:
        HTTPException: 当条目不存在或同步失败时返回错误
    """
    from app.models.subject import Subject
    
    if refresh:
        try:
            subject = await sync_subject_detail(subject_id, db)
            return SubjectRead.model_validate(subject)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                raise HTTPException(status_code=404, detail=f"Subject {subject_id} not found")
            raise HTTPException(status_code=500, detail=f"Bangumi API error: {str(e)}")
        except httpx.RequestError as e:
            raise HTTPException(status_code=500, detail=f"Network error: {str(e)}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")
    else:
        subject = await db.get(Subject, subject_id)
        if not subject:
            raise HTTPException(status_code=404, detail="Subject not found")
        return SubjectRead.model_validate(subject)


@router.put("/{subject_id}", response_model=SubjectRead)
async def update_subject(
    subject_id: int,
    data: SubjectUpdate,
    db: AsyncSession = Depends(get_session)
):
    """
    修改条目信息
    
    此接口保留用于未来错误修正功能，允许手动修正条目数据。
    
    Args:
        subject_id: 条目ID
        data: 要更新的字段
        db: 数据库会话
        
    Returns:
        更新后的 SubjectRead 对象
        
    Raises:
        HTTPException: 当条目不存在时返回404
    """
    from app.models.subject import Subject
    
    subject = await db.get(Subject, subject_id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(subject, field, value)
    
    await db.commit()
    await db.refresh(subject)
    
    return SubjectRead.model_validate(subject)
