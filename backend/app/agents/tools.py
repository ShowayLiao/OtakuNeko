from langchain_core.tools import tool
from typing import Optional, List, Dict, Any
from app.services.bangumi_service import fetch_subject_by_id, get_audience_feedback, get_staff_info, get_cast_info
from app.services.bangumi_client import search_subjects_advanced
from app.schemas.bangumi import SubjectDetail
from app.services.user_profile_service import generate_user_profile

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

@tool
async def search_anime_advanced(
    keyword: str,
    subject_type: int = 2,
    tags: Optional[str] = None,
    min_rating: Optional[float] = None,
    max_rating: Optional[float] = None,
    min_year: Optional[int] = None,
    max_year: Optional[int] = None,
    min_month: Optional[int] = None,
    max_month: Optional[int] = None,
    min_day: Optional[int] = None,
    max_day: Optional[int] = None,
    limit: int = 10
) -> dict:
    """
    Bangumi 动画搜索。按关键词、标签、评分、时间段筛选。当用户想找动画时使用。
    
    ⚠️ keyword 规则（最重要）：
    - keyword 只填用户想搜的动画名称/类型词，如 "进击的巨人"、"魔法少女"
    - 用户问"有什么好看的"、"4月播了什么" → keyword=""（空字符串）
    - 日期（2026年4月）、季节（4月新番）绝对不放进 keyword
    
    参数速查：
    - keyword: 动画名称/题材词，纯问"有什么"时留空 ""
    - tags: 标签，逗号分隔，如 "治愈,热血,原创"
    - min_rating / max_rating: 评分范围 (0-10)
    - min_year / max_year: 年份范围。只提月份不提年份时默认当前年
    - min_month / max_month: 月份范围 (1-12)
    - min_day / max_day: 日期范围 (1-31)
    - limit: 返回条数，默认 10
    """
    try:
        # 准备搜索参数
        subject_types = [subject_type] if subject_type else None
        
        # 处理标签参数
        tag_list = None
        if tags:
            tag_list = [tag.strip() for tag in tags.split(",") if tag.strip()]
        
        # 智能评分处理
        rating_ranges = None
        adjusted_min_rating = min_rating
        adjusted_max_rating = max_rating
        
        # 如果用户没有指定评分但查询中包含推荐/高分等词汇，设置默认阈值
        # 这个逻辑由大模型在调用工具时决定参数，这里保持灵活性
        
        if adjusted_min_rating is not None or adjusted_max_rating is not None:
            rating_ranges = []
            if adjusted_min_rating is not None:
                rating_ranges.append(f">={adjusted_min_rating}")
            if adjusted_max_rating is not None:
                rating_ranges.append(f"<={adjusted_max_rating}")
        
        # 处理日期范围 - 支持精确到年、月、日的搜索
        air_date_ranges = None
        
        # 如果用户指定了月份但没有指定年份，使用当前年份
        from datetime import datetime
        current_year = datetime.now().year
        current_month = datetime.now().month
        
        # 调整年份参数：如果指定了月份但没有年份，使用当前年份
        adjusted_min_year = min_year
        adjusted_max_year = max_year
        adjusted_min_month = min_month
        adjusted_max_month = max_month
        
        # 智能时间处理逻辑
        if (min_month is not None or max_month is not None) and (min_year is None and max_year is None):
            # 用户只提到了月份（如"4月新番"），使用当前年份
            adjusted_min_year = current_year
            adjusted_max_year = current_year
        
        # 处理"最近"查询 - 如果用户查询"最近有什么好看的动画"
        # 这个逻辑由大模型在调用工具时决定参数，这里保持灵活性
        
        if any([adjusted_min_year, adjusted_max_year, min_month, max_month, min_day, max_day]):
            air_date_ranges = []
            
            # 构建开始日期
            if adjusted_min_year is not None:
                start_date = f"{adjusted_min_year:04d}"
                if min_month is not None:
                    start_date += f"-{min_month:02d}"
                    if min_day is not None:
                        start_date += f"-{min_day:02d}"
                    else:
                        start_date += "-01"  # 如果没有指定日期，默认为当月1号
                else:
                    start_date += "-01-01"  # 如果没有指定月份，默认为1月1号
                air_date_ranges.append(f">={start_date}")
            
            # 构建结束日期
            if adjusted_max_year is not None:
                end_date = f"{adjusted_max_year:04d}"
                if max_month is not None:
                    end_date += f"-{max_month:02d}"
                    if max_day is not None:
                        end_date += f"-{max_day:02d}"
                    else:
                        # 如果没有指定日期，需要计算该月的最后一天
                        import calendar
                        last_day = calendar.monthrange(adjusted_max_year, max_month)[1]
                        end_date += f"-{last_day:02d}"
                else:
                    end_date += "-12-31"  # 如果没有指定月份，默认为12月31号
                air_date_ranges.append(f"<={end_date}")
        
        # 调用高级搜索API
        result = await search_subjects_advanced(
            keyword=keyword,
            subject_types=subject_types,
            tags=tag_list,
            rating_ranges=rating_ranges,
            air_date_ranges=air_date_ranges,
            limit=limit,
            offset=0
        )
        
        # 简化返回结果，只保留核心信息
        simplified_results = []
        for item in result.get("data", []):
            simplified_results.append({
                "id": item.get("id"),
                "name": item.get("name"),
                "name_cn": item.get("name_cn"),
                "summary": item.get("summary", "")[:200] + "..." if item.get("summary") else "",
                "score": item.get("rating", {}).get("score", 0),
                "rank": item.get("rating", {}).get("rank", 0),
                "type": item.get("type"),
                "air_date": item.get("air_date"),
                "images": item.get("images", {})
            })

        total = result.get("total", 0)
        if total <= 3 and air_date_ranges:
            fallback = await search_subjects_advanced(
                keyword=keyword,
                subject_types=subject_types,
                tags=tag_list,
                rating_ranges=rating_ranges,
                air_date_ranges=None,
                limit=limit,
                offset=0
            )
            fallback_results = []
            for item in fallback.get("data", []):
                fallback_results.append({
                    "id": item.get("id"),
                    "name": item.get("name"),
                    "name_cn": item.get("name_cn"),
                    "summary": item.get("summary", "")[:200] + "..." if item.get("summary") else "",
                    "score": item.get("rating", {}).get("score", 0),
                    "rank": item.get("rating", {}).get("rank", 0),
                    "type": item.get("type"),
                    "air_date": item.get("air_date"),
                    "images": item.get("images", {})
                })
            return {
                "total": fallback.get("total", 0),
                "limit": limit,
                "results": fallback_results,
                "note": "Bangumi 中该时间段准确 air_date 条目较少，已展示相关结果"
            }

        return {
            "total": total,
            "limit": limit,
            "results": simplified_results
        }
        
    except Exception as e:
        return {"error": f"高级搜索失败: {str(e)}"}

@tool
async def get_current_time() -> dict:
    """
    获取当前系统时间。
    
    当用户询问当前时间、日期或需要时间参考时使用此工具。
    返回当前日期和时间信息，可用于时间相关的查询或验证。
    
    Returns:
        包含当前时间信息的字典，包括：
        - current_time: 当前日期时间字符串 (YYYY-MM-DD HH:MM:SS)
        - current_date: 当前日期字符串 (YYYY-MM-DD)
        - current_year: 当前年份
        - current_month: 当前月份 (1-12)
        - current_day: 当前日期 (1-31)
        - current_hour: 当前小时 (0-23)
        - current_minute: 当前分钟 (0-59)
        - current_second: 当前秒数 (0-59)
        - weekday: 当前星期几 (0=周一, 6=周日)
        - weekday_cn: 中文星期几 (星期一~星期日)
    """
    try:
        from datetime import datetime
        
        now = datetime.now()
        
        # 星期几映射
        weekday_map = {
            0: "星期一",
            1: "星期二", 
            2: "星期三",
            3: "星期四",
            4: "星期五",
            5: "星期六",
            6: "星期日"
        }
        
        weekday_cn = weekday_map.get(now.weekday(), "未知")
        
        return {
            "current_time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "current_date": now.strftime("%Y-%m-%d"),
            "current_year": now.year,
            "current_month": now.month,
            "current_day": now.day,
            "current_hour": now.hour,
            "current_minute": now.minute,
            "current_second": now.second,
            "weekday": now.weekday(),  # 0=周一, 6=周日
            "weekday_cn": weekday_cn,
            "timestamp": now.timestamp(),
            "timezone": "本地时间"
        }
        
    except Exception as e:
        return {"error": f"获取当前时间失败: {str(e)}"}

@tool
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
            "collection": {
                "rate": 8,  # 用户评分 (0-10)
                "type": 2,  # 收藏类型：2=看过
                ...其他收藏字段
            },
            "subject": {
                "id": 12345,  # 动画ID
                "name": "动画名称",
                "tags": [  # 标签列表
                    {"name": "治愈"},
                    {"name": "日常"},
                    ...
                ],
                ...其他动画信息
            }
        },
        ...
    ]
    
    【输出数据结构】
    返回包含三部分数据的用户画像：
    1. llm_summary: 供给大模型使用的全景字典，包含：
       - total_rated: 有效评分数量
       - taste_dictionary: 标签全景字典，格式为{"标签名": [频次, 平均分]}
    
    2. chart_data: 供给前端画图使用的数据结构，包含：
       - radar: 雷达图数据（偏好指数前6的标签）
       - bar_count: 频次柱状图数据（频次前5的标签）
       - bar_score: 质量柱状图数据（平均分前5的标签）
    
    3. watched_ids: 已观看动画的ID列表（去重）
    
    【算法说明】
    1. 数据清洗：提取有效评分数据（跳过评分0或None的记录）
    2. 基础统计：统计每个标签的出现次数和累加总分
    3. 统计学修正：计算平均分，过滤掉count<2的小样本标签
    4. 构建全景字典：按频次降序排列，格式为"标签名": [频次, 平均分]
    5. 计算综合偏好指数：基于评分和频次计算0-100的偏好指数
    6. 构建图表数据：生成雷达图、柱状图所需的数据
    
    【使用示例】
    1. "分析我的动画观看偏好" → 调用此工具分析用户收藏数据
    2. "根据我的观看历史推荐动画" → 先调用此工具生成画像，再基于画像推荐
    3. "我的动画偏好是什么" → 调用此工具获取用户偏好标签
    
    Args:
        collections: 用户收藏列表，每个元素应包含collection和subject信息
        
    Returns:
        包含三部分数据的用户画像字典
    """
    try:
        # 调用用户画像生成服务
        profile = generate_user_profile(collections)
        
        # 返回结果
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


