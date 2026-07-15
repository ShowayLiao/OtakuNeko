from typing import List, Dict, Any
from langchain_core.tools import tool
from app.services.user_profile_service import generate_user_profile
from app.agents.tools.base import log_tool_call


@tool
@log_tool_call("generate_user_profile_tool")
async def generate_user_profile_tool(collections: List[Dict[str, Any]]) -> dict:
    """
    生成用户画像的工具，基于用户的观看记录（收藏数据），通过「频次 + 平均分」的二维加权算法，
    生成高质量的用户画像，用于动画推荐和个性化分析。

    此工具分析用户的动画观看历史，提取用户的偏好标签、评分模式和行为特征，
    生成可用于个性化推荐和用户分析的画像数据。

    【使用场景】
    1. 当需要了解用户的动画偏好时
    2. 当需要为用户推荐个性化动画时
    3. 当需要分析用户的观看习惯和评分模式时
    4. 当需要生成用户画像用于推荐系统时

    【输入数据格式】
    输入应为用户收藏列表，每个收藏包含collection信息和关联的subject信息：
    [
        {
            "collection": {"rate": 8, "type": 2, ...},
            "subject": {"id": 12345, "name": "动画名称", "tags": [...], ...}
        },
        ...
    ]

    Args:
        collections: 用户收藏列表，每个元素应包含collection和subject信息

    Returns:
        包含三部分数据的用户画像字典
    """
    try:
        profile = generate_user_profile(collections)
        return {
            "success": True,
            "profile": profile,
            "summary": f"成功生成用户画像，分析了{profile.get('llm_summary', {}).get('total_rated', 0)}个有效评分"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"生成用户画像失败: {str(e)}",
            "profile": {
                "llm_summary": {"total_rated": 0, "taste_dictionary": {}, "error": str(e)},
                "chart_data": {"radar": [], "bar_count": [], "bar_score": []},
                "watched_ids": []
            }
        }
