import httpx
from typing import Dict, List, Optional, Any
from urllib.parse import urlparse

from bs4 import BeautifulSoup
from fastapi_cache.decorator import cache
from app.core.logging import get_logger

logger = get_logger(__name__)


_CALENDAR_WEEKDAYS = (
    ("Sun", 7, "星期日", "日曜日"),
    ("Mon", 1, "星期一", "月曜日"),
    ("Tue", 2, "星期二", "火曜日"),
    ("Wed", 3, "星期三", "水曜日"),
    ("Thu", 4, "星期四", "木曜日"),
    ("Fri", 5, "星期五", "金曜日"),
    ("Sat", 6, "星期六", "土曜日"),
)
_EXPECTED_WEEKDAY_IDS = {weekday_id for _, weekday_id, _, _ in _CALENDAR_WEEKDAYS}


def _calendar_has_complete_weekdays(calendar: Any) -> bool:
    """Return whether a Bangumi calendar contains all seven weekday IDs."""
    if not isinstance(calendar, list):
        return False

    weekday_ids = {
        day.get("weekday", {}).get("id")
        for day in calendar
        if isinstance(day, dict) and isinstance(day.get("weekday"), dict)
    }
    return _EXPECTED_WEEKDAY_IDS.issubset(weekday_ids)


def _subject_id_from_href(href: Optional[str]) -> Optional[int]:
    if not href:
        return None

    path_parts = urlparse(href).path.rstrip("/").split("/")
    if len(path_parts) < 2 or path_parts[-2] != "subject":
        return None

    try:
        return int(path_parts[-1])
    except ValueError:
        return None


def _parse_calendar_html(html: str) -> List[Dict[str, Any]]:
    """Parse the seven weekday columns from Bangumi's public calendar page."""
    soup = BeautifulSoup(html, "html.parser")
    calendar: List[Dict[str, Any]] = []

    for css_name, weekday_id, weekday_cn, weekday_ja in _CALENDAR_WEEKDAYS:
        weekday_column = soup.select_one(f".week.{css_name}")
        if weekday_column is None:
            continue

        links = weekday_column.select("a.l[href]")
        if not links:
            links = weekday_column.select("a[href]")

        items: List[Dict[str, Any]] = []
        seen_subject_ids = set()
        for link in links:
            href = link.get("href")
            subject_id = _subject_id_from_href(href if isinstance(href, str) else None)
            if subject_id is None or subject_id in seen_subject_ids:
                continue

            title = link.get_text(" ", strip=True)
            if not title:
                continue

            seen_subject_ids.add(subject_id)
            items.append(
                {
                    "id": subject_id,
                    "url": f"https://bgm.tv/subject/{subject_id}",
                    "type": 2,
                    "name": title,
                    "name_cn": title,
                    "summary": "",
                    "air_date": None,
                    "air_weekday": weekday_id,
                }
            )

        calendar.append(
            {
                "weekday": {
                    "en": css_name,
                    "cn": weekday_cn,
                    "ja": weekday_ja,
                    "id": weekday_id,
                },
                "items": items,
            }
        )

    return calendar


def _merge_calendar_data(
    api_calendar: Any, web_calendar: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """Use the web page for weekday coverage and retain API item details."""
    api_days_by_id = {
        day.get("weekday", {}).get("id"): day
        for day in api_calendar
        if isinstance(day, dict) and isinstance(day.get("weekday"), dict)
    } if isinstance(api_calendar, list) else {}

    merged_calendar = []
    for web_day in web_calendar:
        weekday_id = web_day["weekday"]["id"]
        api_day = api_days_by_id.get(weekday_id, {})
        api_items_by_id = {
            item.get("id"): item
            for item in api_day.get("items", [])
            if isinstance(item, dict) and item.get("id") is not None
        }

        merged_items = []
        for web_item in web_day["items"]:
            api_item = api_items_by_id.get(web_item["id"], {})
            merged_items.append({**web_item, **api_item})

        merged_calendar.append({**web_day, "items": merged_items})

    return merged_calendar


class BangumiClient:
    BASE_URL = "https://api.bgm.tv/v0"
    HEADERS = {"User-Agent": "OtakuNeko/1.0 (showayhacci@qq.com)"}
    CALENDAR_URL = "https://api.bgm.tv/calendar"
    WEB_CALENDAR_URL = "https://bgm.tv/calendar"

    async def get_user_collections(self, username: str, subject_type: Optional[int] = None, limit: int = 50, offset: int = 0) -> Dict:
        """
        从 Bangumi API 获取用户的收藏数据
        
        Args:
            username: Bangumi 用户名
            subject_type: 可选，条目类型 (1=书籍/2=动画/3=音乐/4=游戏/6=三次元)
            limit: 每页返回的条目数，默认50
            offset: 偏移量，默认0
            
        Returns:
            包含用户收藏的条目列表和元数据的字典
            
        Raises:
            httpx.HTTPStatusError: 请求失败时抛出
            httpx.RequestError: 网络错误时抛出
        """
        url = f"{self.BASE_URL}/users/{username}/collections"
        
        # 设置请求参数
        params = {
            "limit": limit,
            "offset": offset
        }
        if subject_type is not None:
            params["subject_type"] = subject_type
        
        async with httpx.AsyncClient(headers=self.HEADERS) as client:
            try:
                response = await client.get(url, params=params, timeout=30.0)
                response.raise_for_status()  # 检查请求状态
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Bangumi API 请求失败: {e.response.status_code} - {e.response.text}")
                raise
            except httpx.RequestError as e:
                logger.error(f"网络请求错误: {e}")
                raise

    @cache(expire=604800, namespace="bangumi")
    async def get_subject_detail(self, subject_id: int) -> Dict:
        """
        从 Bangumi API 获取单个条目的详细信息
        
        Args:
            subject_id: Bangumi 条目 ID
            
        Returns:
            条目的详细信息
            
        Raises:
            httpx.HTTPStatusError: 请求失败时抛出
            httpx.RequestError: 网络错误时抛出
        """
        url = f"{self.BASE_URL}/subjects/{subject_id}"
        
        async with httpx.AsyncClient(headers=self.HEADERS) as client:
            try:
                response = await client.get(url, timeout=30.0)
                response.raise_for_status()  # 检查请求状态
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Bangumi API 请求失败: {e.response.status_code} - {e.response.text}")
                raise
            except httpx.RequestError as e:
                logger.error(f"网络请求错误: {e}")
                raise

    async def search_subjects_advanced(
        self,
        keyword: str,
        sort: str = "rank",
        limit: int = 20,
        offset: int = 0,
        subject_types: Optional[List[int]] = None,
        meta_tags: Optional[List[str]] = None,
        tags: Optional[List[str]] = None,
        air_date_ranges: Optional[List[str]] = None,
        rating_ranges: Optional[List[str]] = None,
        rating_count_ranges: Optional[List[str]] = None,
        rank_ranges: Optional[List[str]] = None,
        nsfw: Optional[bool] = None
    ) -> Dict:
        """
        高级搜索：支持完整的 Bangumi API 搜索参数
        
        Args:
            keyword: 搜索关键词
            sort: 排序方式，默认为 "rank"
            limit: 返回结果数量限制，默认20
            offset: 结果偏移量，默认0
            subject_types: 条目类型列表 (1=书籍/2=动画/3=音乐/4=游戏/6=三次元)
            meta_tags: 元标签列表，如 ["童年", "原创"]
            tags: 标签列表，如 ["童年", "原创"]
            air_date_ranges: 放送日期范围列表，如 [">=2020-07-01", "<2020-10-01"]
            rating_ranges: 评分范围列表，如 [">=6", "<8"]
            rating_count_ranges: 评分人数范围列表，如 [">=200", "<5000"]
            rank_ranges: 排名范围列表，如 [">10", "<=18"]
            nsfw: 是否包含NSFW内容
            
        Returns:
            包含搜索结果的字典
            
        Raises:
            httpx.HTTPStatusError: 请求失败时抛出
            httpx.RequestError: 网络错误时抛出
        """
        url = f"{self.BASE_URL}/search/subjects"
        
        # 设置 URL 查询参数
        params = {
            "limit": limit,
            "offset": offset
        }
        
        # 构建完整的请求体
        payload: dict[str, Any] = {
            "keyword": keyword,
            "sort": sort,
            "filter": {}
        }
        
        # 构建过滤器对象
        filter_dict: dict[str, Any] = {}
        
        # 添加类型过滤
        if subject_types:
            filter_dict["type"] = subject_types
        
        # 添加元标签过滤
        if meta_tags:
            filter_dict["meta_tags"] = meta_tags
        
        # 添加标签过滤
        if tags:
            filter_dict["tag"] = tags
        
        # 添加放送日期范围过滤
        if air_date_ranges:
            filter_dict["air_date"] = air_date_ranges
        
        # 添加评分范围过滤
        if rating_ranges:
            filter_dict["rating"] = rating_ranges
        
        # 添加评分人数范围过滤
        if rating_count_ranges:
            filter_dict["rating_count"] = rating_count_ranges
        
        # 添加排名范围过滤
        if rank_ranges:
            filter_dict["rank"] = rank_ranges
        
        # 添加NSFW过滤
        if nsfw is not None:
            filter_dict["nsfw"] = nsfw
        
        # 将过滤器添加到payload中
        if filter_dict:
            payload["filter"] = filter_dict
        
        async with httpx.AsyncClient(headers=self.HEADERS) as client:
            try:
                # 发送 POST 请求
                response = await client.post(
                    url,
                    params=params,
                    json=payload,
                    timeout=30.0
                )
                response.raise_for_status()  # 检查请求状态
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Bangumi API 高级搜索请求失败: {e.response.status_code} - {e.response.text}")
                raise
            except httpx.RequestError as e:
                logger.error(f"网络请求错误: {e}")
                raise

    @cache(expire=86400, namespace="bangumi")
    async def search_subjects(
        self,
        keyword: Optional[str] = None,
        subject_type: Optional[int] = None,
        limit: int = 20,
        offset: int = 0
    ) -> Dict:
        """
        从 Bangumi API 搜索条目
        
        Args:
            keyword: 搜索关键词
            subject_type: 可选，条目类型 (1=书籍/2=动画/3=音乐/4=游戏/6=三次元)
            limit: 返回结果数量限制，默认20
            offset: 结果偏移量，默认0
            
        Returns:
            包含搜索结果的字典
            
        Raises:
            httpx.HTTPStatusError: 请求失败时抛出
            httpx.RequestError: 网络错误时抛出
        """
        # 如果keyword为None，直接返回空结果
        if keyword is None:
            return {"data": [], "total": 0}
        
        url = f"{self.BASE_URL}/search/subjects"
        
        # 设置 URL 查询参数 (Query Parameters)
        params = {
            "limit": limit,
            "offset": offset
        }
        
        # 构建请求体 (Request Body)
        payload: dict[str, Any] = {
            "keyword": keyword,
            "sort": "rank",
            "filter": {}
        }
        
        # 添加类型过滤
        if subject_type is not None:
            payload["filter"]["type"] = [subject_type]
        
        async with httpx.AsyncClient(headers=self.HEADERS) as client:
            try:
                # 发送 POST 请求
                response = await client.post(
                    url,
                    params=params,
                    json=payload,
                    timeout=30.0
                )
                response.raise_for_status()  # 检查请求状态
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Bangumi API 请求失败: {e.response.status_code} - {e.response.text}")
                raise
            except httpx.RequestError as e:
                logger.error(f"网络请求错误: {e}")
                raise

    @cache(expire=86400, namespace="bangumi")
    async def get_user_info(self, username: str) -> Dict:
        """
        从 Bangumi API 获取用户信息
        
        Args:
            username: Bangumi 用户名
            
        Returns:
            包含用户信息的字典
            
        Raises:
            httpx.HTTPStatusError: 请求失败时抛出
            httpx.RequestError: 网络错误时抛出
        """
        url = f"{self.BASE_URL}/users/{username}"
        
        async with httpx.AsyncClient(headers=self.HEADERS) as client:
            try:
                response = await client.get(url, timeout=30.0)
                response.raise_for_status()  # 检查请求状态
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Bangumi API 请求失败: {e.response.status_code} - {e.response.text}")
                raise
            except httpx.RequestError as e:
                logger.error(f"网络请求错误: {e}")
                raise

    async def get_subject_raw(self, subject_id: int) -> Dict[str, Any]:
        """
        只负责发送请求，返回原始 JSON 字典。
        不包含任何业务逻辑清洗。
        """
        url = f"{self.BASE_URL}/subjects/{subject_id}"
        async with httpx.AsyncClient(headers=self.HEADERS) as client:
            try:
                resp = await client.get(url)
                # 如果是 404 或 500，这里直接抛错
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Bangumi API 请求失败: {e.response.status_code} - {e.response.text}")
                raise
            except httpx.RequestError as e:
                logger.error(f"网络请求错误: {e}")
                raise
            
    async def get_persons_raw(self, subject_id: int) -> list:
        """获取原始的人物/Staff列表"""
        url = f"{self.BASE_URL}/subjects/{subject_id}/persons"
        async with httpx.AsyncClient(headers=self.HEADERS) as client:
            try:
                resp = await client.get(url)
                # 如果是 404 或 500，这里直接抛错
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Bangumi API 请求失败: {e.response.status_code} - {e.response.text}")
                raise
            except httpx.RequestError as e:
                logger.error(f"网络请求错误: {e}")
                raise

    async def get_characters_raw(self, subject_id: int) -> list:
        """获取原始的角色列表"""
        url = f"{self.BASE_URL}/subjects/{subject_id}/characters"
        async with httpx.AsyncClient(headers=self.HEADERS) as client:
            try:
                resp = await client.get(url)
                # 如果是 404 或 500，这里直接抛错
                resp.raise_for_status()
                return resp.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"Bangumi API 请求失败: {e.response.status_code} - {e.response.text}")
                raise
            except httpx.RequestError as e:
                logger.error(f"网络请求错误: {e}")
                raise

    @cache(expire=86400, namespace="bangumi-calendar-v3")
    async def get_calendar(self) -> List[Dict[str, Any]]:
        """
        从 Bangumi API 获取每日放送信息
        
        Returns:
            包含每日放送信息的字典
            
        Raises:
            httpx.HTTPStatusError: 请求失败时抛出
            httpx.RequestError: 网络错误时抛出
        """
        url = self.CALENDAR_URL
        
        async with httpx.AsyncClient(headers=self.HEADERS) as client:
            try:
                response = await client.get(url, timeout=30.0)
                response.raise_for_status()  # 检查请求状态
                api_calendar = response.json()
                if _calendar_has_complete_weekdays(api_calendar):
                    return api_calendar

                logger.warning(
                    "Bangumi API calendar has incomplete weekday coverage; using web fallback"
                )
                web_response = await client.get(self.WEB_CALENDAR_URL, timeout=30.0)
                web_response.raise_for_status()
                web_calendar = _parse_calendar_html(web_response.text)
                if not _calendar_has_complete_weekdays(web_calendar):
                    raise ValueError("Bangumi web calendar does not contain all weekdays")
                return _merge_calendar_data(api_calendar, web_calendar)
            except httpx.HTTPStatusError as e:
                logger.error(f"Bangumi API 请求失败: {e.response.status_code} - {e.response.text}")
                raise
            except httpx.RequestError as e:
                logger.error(f"网络请求错误: {e}")
                raise


# 创建全局单例实例
bangumi_client = BangumiClient()

# 为了保持向后兼容，导出原函数名作为别名
fetch_user_collections = bangumi_client.get_user_collections
fetch_subject_detail = bangumi_client.get_subject_detail
search_subjects = bangumi_client.search_subjects
search_subjects_advanced = bangumi_client.search_subjects_advanced
fetch_user_info = bangumi_client.get_user_info
fetch_calendar = bangumi_client.get_calendar
