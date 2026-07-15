from langchain_core.tools import tool
from app.agents.tools.base import log_tool_call


@tool
@log_tool_call("get_current_time")
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
        weekday_map = {0: "星期一", 1: "星期二", 2: "星期三", 3: "星期四", 4: "星期五", 5: "星期六", 6: "星期日"}
        return {
            "success": True,
            "current_time": now.strftime("%Y-%m-%d %H:%M:%S"),
            "current_date": now.strftime("%Y-%m-%d"),
            "current_year": now.year,
            "current_month": now.month,
            "current_day": now.day,
            "current_hour": now.hour,
            "current_minute": now.minute,
            "current_second": now.second,
            "weekday": now.weekday(),
            "weekday_cn": weekday_map.get(now.weekday(), "未知"),
            "timestamp": now.timestamp(),
            "timezone": "本地时间"
        }
    except Exception as e:
        return {"success": False, "error": f"获取当前时间失败: {str(e)}"}
