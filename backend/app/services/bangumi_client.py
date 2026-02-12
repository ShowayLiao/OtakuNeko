import httpx
from typing import Dict, List, Optional, Any

from fastapi_cache.decorator import cache
from app.core.logging import get_logger

logger = get_logger(__name__)


class BangumiClient:
    BASE_URL = "https://api.bgm.tv/v0"
    HEADERS = {"User-Agent": "OtakuNeko/1.0 (showayhacci@qq.com)"}

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
        payload = {
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


# 创建全局单例实例
bangumi_client = BangumiClient()

# 为了保持向后兼容，导出原函数名作为别名
fetch_user_collections = bangumi_client.get_user_collections
fetch_subject_detail = bangumi_client.get_subject_detail
search_subjects = bangumi_client.search_subjects
fetch_user_info = bangumi_client.get_user_info
