from typing import Optional, Dict, Any
import qbittorrentapi
from fastapi import HTTPException, status
from app.core.config import settings
from app.core.logging import get_logger
from app.schemas.rss import RssRulesResponse, RssItemsResponse, RssRule

logger = get_logger(__name__)


class QBService:
    """
    qBittorrent API 服务类
    封装 qBittorrent API 调用方法
    """
    
    def __init__(self):
        """
        初始化 QBService
        """
        self.client = None
        self._initialize_client()
    
    def _initialize_client(self):
        """
        初始化 qBittorrent 客户端
        """
        try:
            # 记录初始化开始
            logger.info(f"开始初始化 qBittorrent 客户端")
            logger.debug(f"qBittorrent 配置: host={settings.QB_HOST}, username={settings.QB_USERNAME}")
            
            # 创建 qBittorrent 客户端
            self.client = qbittorrentapi.Client(
                host=settings.QB_HOST,
                username=settings.QB_USERNAME,
                password=settings.QB_PASSWORD
            )
            
            # 测试连接和鉴权
            logger.info("正在测试 qBittorrent 连接和鉴权")
            self.client.auth_log_in()
            logger.info("qBittorrent 客户端初始化成功")
        except qbittorrentapi.LoginFailed as e:
            logger.error(f"qBittorrent 登录失败: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"qBittorrent 登录失败: {str(e)}"
            )
        except qbittorrentapi.ConnectionError as e:
            logger.error(f"无法连接到 qBittorrent: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"无法连接到 qBittorrent: {str(e)}"
            )
        except Exception as e:
            logger.error(f"初始化 qBittorrent 客户端失败: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"初始化 qBittorrent 客户端失败: {str(e)}"
            )
    
    def get_client(self):
        """
        获取 qBittorrent 客户端实例
        
        Returns:
            qbittorrentapi.Client: qBittorrent 客户端实例
        """
        if not self.client:
            logger.debug("qBittorrent 客户端未初始化，正在初始化...")
            self._initialize_client()
        return self.client
    
    def get_rss_items(self) -> RssItemsResponse:
        """
        获取所有 RSS 订阅项
        
        Returns:
            RssItemsResponse: RSS 订阅项列表
        """
        try:
            logger.info("开始获取 RSS 订阅项")
            client = self.get_client()
            result = client.rss_items()
            logger.info(f"成功获取 RSS 订阅项，共 {len(result) if isinstance(result, dict) else 0} 个")
            return RssItemsResponse(items=result)
        except Exception as e:
            logger.error(f"获取 RSS 订阅项失败: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"获取 RSS 订阅项失败: {str(e)}"
            )
    
    def add_rss_feed(self, url: str, name: Optional[str] = None) -> None:
        """
        添加 RSS 订阅源
        
        Args:
            url: RSS 源 URL
            name: 订阅源名称
        """
        try:
            logger.info(f"开始添加 RSS 订阅源: url={url}, name={name}")
            client = self.get_client()
            client.rss_add_feed(url=url, item_path=name)
            logger.info(f"成功添加 RSS 订阅源: url={url}")
        except Exception as e:
            logger.error(f"添加 RSS 订阅源失败: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"添加 RSS 订阅源失败: {str(e)}"
            )

    def upsert_rss_feed(self, url: str, name: str) -> None:
        """
        Upsert RSS 订阅源 (存在则检查更新，不存在则添加)
        注意：qBittorrent 不支持直接修改 RSS 的 URL，所以更新等同于"删除后重新添加"
        """
        try:
            client = self.get_client()
            
            # 1. 获取当前所有 RSS 条目 (返回的是一个字典，Key 是路径/名字)
            # include_feed_data=True 确保我们需要获取 URL
            current_feeds = client.rss_items(include_feed_data=True)
            
            # 2. 检查是否已存在同名订阅
            if name in current_feeds:
                existing_feed = current_feeds[name]
                existing_url = existing_feed.get('url', '')
                
                # 情况 A: URL 完全一致 -> 无需操作
                if existing_url == url:
                    logger.info(f"RSS 订阅已存在且一致，跳过: name={name}")
                    return

                # 情况 B: URL 不一致 -> 需要更新
                # 由于 qBt API 不支持直接修改 URL，必须先删除旧的
                logger.warning(f"检测到 RSS URL 变更，正在更新: name={name}")
                client.rss_remove_item(item_path=name)
            
            # 3. 添加订阅 (新建 或 删除后的重建)
            client.rss_add_feed(url=url, item_path=name)
            logger.info(f"成功 Upsert RSS 订阅源: name={name}, url={url}")

        except Exception as e:
            logger.error(f"Upsert RSS 订阅源失败: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Upsert RSS 订阅源失败: {str(e)}"
            )
    
    def remove_rss_item(self, item_path: str) -> None:
        """
        删除 RSS 订阅项
        
        Args:
            item_path: 订阅项路径
        """
        try:
            logger.info(f"开始删除 RSS 订阅项: {item_path}")
            client = self.get_client()
            client.rss_remove_item(item_path=item_path)
            logger.info(f"成功删除 RSS 订阅项: {item_path}")
        except Exception as e:
            logger.error(f"删除 RSS 订阅项失败: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"删除 RSS 订阅项失败: {str(e)}"
            )
    
    def set_rss_rule(self, rule_name: str, rule: RssRule) -> None:
        """
        设置 RSS 自动下载规则
        
        Args:
            rule_name: 规则名称
            rule: RSS 规则配置
        """
        try:
            client = self.get_client()
            
            # 1. 使用 by_alias=True 确保转为 camelCase (例如 save_path -> savePath)
            rule_params = rule.model_dump(exclude_unset=True, by_alias=True)
            
            logger.info(f"开始设置规则: {rule_name}")
            logger.info(f"最终 Payload: {rule_params}")

            # 2. 这里的关键是 rule_def=rule_params，不要用 **
            client.rss_set_rule(rule_name=rule_name, rule_def=rule_params)
            
            logger.info(f"成功设置 RSS 自动下载规则: {rule_name}")
        except Exception as e:
            logger.error(f"设置 RSS 自动下载规则失败: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"设置 RSS 自动下载规则失败: {str(e)}"
            )
    
    def remove_rss_rule(self, rule_name: str) -> None:
        """
        删除 RSS 自动下载规则
        
        Args:
            rule_name: 规则名称
        """
        try:
            logger.info(f"开始删除 RSS 自动下载规则: {rule_name}")
            client = self.get_client()
            client.rss_remove_rule(rule_name=rule_name)
            logger.info(f"成功删除 RSS 自动下载规则: {rule_name}")
        except Exception as e:
            logger.error(f"删除 RSS 自动下载规则失败: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"删除 RSS 自动下载规则失败: {str(e)}"
            )
    
    def get_rss_rules(self) -> RssRulesResponse:
        """
        获取所有 RSS 自动下载规则
        
        Returns:
            RssRulesResponse: RSS 自动下载规则列表
        """
        try:
            logger.info("开始获取 RSS 自动下载规则")
            client = self.get_client()
            result = client.rss_rules()
            logger.info(f"成功获取 RSS 自动下载规则，共 {len(result) if isinstance(result, dict) else 0} 个")
            return RssRulesResponse(rules=result)
        except Exception as e:
            logger.error(f"获取 RSS 自动下载规则失败: {str(e)}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"获取 RSS 自动下载规则失败: {str(e)}"
            )
