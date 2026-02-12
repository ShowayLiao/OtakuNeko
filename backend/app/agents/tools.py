from langchain_core.tools import tool
from app.services.bangumi_service import fetch_subject_by_id
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