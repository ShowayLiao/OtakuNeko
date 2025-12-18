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

def test_no_data_update():
    """测试在没有数据时更新数据的情况"""
    print("=== 测试在没有数据时更新数据 ===")
    
    # 1. 确保没有数据文件
    test_username = "test_user"
    data_dir = "data"
    data_file = f"bangumi_{test_username}_records.json"
    data_path = os.path.join(data_dir, data_file)
    db_path = os.path.join(data_dir, "otaku_neko.db")
    
    # 清理旧数据（测试用，实际使用时不要删除用户数据）
    if os.path.exists(data_path):
        os.remove(data_path)
        print(f"已删除旧的JSON数据文件: {data_path}")
    
    # 2. 初始化服务
    bgm_service = BangumiService(username=test_username)
    
    # 3. 测试load_local_records
    print("\n1. 测试load_local_records方法:")
    records = bgm_service.load_local_records()
    print(f"   返回值类型: {type(records)}")
    print(f"   返回值长度: {len(records)}")
    print(f"   返回值: {records}")
    
    # 4. 测试save_records
    print("\n2. 测试save_records方法:")
    try:
        bgm_service.save_records([])
        print("   ✓ 保存空记录列表成功")
    except Exception as e:
        print(f"   ✗ 保存空记录列表失败: {e}")
    
    # 5. 测试run_sync（模拟空数据情况）
    print("\n3. 测试run_sync方法:")
    try:
        # 覆盖_fetch_user_collection_from_api方法返回空列表
        original_fetch = BangumiService._fetch_user_collection_from_api
        BangumiService._fetch_user_collection_from_api = lambda *_: []
        
        result = bgm_service.run_sync()
        print(f"   ✓ run_sync执行成功: {result}")
        
        # 恢复原始方法
        BangumiService._fetch_user_collection_from_api = original_fetch
    except Exception as e:
        print(f"   ✗ run_sync执行失败: {e}")
    
    print("\n=== 测试完成 ===")

if __name__ == "__main__":
    test_no_data_update()
