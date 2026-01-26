#!/usr/bin/env python3
"""
测试 BGM 同步函数
"""

import asyncio
import logging
from app.services.bangumi_service import sync_user_collections
from app.db.database import get_session
from app.schemas.collection import CollectionSyncRequest

# 设置日志级别
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_sync_user_collections():
    """测试 sync_user_collections 函数"""
    print("=== 测试 sync_user_collections 函数 ===")
    
    db = None
    try:
        # 获取数据库会话
        async for db in get_session():
            # 创建测试请求数据
            request_data = CollectionSyncRequest(
                subject_type=None,
                limit=50,
                offset=0
            )
            
            # 调用 sync_user_collections 函数
            sync_count = await sync_user_collections("hacci", db, request_data)
            
            print(f"同步成功！同步了 {sync_count} 条记录")
            return True
    except Exception as e:
        print(f"同步失败: {e}")
        logger.exception("同步失败的详细信息:")
        return False

if __name__ == "__main__":
    asyncio.run(test_sync_user_collections())
