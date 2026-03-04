from langchain_core.tools import tool
from app.services.bangumi_service import fetch_subject_by_id, get_audience_feedback, get_staff_info, get_cast_info
from app.schemas.bangumi import SubjectDetail

@tool
async def get_anime_info(subject_id: int) -> dict:
    """
    Get detailed information about an anime using its Bangumi ID.
    Returns summary, ratings, and CORE staff members (Director, Studio, Scriptwriter, etc.).
    
    Use this tool to analyze the production quality or background of an anime.
    """
    try:
        # 调用 Service
        result: SubjectDetail = await fetch_subject_by_id(subject_id)
        
        # 转成 dict 返回给 Agent
        # exclude_none=True 可以去掉那些空的字段，节省 Token
        return result.model_dump(exclude_none=True)
        
    except Exception as e:
        return {"error": f"Failed to fetch anime info: {str(e)}"}

@tool
async def fetch_audience_reviews(subject_id: int) -> dict:
    """
    获取 Bangumi 条目的观众评价（短评和长评）。
    返回观众的吐槽内容和长评摘要，用于分析动画口碑。
    
    Use this tool to analyze the audience feedback and口碑 of an anime.
    """
    try:
        # 调用 Service
        result = await get_audience_feedback(subject_id)
        
        # 转成 dict 返回给 Agent
        return result.model_dump(exclude_none=True)
        
    except Exception as e:
        return {"error": f"Failed to fetch audience reviews: {str(e)}"}

@tool
async def get_anime_staff(subject_id: int) -> dict:
    """
    获取 Bangumi 条目的制作人员信息。
    返回核心制作人员列表，包括监督、脚本、制作公司等。
    
    Use this tool to analyze the production team behind an anime.
    """
    try:
        # 调用 Service
        result = await get_staff_info(subject_id)
        
        # 转成 dict 返回给 Agent
        return {"staff": [staff.model_dump() for staff in result]}
        
    except Exception as e:
        return {"error": f"Failed to fetch anime staff: {str(e)}"}

@tool
async def get_anime_cast(subject_id: int) -> dict:
    """
    获取 Bangumi 条目的声优阵容信息。
    返回核心角色的配音演员列表。
    
    Use this tool to analyze the voice cast of an anime.
    """
    try:
        # 调用 Service
        result = await get_cast_info(subject_id)
        
        # 转成 dict 返回给 Agent
        return {"cast": [cast.model_dump() for cast in result]}
        
    except Exception as e:
        return {"error": f"Failed to fetch anime cast: {str(e)}"}