#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试数据库重构功能
"""

import sys
import os

# 添加项目根目录到 Python 路径
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from src.database import DatabaseManager
from src.BgmServe import BangumiService

def test_database_manager():
    """测试 DatabaseManager 类"""
    print("=== 测试 DatabaseManager 类 ===")
    
    # 创建数据库管理器实例
    db_manager = DatabaseManager()
    
    # 测试用户管理
    username = "test_user"
    user_id = db_manager.get_user_id(username)
    print(f"创建/获取用户 '{username}'，ID: {user_id}")
    
    # 测试保存记录
    test_records = [
        {
            "id": 12345,
            "title": "测试动漫1",
            "type": "anime",
            "status": "watching",
            "score": 8,
            "tags": ["测试", "动漫"],
            "summary": "这是一个测试动漫",
            "image": "https://example.com/image.jpg",
            "updated_at": "2025-12-18T10:00:00+08:00",
            "director": "测试导演",
            "script": "测试编剧",
            "studio": "测试工作室",
            "cv": "测试声优"
        },
        {
            "id": 67890,
            "title": "测试动漫2",
            "type": "anime",
            "status": "watched",
            "score": 9,
            "tags": ["测试", "动漫", "完结"],
            "summary": "这是另一个测试动漫",
            "image": "https://example.com/image2.jpg",
            "updated_at": "2025-12-18T11:00:00+08:00",
            "director": "测试导演2",
            "script": "测试编剧2",
            "studio": "测试工作室2",
            "cv": "测试声优2"
        }
    ]
    
    print("保存测试记录...")
    db_manager.save_records(username, test_records)
    
    # 测试读取记录
    print("读取测试记录...")
    records = db_manager.load_records(username)
    print(f"读取到 {len(records)} 条记录")
    for record in records:
        print(f"  - {record['title']} (ID: {record['id']}, 状态: {record['status']})")
    
    print("DatabaseManager 测试完成！")

def test_bangumi_service():
    """测试 BangumiService 类"""
    print("\n=== 测试 BangumiService 类 ===")
    
    # 创建 BangumiService 实例
    bgm_service = BangumiService(username="hacci")
    
    # 测试加载本地记录（应该会自动迁移JSON数据）
    print("加载本地记录...")
    records = bgm_service.load_local_records()
    print(f"加载到 {len(records)} 条动漫记录")
    
    # 如果有记录，打印前3条
    if records:
        print("前3条记录：")
        for i, record in enumerate(records[:3]):
            print(f"  {i+1}. {record['title']} (ID: {record['id']}, 状态: {record['status']})")
    
    print("BangumiService 测试完成！")

if __name__ == "__main__":
    try:
        test_database_manager()
        test_bangumi_service()
        print("\n🎉 所有测试通过！")
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()