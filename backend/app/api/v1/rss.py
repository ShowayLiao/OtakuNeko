from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from app.api.deps import check_qb_enabled
from app.services.qb_service import QBService
from app.schemas.rss import (
    AddRssFeedRequest,
    RemoveRssItemRequest,
    SetRssRuleRequest,
    RemoveRssRuleRequest,
    RssRulesResponse,
    RssItemsResponse,
    RssRule
)

router = APIRouter(prefix="/rss", tags=["RSS"])


@router.get("/list", dependencies=[Depends(check_qb_enabled)], response_model=RssItemsResponse)
def get_rss_list():
    """
    获取所有 RSS 订阅项
    
    Returns:
        RssItemsResponse: RSS 订阅项列表
    """
    qb_service = QBService()
    return qb_service.get_rss_items()


@router.post("/add", dependencies=[Depends(check_qb_enabled)])
def add_rss_feed(request: AddRssFeedRequest):
    """
    添加 RSS 订阅源
    
    Args:
        request: 添加 RSS 订阅源请求
    """
    qb_service = QBService()
    qb_service.add_rss_feed(url=request.url, name=request.name)
    return {"message": "RSS 订阅源添加成功"}


@router.post("/upsert", dependencies=[Depends(check_qb_enabled)])
def upsert_rss_feed(request: AddRssFeedRequest):
    """
    Upsert RSS 订阅源 (存在则检查更新，不存在则添加)
    
    Args:
        request: Upsert RSS 订阅源请求
    """
    qb_service = QBService()
    qb_service.upsert_rss_feed(url=request.url, name=request.name)
    return {"message": "RSS 订阅源 upsert 成功"}


@router.delete("/remove", dependencies=[Depends(check_qb_enabled)])
def remove_rss_item(request: RemoveRssItemRequest):
    """
    删除 RSS 订阅项
    
    Args:
        request: 删除 RSS 订阅项请求
    """
    qb_service = QBService()
    qb_service.remove_rss_item(item_path=request.item_path)
    return {"message": "RSS 订阅项删除成功"}


@router.post("/set-rule", dependencies=[Depends(check_qb_enabled)])
def set_rss_rule(request: SetRssRuleRequest):
    """
    设置 RSS 自动下载规则
    
    Args:
        request: 设置 RSS 自动下载规则请求
    """
    qb_service = QBService()
    qb_service.set_rss_rule(
        rule_name=request.rule_name,
        rule=request.rule
    )
    return {"message": "RSS 自动下载规则设置成功"}


@router.delete("/remove-rule", dependencies=[Depends(check_qb_enabled)])
def remove_rss_rule(request: RemoveRssRuleRequest):
    """
    删除 RSS 自动下载规则
    
    Args:
        request: 删除 RSS 自动下载规则请求
    """
    qb_service = QBService()
    qb_service.remove_rss_rule(rule_name=request.rule_name)
    return {"message": "RSS 自动下载规则删除成功"}


@router.get("/rules", dependencies=[Depends(check_qb_enabled)], response_model=RssRulesResponse)
def get_rss_rules():
    """
    获取所有 RSS 自动下载规则
    
    Returns:
        RssRulesResponse: RSS 自动下载规则列表
    """
    qb_service = QBService()
    return qb_service.get_rss_rules()
