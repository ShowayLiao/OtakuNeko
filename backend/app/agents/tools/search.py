from typing import Optional
from langchain_core.tools import tool
from app.capabilities.anime import AnimeCapability
from app.agents.tools.base import log_tool_call


def _build_air_date_ranges(min_year, max_year, min_month, max_month, min_day, max_day):
    from datetime import datetime
    import calendar

    current_year = datetime.now().year
    adjusted_min_year = min_year
    adjusted_max_year = max_year

    if (min_month is not None or max_month is not None) and (min_year is None and max_year is None):
        adjusted_min_year = current_year
        adjusted_max_year = current_year

    ranges = []
    if adjusted_min_year is not None:
        start_date = f"{adjusted_min_year:04d}"
        if min_month is not None:
            start_date += f"-{min_month:02d}"
            start_date += f"-{min_day:02d}" if min_day is not None else "-01"
        else:
            start_date += "-01-01"
        ranges.append(f">={start_date}")

    if adjusted_max_year is not None:
        end_date = f"{adjusted_max_year:04d}"
        if max_month is not None:
            end_date += f"-{max_month:02d}"
            if max_day is not None:
                end_date += f"-{max_day:02d}"
            else:
                last_day = calendar.monthrange(adjusted_max_year, max_month)[1]
                end_date += f"-{last_day:02d}"
        else:
            end_date += "-12-31"
        ranges.append(f"<={end_date}")
    return ranges


_anime_capability = AnimeCapability()


@tool
@log_tool_call("search_anime_advanced")
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
        subject_types = [subject_type] if subject_type else None
        tag_list = [t.strip() for t in tags.split(",") if t.strip()] if tags else None

        rating_ranges = None
        if min_rating is not None or max_rating is not None:
            rating_ranges = []
            if min_rating is not None:
                rating_ranges.append(f">={min_rating}")
            if max_rating is not None:
                rating_ranges.append(f"<={max_rating}")

        air_ranges = _build_air_date_ranges(min_year, max_year, min_month, max_month, min_day, max_day)

        result = await _anime_capability.execute(
            "search",
            keyword=keyword, subject_types=subject_types, tags=tag_list,
            rating_ranges=rating_ranges if rating_ranges else None,
            air_date_ranges=air_ranges if air_ranges else None,
            limit=limit, offset=0
        )

        if result.get("success") and result.get("total", 0) <= 3 and air_ranges:
            fallback = await _anime_capability.execute(
                "search",
                keyword=keyword, subject_types=subject_types, tags=tag_list,
                rating_ranges=rating_ranges if rating_ranges else None,
                air_date_ranges=None, limit=limit, offset=0
            )
            fallback_results = fallback.get("results", [])
            return {
                "success": fallback.get("success", False), "total": fallback.get("total", 0), "limit": limit,
                "results": fallback_results,
                "note": "Bangumi 中该时间段准确 air_date 条目较少，已展示相关结果"
            }

        result["limit"] = limit
        return result
    except Exception as e:
        return {"success": False, "error": f"高级搜索失败: {str(e)}"}
