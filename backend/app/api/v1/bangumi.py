from fastapi import APIRouter, Depends, HTTPException
from app.services.bangumi_service import get_bangumi_user_info, get_bangumi_calendar
from app.schemas.user import BangumiUserInfo
from app.schemas.bangumi import BangumiCalendar

router = APIRouter(prefix="/bangumi", tags=["Bangumi"])


@router.get("/user/{username}", response_model=BangumiUserInfo)
async def get_bangumi_user_endpoint(username: str):
    """
    获取 Bangumi 用户信息
    
    Args:
        username: Bangumi 用户名
        
    Returns:
        Bangumi 用户信息
        
    Raises:
        HTTPException: 当获取用户信息失败时返回 500 错误
    """
    try:
        user_info = await get_bangumi_user_info(username)
        return user_info
        
    except Exception as e:
        import traceback
        print(f"[获取 Bangumi 用户信息] 错误: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"获取 Bangumi 用户信息失败: {str(e)}")


@router.get("/calendar", response_model=BangumiCalendar)
async def get_bangumi_calendar_endpoint():
    """
    获取 Bangumi 每日放送信息
    
    Returns:
        Bangumi 每日放送信息
        
    Raises:
        HTTPException: 当获取每日放送信息失败时返回 500 错误
    """
    try:
        calendar_info = await get_bangumi_calendar()
        # 直接返回 BangumiCalendar 对象
        return calendar_info
        
    except Exception as e:
        import traceback
        print(f"[获取 Bangumi 每日放送信息] 错误: {str(e)}")
        print(traceback.format_exc())
        raise HTTPException(status_code=500, detail=f"获取 Bangumi 每日放送信息失败: {str(e)}")
