#!/usr/bin/env python3
"""
Dashboard API 自动化测试脚本

这个脚本测试以下 API 端点：
1. GET /api/v1/dashboard/stats - 获取用户仪表板统计数据
"""

import sys
from auth_client import AuthClient


def test_get_user_stats(auth_client):
    """测试获取用户仪表板统计数据 API"""
    print("=== 测试获取用户仪表板统计数据 API ===")
    
    session = auth_client.get_authenticated_client()
    base_url = auth_client.base_url
    
    # 测试获取用户仪表板统计数据
    get_response = session.get(f"{base_url}/api/v1/dashboard/stats")
    
    if get_response.status_code == 200:
        get_result = get_response.json()
        print(f"获取成功！")
        print(f"响应数据: {get_result}")
        
        # 验证响应数据格式
        expected_fields = ['anime', 'book', 'music', 'game', 'real']
        for field in expected_fields:
            if field in get_result:
                print(f"  ✅ 包含字段: {field} = {get_result[field]}")
            else:
                print(f"  ❌ 缺少字段: {field}")
                return False
        
        return True
    else:
        print(f"获取失败: {get_response.status_code} {get_response.text}")
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
        test_results = {}
        
        # 测试获取用户仪表板统计数据
        test_results["get_user_stats"] = test_get_user_stats(auth_client)
        
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
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
