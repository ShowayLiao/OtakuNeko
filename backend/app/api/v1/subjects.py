from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_session
from app.services.subject_service import search_subjects, search_mixed
from app.services.anime_service import sync_subject_detail
from app.services.bangumi_service import upsert_subject
from app.models import Subject
import httpx

# 缓存相关导入
from fastapi_cache.decorator import cache

router = APIRouter(prefix="/subjects", tags=["Subjects"])

# Bangumi 官方 API 配置
BANGUMI_API_BASE = "https://api.bgm.tv"


@router.post("/search-bangumi")
@cache(expire=60)  # 添加缓存装饰器，过期时间为60秒
async def search_bangumi_subjects(
    keyword: Optional[str] = Query(None, description="搜索关键词"),
    type: Optional[int] = Query(None, description="条目类型 (1=书籍/2=动画/3=音乐/4=游戏/6=三次元)"),
    limit: int = Query(20, ge=1, le=100, description="返回结果数量"),
    offset: int = Query(0, ge=0, description="结果偏移量"),
    sort: str = Query("rank", description="排序方式 (rank/score/date)")
):
    """
    从 Bangumi 官方 API 搜索条目
    
    Args:
        keyword: 搜索关键词 (可选)
        type: 条目类型 (1=书籍/2=动画/3=音乐/4=游戏/6=三次元) (可选)
        limit: 返回结果数量限制
        offset: 结果偏移量
        sort: 排序方式
    
    Returns:
        Bangumi API 返回的原始 JSON 数据
    """
    try:
        # 构造请求体
        request_body = {
            "keyword": keyword or "",
            "sort": sort,
            "filter": {}
        }
        
        # 添加类型过滤
        if type is not None:
            request_body["filter"]["type"] = [type]
        
        # 发送请求到 Bangumi 官方 API
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
            
            # 返回原始 JSON 数据
            return response.json()
            
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Bangumi API timeout")
    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail=f"Network error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Search failed: {str(e)}")


@router.get("/", response_model=List[Subject])
@cache(expire=60)  # 添加缓存装饰器，过期时间为60秒
async def search_subjects_endpoint(
    keyword: Optional[str] = Query(None, description="搜索关键词"),
    type: Optional[int] = Query(None, description="条目类型 (1=书籍/2=动画/3=音乐/4=游戏/6=三次元)"),
    limit: int = Query(20, ge=1, le=100, description="返回结果数量"),
    offset: int = Query(0, ge=0, description="结果偏移量"),
    db: AsyncSession = Depends(get_session)
):
    """
    在本地数据库的所有 Subject 中搜索
    
    Args:
        keyword: 搜索关键词 (可选)
        type: 条目类型 (1=书籍/2=动画/3=音乐/4=游戏/6=三次元) (可选)
        limit: 返回结果数量限制
        offset: 结果偏移量
    
    Returns:
        Subject 列表
    """
    subjects = await search_subjects(db, keyword, type, limit, offset)
    return subjects


@router.get("/search/mixed")
@cache(expire=60)  # 添加缓存装饰器，过期时间为60秒
async def search_mixed_endpoint(
    keyword: str = Query(..., description="搜索关键词"),
    type: Optional[int] = Query(None, description="条目类型 (1=书籍/2=动画/3=音乐/4=游戏/6=三次元)"),
    username: Optional[str] = Query(None, description="用户名，用于查询收藏状态"),
    limit: int = Query(20, ge=1, le=100, description="返回结果数量"),
    offset: int = Query(0, ge=0, description="结果偏移量"),
    db: AsyncSession = Depends(get_session)
):
    """
    混合搜索：本地优先，远程回退，返回带用户收藏状态的搜索结果
    
    实现策略：
    1. Step 1 (Local): 使用 SQL LIKE 查询本地 Subject 表，同时查询用户收藏状态
    2. Step 2 (Remote Check): 如果本地结果数量为 0，则调用 Bangumi API
    3. Step 3 (Adaptation): 如果数据来自 Remote，使用适配器模式转换为统一格式，但不入库
    
    Args:
        keyword: 搜索关键词 (必填)
        type: 条目类型 (1=书籍/2=动画/3=音乐/4=游戏/6=三次元) (可选)
        username: 用户名，用于查询收藏状态 (可选)
        limit: 返回结果数量限制
        offset: 结果偏移量
        db: 数据库会话
    
    Returns:
        {
            "data": List[Dict],  # 统一格式的条目数据 (SubjectWithUserStatus)
            "source": "local" | "remote",  # 数据来源
            "total": int  # 总数
        }
    """
    from app.models import User
    from sqlmodel import select
    
    # 获取用户ID
    user_id = None
    if username:
        user_result = await db.execute(select(User).where(User.username == username))
        user = user_result.scalars().first()
        if user:
            user_id = user.id
    
    result = await search_mixed(db, keyword, type, user_id, limit, offset)
    return result


@router.get("/{subject_id}", response_model=Subject)
async def get_subject(
    subject_id: int,
    db: AsyncSession = Depends(get_session)
):
    """
    根据ID获取单个条目的详细信息
    
    Args:
        subject_id: 条目ID
        db: 数据库会话
        
    Returns:
        Subject 对象
        
    Raises:
        HTTPException: 当条目不存在时返回404
    """
    from app.models.subject import Subject
    
    subject = await db.get(Subject, subject_id)
    if not subject:
        raise HTTPException(status_code=404, detail="Subject not found")
    return subject


@router.post("/ingest")
async def ingest_subject_data(
    bangumi_data: Dict, 
    db: AsyncSession = Depends(get_session)
):
    """
    接收 Bangumi 的原始 JSON 数据并保存到数据库
    
    Args:
        bangumi_data: Bangumi API 返回的原始 JSON 数据
        db: 数据库会话
        
    Returns:
        保存成功的条目信息
    """
    try:
        # 验证必要字段
        if not bangumi_data.get("id") or not bangumi_data.get("name"):
            raise HTTPException(status_code=400, detail="Missing required fields: id or name")
        
        # 调用服务保存数据
        subject = await upsert_subject(db, bangumi_data)
        
        return {
            "message": "Subject data saved successfully",
            "data": subject.model_dump()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save subject data: {str(e)}")


@router.get("/sync/{bgm_id}")
async def sync_subject_detail_endpoint(
    bgm_id: int,
    db: AsyncSession = Depends(get_session)
):
    """
    同步单个条目的详细信息
    
    Args:
        bgm_id: Bangumi 条目 ID
        db: 数据库会话
        
    Returns:
        同步结果
    """
    try:
        # 调用服务层同步数据
        subject = await sync_subject_detail(bgm_id, db)
        
        return {
            "message": f"Successfully synced subject {bgm_id}",
            "data": subject.model_dump()
        }
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Subject {bgm_id} not found")
        raise HTTPException(status_code=500, detail=f"Bangumi API error: {str(e)}")
    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail=f"Network error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")
