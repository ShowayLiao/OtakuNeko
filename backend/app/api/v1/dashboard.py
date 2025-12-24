from fastapi import APIRouter, Depends
from sqlmodel import select, SQLModel
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_session
from app.models.subject import Subject
from app.models.collection import Collection
from typing import List, Optional
from datetime import datetime
import logging

# 创建路由器
router = APIRouter(tags=["Dashboard"])


# 定义响应模型
class DashboardStatsResponse(SQLModel):
    total_subjects: int
    total_collections: int
    system_status: str
    recent_activity: List[dict]


@router.get("/dashboard/stats", response_model=DashboardStatsResponse)
async def get_dashboard_stats(session: AsyncSession = Depends(get_session)):
    """
    获取仪表盘统计数据
    """
    try:
        # 1. 统计Subject表的总数
        subject_result = await session.execute(select(Subject))
        total_subjects = len(subject_result.scalars().all())
        
        # 2. 统计Collection表的总数
        collection_result = await session.execute(select(Collection))
        total_collections = len(collection_result.scalars().all())
        
        # 3. 获取最近更新的5条Collection
        recent_collections_result = await session.execute(
            select(Collection).order_by(Collection.updated_at.desc()).limit(5)
        )
        recent_collections = recent_collections_result.scalars().all()
        
        # 构建recent_activity数据
        recent_activity = []
        for collection in recent_collections:
            # 查询关联的subject
            subject_result = await session.execute(select(Subject).where(Subject.id == collection.subject_id))
            subject = subject_result.scalars().first()
            
            if subject:
                recent_activity.append({
                    "id": f"{collection.user_id}-{collection.subject_id}",
                    "user_id": collection.user_id,
                    "subject_id": collection.subject_id,
                    "subject_name": subject.name_cn or subject.name,
                    "subject_type": subject.type.value,
                    "collection_type": collection.type.value,
                    "updated_at": collection.updated_at.isoformat()
                })
        
        # 4. 系统状态（这里简单返回"Pulsed"）
        system_status = "Pulsed"
        
        return DashboardStatsResponse(
            total_subjects=total_subjects,
            total_collections=total_collections,
            system_status=system_status,
            recent_activity=recent_activity
        )
    except Exception as e:
        logging.error(f"Error getting dashboard stats: {e}")
        # 返回默认值
        return DashboardStatsResponse(
            total_subjects=0,
            total_collections=0,
            system_status="Running",
            recent_activity=[]
        )
