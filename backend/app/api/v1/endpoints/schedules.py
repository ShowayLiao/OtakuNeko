from fastapi import APIRouter, Depends, HTTPException, Query, Path
from typing import List
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.database import get_session
from app.api.deps import get_current_user
from app.services.schedule_service import ScheduleService
from app.schemas.schedule import ScheduleRead, ScheduleCreate, ScheduleUpdate

router = APIRouter(prefix="/schedules", tags=["Schedules"])


@router.get("/", response_model=List[ScheduleRead])
async def get_user_schedules(
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """
    获取当前用户的所有排班记录
    
    Args:
        current_user: 当前认证用户
        db: 数据库会话
        
    Returns:
        当前用户的所有排班记录列表
        
    Raises:
        HTTPException: 当获取失败时返回错误
    """
    try:
        schedules = await ScheduleService.get_user_schedules(db, current_user.id)
        return schedules
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取排班记录失败: {str(e)}")


@router.get("/by-day/{day}", response_model=List[ScheduleRead])
async def get_schedules_by_day(
    day: int = Path(..., ge=0, le=6, description="星期几，0-6 (周日到周六)"),
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """
    获取当前用户指定星期的排班记录
    
    Args:
        day: 星期几，0-6 (周日到周六)
        current_user: 当前认证用户
        db: 数据库会话
        
    Returns:
        指定星期的排班记录列表
        
    Raises:
        HTTPException: 当获取失败时返回错误
    """
    try:
        schedules = await ScheduleService.get_schedules_by_day(db, current_user.id, day)
        return schedules
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取指定星期的排班记录失败: {str(e)}")


@router.post("/", response_model=ScheduleRead, status_code=201)
async def create_schedule(
    schedule_data: ScheduleCreate,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """
    为当前用户创建新的排班记录
    
    Args:
        schedule_data: 排班数据，使用 ScheduleCreate schema
        current_user: 当前认证用户
        db: 数据库会话
        
    Returns:
        创建的排班记录
        
    Raises:
        HTTPException: 当创建失败时返回错误
    """
    try:
        new_schedule = await ScheduleService.create_schedule(db, current_user.id, schedule_data)
        if not new_schedule:
            raise HTTPException(status_code=409, detail="排班记录已存在")
        return new_schedule
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"创建排班记录失败: {str(e)}")


@router.put("/{id}", response_model=ScheduleRead)
async def update_schedule(
    id: int,
    schedule_data: ScheduleUpdate,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """
    更新当前用户的排班记录
    
    Args:
        id: 排班ID
        schedule_data: 更新的排班数据，使用 ScheduleUpdate schema
        current_user: 当前认证用户
        db: 数据库会话
        
    Returns:
        更新后的排班记录
        
    Raises:
        HTTPException: 当更新失败或记录不存在时返回错误
    """
    try:
        updated_schedule = await ScheduleService.update_schedule(db, id, current_user.id, schedule_data)
        if not updated_schedule:
            raise HTTPException(status_code=404, detail="排班记录不存在或不属于当前用户")
        return updated_schedule
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"更新排班记录失败: {str(e)}")


@router.delete("/{id}", response_model=dict, status_code=200)
async def delete_schedule(
    id: int,
    current_user = Depends(get_current_user),
    db: AsyncSession = Depends(get_session)
):
    """
    删除当前用户的排班记录
    
    Args:
        id: 排班ID
        current_user: 当前认证用户
        db: 数据库会话
        
    Returns:
        删除结果，包含成功状态和消息
        
    Raises:
        HTTPException: 当删除失败或记录不存在时返回错误
    """
    try:
        deleted = await ScheduleService.delete_schedule(db, id, current_user.id)
        if not deleted:
            raise HTTPException(status_code=404, detail="排班记录不存在或不属于当前用户")
        return {"status": "success", "message": "排班记录删除成功"}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"删除排班记录失败: {str(e)}")
