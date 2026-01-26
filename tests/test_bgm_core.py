#!/usr/bin/env python3
"""
BGM同步核心功能测试脚本

这个脚本直接测试BGM同步的核心逻辑，跳过数据库和API服务器部分：
1. 测试从Bangumi API获取数据
2. 测试数据转换逻辑
"""

import sys
import os

# 添加backend目录到Python路径
# backend目录在项目根目录，而不是在tests目录中
tests_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(tests_dir)
backend_dir = os.path.join(project_root, 'backend')
sys.path.insert(0, backend_dir)
print(f"项目根目录: {project_root}")
print(f"添加到Python路径的backend目录: {backend_dir}")
print(f"当前Python路径: {sys.path}")

import asyncio
import httpx
import json
from app.services.bangumi_client import fetch_user_collections
from app.schemas.adapters import adapt_bangumi_collection_to_list


async def test_bgm_api_access():
    """测试访问Bangumi API"""
    print("=== 测试访问Bangumi API ===")
    
    username = "hacci"
    try:
        # 调用fetch_user_collections函数，获取用户收藏数据
        response_json = await fetch_user_collections(username, limit=5, offset=0)
        
        print(f"✅ Bangumi API访问成功")
        print(f"✅ 返回数据类型: {type(response_json)}")
        print(f"✅ 总记录数: {response_json.get('total', 0)}")
        print(f"✅ 本次返回记录数: {len(response_json.get('data', []))}")
        
        # 打印第一条记录，查看数据结构
        if response_json.get('data'):
            first_item = response_json['data'][0]
            print(f"✅ 第一条记录: {json.dumps(first_item, ensure_ascii=False, indent=2)}")
        
        return response_json
    except Exception as e:
        print(f"❌ Bangumi API访问失败: {e}")
        import traceback
        traceback.print_exc()
        return None


async def test_data_adapter():
    """测试数据转换逻辑"""
    print("\n=== 测试数据转换逻辑 ===")
    
    # 首先获取数据
    response_json = await test_bgm_api_access()
    if not response_json:
        return False
    
    try:
        # 调用adapt_bangumi_collection_to_list函数，转换数据
        collections_list = adapt_bangumi_collection_to_list(response_json)
        
        print(f"✅ 数据转换成功")
        print(f"✅ 转换后类型: {type(collections_list)}")
        print(f"✅ 转换后总记录数: {collections_list.total}")
        print(f"✅ 转换后条目数: {len(collections_list.items)}")
        
        # 打印第一条转换后的记录
        if collections_list.items:
            first_item = collections_list.items[0]
            print(f"✅ 第一条转换后记录: {first_item}")
        
        return True
    except Exception as e:
        print(f"❌ 数据转换失败: {e}")
        import traceback
        traceback.print_exc()
        return False


async def main():
    """主测试函数"""
    print("=== BGM同步核心功能测试 ===")
    
    # 测试数据适配器
    success = await test_data_adapter()
    
    print(f"\n=== 测试结果 ===")
    if success:
        print("✅ BGM同步核心功能测试通过")
        return 0
    else:
        print("❌ BGM同步核心功能测试失败")
        return 1


if __name__ == "__main__":
    asyncio.run(main())
