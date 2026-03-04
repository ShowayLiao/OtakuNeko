import httpx
from typing import Optional
from app.core.logging import get_logger

logger = get_logger(__name__)

class BangumiClient:
    WEB_BASE_URL = "https://bgm.tv"
    SCRAPER_HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
        "Referer": "https://bgm.tv/"
    }

    async def get_comments_html(self, subject_id: int) -> str:
        """
        获取 Bangumi 条目的短评 HTML
        
        Args:
            subject_id: Bangumi 条目 ID
            
        Returns:
            短评页面的 HTML 文本
        """
        url = f"{self.WEB_BASE_URL}/subject/{subject_id}/comments"
        async with httpx.AsyncClient(headers=self.SCRAPER_HEADERS) as client:
            try:
                response = await client.get(url, timeout=30.0)
                response.raise_for_status()
                return response.text
            except httpx.HTTPStatusError as e:
                logger.error(f"Bangumi API 请求失败: {e.response.status_code} - {e.response.text}")
                raise
            except httpx.RequestError as e:
                logger.error(f"网络请求错误: {e}")
                raise

    async def get_reviews_html(self, subject_id: int) -> str:
        """
        获取 Bangumi 条目的长评 HTML
        
        Args:
            subject_id: Bangumi 条目 ID
            
        Returns:
            长评页面的 HTML 文本
        """
        url = f"{self.WEB_BASE_URL}/subject/{subject_id}/reviews"
        async with httpx.AsyncClient(headers=self.SCRAPER_HEADERS) as client:
            try:
                response = await client.get(url, timeout=30.0)
                response.raise_for_status()
                return response.text
            except httpx.HTTPStatusError as e:
                logger.error(f"Bangumi API 请求失败: {e.response.status_code} - {e.response.text}")
                raise
            except httpx.RequestError as e:
                logger.error(f"网络请求错误: {e}")
                raise
