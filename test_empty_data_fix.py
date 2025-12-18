#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试在没有数据时更新数据是否会报错
"""

import os
import sys
import json

# 添加项目根目录到Python路径
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from src.BgmServe import BangumiService
from src.database import DatabaseManager

def test_empty_data_scenario():
    """测试在没有数据时的各种操作场景"""
    print("=== 测试没有数据时的操作场景 ===")
    
    # 1. 初始化服务
    test_username = "test_empty_data"
    bgm_service = BangumiService(username=test_username)
    
    # 2. 测试load_local_records - 应该返回空列表
    print("\n1. 测试load_local_records:")
    records = bgm_service.load_local_records()
    assert isinstance(records, list), f"Expected list, got {type(records)}"
    assert len(records) == 0, f"Expected empty list, got {len(records)} records"
    print("   ✓ 正确返回空列表")
    
    # 3. 测试save_records - 空列表应该被正确处理
    print("\n2. 测试save_records(空列表):")
    try:
        bgm_service.save_records([])
        print("   ✓ 空列表保存成功")
    except Exception as e:
        print(f"   ✗ 空列表保存失败: {e}")
        return False
    
    # 4. 测试save_records - 单条记录应该被正确保存
    print("\n3. 测试save_records(单条记录):")
    test_record = {
        "id": 12345,
        "title": "测试动漫",
        "type": "anime",
        "status": "watched",
        "score": 8,
        "tags": ["测试", "动画"],
        "summary": "这是一个测试动漫",
        "image": "",
        "updated_at": "2025-12-18T00:00:00+08:00",
        "director": "测试导演",
        "script": "测试编剧",
        "studio": "测试工作室",
        "cv": "测试声优"
    }
    
    try:
        bgm_service.save_records([test_record])
        print("   ✓ 单条记录保存成功")
        
        # 验证保存是否成功
        saved_records = bgm_service.load_local_records()
        assert len(saved_records) == 1, f"Expected 1 record, got {len(saved_records)}"
        assert saved_records[0]["id"] == 12345, f"Expected record with id 12345, got {saved_records[0]["id"]}"
        print("   ✓ 保存的记录可以正确读取")
    except Exception as e:
        print(f"   ✗ 单条记录保存失败: {e}")
        return False
    
    # 5. 测试更新现有记录
    print("\n4. 测试更新现有记录:")
    updated_record = test_record.copy()
    updated_record["score"] = 10  # 更新评分
    updated_record["updated_at"] = "2025-12-18T01:00:00+08:00"
    
    try:
        bgm_service.save_records([updated_record])
        print("   ✓ 记录更新成功")
        
        # 验证更新是否成功
        saved_records = bgm_service.load_local_records()
        assert len(saved_records) == 1, f"Expected 1 record, got {len(saved_records)}"
        assert saved_records[0]["score"] == 10, f"Expected score 10, got {saved_records[0]["score"]}"
        print("   ✓ 更新的记录可以正确读取")
    except Exception as e:
        print(f"   ✗ 记录更新失败: {e}")
        return False
    
    print("\n=== 所有测试通过！修复成功！ ===")
    return True

if __name__ == "__main__":
    success = test_empty_data_scenario()
    sys.exit(0 if success else 1)
