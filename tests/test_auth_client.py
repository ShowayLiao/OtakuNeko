#!/usr/bin/env python3
"""
AuthClient 示例脚本，展示如何使用 AuthClient 类测试后端 API

这个脚本演示了：
1. 初始化 AuthClient
2. 登录获取认证
3. 使用已认证的客户端发送请求
4. 清除认证信息
"""

import sys
from auth_client import AuthClient


def main():
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
        print(f"用户信息: {login_response['user']}")
        
        print("\n=== 获取已认证客户端 ===")
        # 获取已认证的会话客户端
        session = auth_client.get_authenticated_client()
        print(f"已获取已认证客户端，Authorization头: {session.headers.get('Authorization')}")
        
        print("\n=== 测试API请求 ===")
        # 这里可以添加实际的API测试，例如获取用户信息或其他需要认证的接口
        # 示例：获取当前用户信息（假设存在 /api/v1/users/me 接口）
        # user_me_response = session.get(f"{base_url}/api/v1/users/me")
        # if user_me_response.status_code == 200:
        #     print(f"获取用户信息成功: {user_me_response.json()}")
        # else:
        #     print(f"获取用户信息失败: {user_me_response.status_code} {user_me_response.text}")
        
        print("\n=== 清除认证信息 ===")
        auth_client.clear_auth()
        print(f"已清除认证信息，Token: {auth_client.get_token()}")
        print(f"当前用户信息: {auth_client.get_current_user()}")
        
        print("\n=== 测试完成 ===")
        print("AuthClient 示例脚本执行成功！")
        
    except Exception as e:
        print(f"发生错误: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    sys.exit(main())