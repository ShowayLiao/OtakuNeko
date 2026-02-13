from typing import Optional, Dict, List, Any
from pydantic import BaseModel, RootModel


class RemoveRssRuleRequest(BaseModel):
    """
    删除 RSS 自动下载规则请求模型
    """
    rule_name: str


class TorrentParams(BaseModel):
    """
    种子参数模型
    """
    category: str
    content_layout: Optional[str] = None
    download_limit: int
    download_path: str
    inactive_seeding_time_limit: int
    operating_mode: str
    ratio_limit: int
    save_path: str
    seeding_time_limit: int
    share_limit_action: str
    skip_checking: bool
    ssl_certificate: str
    ssl_dh_params: str
    ssl_private_key: str
    tags: List[str]
    upload_limit: int
    use_auto_tmm: Optional[bool] = None
    stop_condition: Optional[str] = None


class RssRule(BaseModel):
    """
    RSS 自动下载规则模型
    """
    addPaused: Optional[bool] = None
    affectedFeeds: List[str]
    assignedCategory: str
    enabled: bool
    episodeFilter: str
    ignoreDays: int
    lastMatch: Optional[str] = None
    mustContain: str
    mustNotContain: str
    previouslyMatchedEpisodes: List[str]
    priority: int
    savePath: str
    smartFilter: bool
    torrentContentLayout: Optional[str] = None
    torrentParams: Optional[TorrentParams] = None
    useRegex: bool


class RssFeedItem(BaseModel):
    """
    RSS 订阅项模型
    """
    uid: str
    url: str


class RssItemsResponse(BaseModel):
    """
    RSS 订阅项列表响应模型
    """
    items: Dict[str, RssFeedItem]
    
    @classmethod
    def __get_validators__(cls):
        yield cls.validate
    
    @classmethod
    def validate(cls, v):
        if isinstance(v, dict):
            return cls(items=v)
        return v


class RssRulesResponse(BaseModel):
    """
    RSS 自动下载规则响应模型
    """
    rules: Dict[str, RssRule]
    
    @classmethod
    def __get_validators__(cls):
        yield cls.validate
    
    @classmethod
    def validate(cls, v):
        if isinstance(v, dict):
            return cls(rules=v)
        return v


class AddRssFeedRequest(BaseModel):
    """
    添加 RSS 订阅源请求模型
    """
    url: str
    name: Optional[str] = None


class RemoveRssItemRequest(BaseModel):
    """
    删除 RSS 订阅项请求模型
    """
    item_path: str


class SetRssRuleRequest(BaseModel):
    """
    设置 RSS 自动下载规则请求模型
    """
    rule_name: str
    rule: RssRule


