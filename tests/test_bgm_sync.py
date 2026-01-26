#!/usr/bin/env python3
"""
BGM同步功能测试脚本

这个脚本只测试以下 API 端点：
POST /api/v1/collections/sync/bgm - 同步 BGM 收藏
"""

import sys
import json
from auth_client import AuthClient


def test_sync_bgm(auth_client):
    """测试同步 BGM 收藏 API"""
    print(f"\n=== 测试同步 BGM 收藏 API ===")
    
    session = auth_client.get_authenticated_client()
    base_url = auth_client.base_url
    
    # 测试同步 BGM 收藏
    sync_data = {
        "subject_type": None,
        "limit": 5,
        "offset": 0
    }
    
    sync_response = session.post(f"{base_url}/api/v1/collections/sync/bgm", json=sync_data)
    
    if sync_response.status_code == 200:
        sync_result = sync_response.json()
        print(f"同步 BGM 收藏成功！")
        print(f"同步结果: {sync_result}")
        return True
    else:
        print(f"同步 BGM 收藏失败: {sync_response.status_code} {sync_response.text}")
        return False


def main():
    """主测试函数"""
    # 设置基础URL，根据实际情况修改
    base_url = "http://localhost:8000"
    
    # 初始化AuthClient
    auth_client = AuthClient(base_url)
    
    try:
        print("=== 登录测试 ===")
        # 登录，使用测试用户名
        login_response = auth_client.login(
            username="test_user",
            nickname="测试用户",
            sign="这是一个测试签名"
        )
        print(f"登录成功！")
        print(f"Token: {login_response['access_token']}")
        
        # 执行测试用例
        test_results = {
            "sync_bgm": test_sync_bgm(auth_client)
        }
        
        print("\n=== 测试结果汇总 ===")
        for test_name, result in test_results.items():
            status = "通过" if result else "失败"
            print(f"{test_name}: {status}")
        
        # 计算通过率
        passed = sum(test_results.values())
        total = len(test_results)
        print(f"\n总测试数: {total}, 通过数: {passed}, 通过率: {passed/total*100:.1f}%")
        
        print("\n=== 清除认证信息 ===")
        auth_client.clear_auth()
        print(f"已清除认证信息")
        
        print("\n=== 测试完成 ===")
        return 0
        
    except Exception as e:
        print(f"发生错误: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
