from __future__ import annotations
import json
from app.core.logging import get_logger
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Optional, List

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, col

from app.models import AnimeBroadcastMetadata

logger = get_logger(__name__)


class BangumiDataSyncService:
    """
    Bangumi 数据同步服务
    
    用于从 bangumi-data 同步番剧放送信息，并提供查询放送时间的功能
    """
    # 常量定义
    DATA_URL = "https://cdn.jsdelivr.net/npm/bangumi-data@0.3/dist/data.json"
    
    @classmethod
    async def fetch_and_sync_recent_data(cls, db: AsyncSession) -> int:
        """
        从 bangumi-data 同步最近的番剧放送信息
        
        Args:
            db: 数据库会话
        
        Returns:
            同步的记录数量
        
        Raises:
            Exception: 同步过程中发生错误时抛出
        """
        # 数据源配置
        data_sources = [
            "https://cdn.jsdelivr.net/npm/bangumi-data@0.3/dist/data.json",
            "https://unpkg.com/bangumi-data@0.3/dist/data.json",  # 备用数据源
        ]
        
        # 重试配置
        max_retries = 3
        retry_delay = 2  # 秒
        
        for attempt in range(max_retries):
            for source_idx, data_url in enumerate(data_sources):
                try:
                    logger.info(f"开始同步 bangumi-data 数据 (尝试 {attempt + 1}/{max_retries}, 数据源 {source_idx + 1}/{len(data_sources)})")
                    logger.info(f"使用数据源: {data_url}")
                    
                    # 记录请求开始时间
                    start_time = datetime.now()
                    
                    # 使用 httpx 异步下载数据
                    async with httpx.AsyncClient() as client:
                        response = await client.get(data_url, timeout=30.0)
                        
                        # 计算响应时间
                        response_time = (datetime.now() - start_time).total_seconds()
                        
                        # 记录详细的网络请求日志
                        logger.info(f"网络请求完成，状态码: {response.status_code}, 响应时间: {response_time:.2f}s")
                        
                        response.raise_for_status()
                        data = response.json()
                    
                    logger.info("成功下载 bangumi-data 数据")
                    
                    # 验证数据格式
                    if not isinstance(data, dict) or "items" not in data:
                        logger.error("下载的数据格式不正确，缺少 'items' 字段")
                        continue
                    
                    # 计算日期范围
                    current_date = datetime.now(timezone.utc)
                    start_date = current_date - timedelta(days=90)
                    end_date = current_date + timedelta(days=90)
                    
                    logger.info(f"过滤日期范围: {start_date} 到 {end_date}")
                    
                    # 推荐的重点流媒体平台白名单（基于常见 RSS 压制源）
                    # 使用 set 提供 O(1) 的查找速度
                    TARGET_STREAMING_SITES = {
                        "gamer",           # 巴哈姆特動畫瘋 (繁中主力源)
                        "gamer_hk",        # 動畫瘋(港)
                        # "crunchyroll",     # Crunchyroll (欧美/多语言硬字幕主力源)
                        "bilibili",        # Bilibili (简中主力源)
                        "bilibili_tv",     # B-Global
                        "ani_one",         # Ani-One (YouTube流)
                        "ani_one_asia",
                        "netflix",         # 独占网飞源
                        "disneyplus",      # 独占迪士尼源
                        "unext",           # 日本主要网络先行平台
                        "abema"
                    }
                    
                    # 过滤并处理数据
                    items = data.get("items", [])
                    filtered_items = []
                    
                    for item in items:
                        # 1. 收集所有可能的有效时间字符串
                        valid_time_strs = []

                        # 先加入根目录的传统放送时间兜底
                        root_begin = item.get("begin")
                        if root_begin:
                            valid_time_strs.append(root_begin)

                        # 2. 遍历 sites，只收集白名单平台的时间字符串
                        for site in item.get("sites", []):
                            if site.get("site") in TARGET_STREAMING_SITES:
                                site_begin = site.get("begin")
                                if site_begin:
                                    valid_time_strs.append(site_begin)

                        # 3. 如果没有任何有效时间，直接跳过
                        if not valid_time_strs:
                            continue

                        # 4. 性能核心：利用字符串字典序直接找出最早的时间！
                        # min() 是 Python 底层 C 实现的，极快
                        earliest_time_str = min(valid_time_strs)

                        # 5. 全程只在这里执行唯一的一次 datetime 转换
                        begin_time = None
                        try:
                            begin_time = datetime.fromisoformat(earliest_time_str).astimezone(timezone.utc)
                        except ValueError as e:
                            logger.warning(f"解析最优时间失败: {earliest_time_str}, 错误: {e}")
                            continue
                                                
                        # 过滤时间范围
                        if not (start_date <= begin_time <= end_date):
                            continue
                        
                        # 提取 bangumi_id
                        bangumi_id = None
                        sites = item.get("sites", [])
                        for site in sites:
                            if site.get("site") == "bangumi":
                                try:
                                    bangumi_id = int(site.get("id"))
                                except ValueError as e:
                                    logger.warning(f"解析 bangumi_id 失败: {site.get('id')}, 错误: {e}")
                                break
                        
                        if not bangumi_id:
                            continue
                        
                        # 提取年份和季度
                        year = begin_time.year
                        month = begin_time.month
                        # 季度映射: 1月-3月为1，4月-6月为4，7月-9月为7，10月-12月为10
                        if 1 <= month <= 3:
                            season = 1
                        elif 4 <= month <= 6:
                            season = 4
                        elif 7 <= month <= 9:
                            season = 7
                        else:
                            season = 10
                        
                        # 添加到过滤列表
                        filtered_items.append({
                            "bangumi_id": bangumi_id,
                            "title": item.get("title", ""),
                            "broadcast_begin": begin_time,
                            "year": year,
                            "season": season
                        })
                    
                    logger.info(f"过滤后的数据条数: {len(filtered_items)}")
                    
                    if not filtered_items:
                        logger.warning("过滤后没有数据，尝试下一个数据源")
                        continue
                    
                    # 执行 Upsert 操作
                    synced_count = 0
                    for item in filtered_items:
                        try:
                            # 查询是否存在
                            query = select(AnimeBroadcastMetadata).where(
                                AnimeBroadcastMetadata.bangumi_id == item["bangumi_id"]
                            )
                            result = await db.execute(query)
                            existing_record = result.scalar_one_or_none()
                            
                            if existing_record:
                                # 更新记录
                                existing_record.broadcast_begin = item["broadcast_begin"]
                                existing_record.updated_at = datetime.now(timezone.utc)
                                logger.debug(f"更新记录: {item['bangumi_id']}")
                            else:
                                # 插入新记录
                                new_record = AnimeBroadcastMetadata(
                                    bangumi_id=item["bangumi_id"],
                                    title=item["title"],
                                    broadcast_begin=item["broadcast_begin"],
                                    broadcast_tz="Asia/Tokyo",
                                    year=item["year"],
                                    season=item["season"]
                                )
                                db.add(new_record)
                                logger.debug(f"插入新记录: {item['bangumi_id']}")
                            
                            synced_count += 1
                        except Exception as e:
                            logger.warning(f"处理记录失败 {item['bangumi_id']}: {type(e).__name__}: {e}")
                            continue
                    
                    # 提交事务
                    await db.commit()
                    logger.info(f"同步完成，处理了 {synced_count} 条记录")
                    return synced_count
                    
                except httpx.HTTPError as e:
                    # 捕获网络相关错误
                    logger.error(f"网络请求失败: {type(e).__name__}: {e}")
                    logger.error(f"错误详情: {str(e)}")
                    # 尝试下一个数据源
                    continue
                except json.JSONDecodeError as e:
                    # 捕获 JSON 解析错误
                    logger.error(f"JSON 解析失败: {type(e).__name__}: {e}")
                    # 尝试下一个数据源
                    continue
                except Exception as e:
                    # 捕获其他所有错误
                    logger.error(f"同步过程中发生错误: {type(e).__name__}: {e}")
                    logger.error(f"错误详情: {str(e)}")
                    # 尝试下一个数据源
                    continue
            
            # 所有数据源都失败，等待重试
            if attempt < max_retries - 1:
                logger.info(f"所有数据源都失败，{retry_delay} 秒后重试...")
                import asyncio
                await asyncio.sleep(retry_delay)
                retry_delay *= 2  # 指数退避
        
        # 所有重试都失败
        error_msg = f"所有重试都失败，无法同步 bangumi-data 数据"
        logger.error(error_msg)
        await db.rollback()
        raise Exception(error_msg)
    
    @classmethod
    async def get_air_time(
        cls, db: AsyncSession, bangumi_id: int, retry: bool = True
    ) -> Optional[Dict[str, Any]]:
        """
        获取番剧的放送时间
        
        Args:
            db: 数据库会话
            bangumi_id: Bangumi 的 subject_id
            retry: 是否在找不到数据时尝试同步
        
        Returns:
            包含 air_time 和 weekday 的字典，如果找不到返回 None
        """
        try:
            logger.info(f"查询番剧放送时间: {bangumi_id}")
            
            # 查询数据库
            query = select(AnimeBroadcastMetadata).where(
                AnimeBroadcastMetadata.bangumi_id == bangumi_id
            )
            result = await db.execute(query)
            record = result.scalar_one_or_none()
            
            if record:
                # 提取 air_time 和 weekday
                broadcast_begin = record.broadcast_begin
                air_time = broadcast_begin.time()
                # weekday() 返回 0-6，对应周一到周日
                weekday = broadcast_begin.weekday()
                
                logger.info(f"找到番剧放送时间: {air_time}, 星期: {weekday}")
                return {
                    "air_time": air_time,
                    "weekday": weekday
                }
            elif retry:
                # Fallback 机制：尝试同步数据
                logger.warning(f"未找到番剧放送时间，尝试同步数据: {bangumi_id}")
                await cls.fetch_and_sync_recent_data(db)
                
                # 再次查询
                return await cls.get_air_time(db, bangumi_id, retry=False)
            else:
                logger.warning(f"未找到番剧放送时间: {bangumi_id}")
                return None
        except Exception as e:
            logger.error(f"获取番剧放送时间失败: {e}")
            return None
    
    @classmethod
    async def get_air_time_batch(
        cls, db: AsyncSession, bangumi_ids: List[int]
    ) -> Dict[int, str]:
        """
        批量获取番剧的放送时间
        
        Args:
            db: 数据库会话
            bangumi_ids: Bangumi 的 subject_id 列表
        
        Returns:
            包含 bangumi_id 和放送时间的字典，格式为 {bangumi_id: "HH:MM"}
        """
        try:
            logger.info(f"批量查询番剧放送时间，共 {len(bangumi_ids)} 个 ID")
            
            # 批量查询数据库
            query = select(AnimeBroadcastMetadata).where(
                col(AnimeBroadcastMetadata.bangumi_id).in_(bangumi_ids)
            )
            result = await db.execute(query)
            records = result.scalars().all()
            
            logger.info(f"批量查询结果: {len(records)} 条记录")
            
            # 自动回退机制
            # 如果查询结果的数量远少于传入 ID 的数量，触发同步
            if len(records) < len(bangumi_ids) * 0.5:
                logger.warning(f"查询结果数量较少，尝试同步数据")
                await cls.fetch_and_sync_recent_data(db)
                
                # 重新查询
                query = select(AnimeBroadcastMetadata).where(
                    col(AnimeBroadcastMetadata.bangumi_id).in_(bangumi_ids)
                )
                result = await db.execute(query)
                records = result.scalars().all()
                
                logger.info(f"同步后查询结果: {len(records)} 条记录")
            
            # 构建返回字典
            result_dict: Dict[int, str] = {}
            current_date = datetime.now(timezone.utc)
            
            for record in records:
                # 提取放送时间，直接返回原始的 ISO 时间格式
                broadcast_begin = record.broadcast_begin
                # 转换为 ISO 格式字符串
                time_str = broadcast_begin.isoformat()
                result_dict[record.bangumi_id] = time_str
            
            logger.info(f"批量查询完成，返回 {len(result_dict)} 条记录")
            return result_dict
        except Exception as e:
            logger.error(f"批量获取番剧放送时间失败: {e}")
            return {}
