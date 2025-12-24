from fastapi import APIRouter, Depends, HTTPException, Query
from typing import Optional, List, Dict
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_session
from app.services.subject_service import search_subjects
from app.services.anime_service import sync_subject_detail
from app.services.bangumi_service import upsert_subject
from app.models import Subject
import httpx

# 缓存相关导入
from fastapi_cache.decorator import cache

router = APIRouter(prefix="/subjects", tags=["Subjects"])


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


@router.post("/ingest")
async def ingest_subject_data(
    bgm_data: Dict, 
    db: AsyncSession = Depends(get_session)
):
    """
    接收 Bangumi 的原始 JSON 数据并保存到数据库
    
    Args:
        bgm_data: Bangumi API 返回的原始 JSON 数据
        db: 数据库会话
        
    Returns:
        保存成功的条目信息
    """
    try:
        # 验证必要字段
        if not bgm_data.get("id") or not bgm_data.get("name"):
            raise HTTPException(status_code=400, detail="Missing required fields: id or name")
        
        # 调用服务保存数据
        subject = await upsert_subject(db, bgm_data)
        
        return {
            "message": "Subject data saved successfully",
            "data": subject.model_dump()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save subject data: {str(e)}")


@router.get("/sync/{subject_id}")
async def sync_subject_detail_endpoint(
    subject_id: int,
    db: AsyncSession = Depends(get_session)
):
    """
    同步单个条目的详细信息
    
    Args:
        subject_id: Bangumi 条目 ID
        db: 数据库会话
        
    Returns:
        同步结果
    """
    try:
        # 调用服务层同步数据
        subject = await sync_subject_detail(subject_id, db)
        
        return {
            "message": f"Successfully synced subject {subject_id}",
            "data": subject.model_dump()
        }
    except httpx.HTTPStatusError as e:
        if e.response.status_code == 404:
            raise HTTPException(status_code=404, detail=f"Subject {subject_id} not found")
        raise HTTPException(status_code=500, detail=f"Bangumi API error: {str(e)}")
    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail=f"Network error: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")
