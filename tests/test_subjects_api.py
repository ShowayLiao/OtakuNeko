#!/usr/bin/env python3
"""
Subjects API 自动化测试脚本

这个脚本测试以下 API 端点：
1. GET /api/v1/subjects - 搜索 subjects
2. POST /api/v1/subjects - 创建 subject
3. GET /api/v1/subjects/{subject_id} - 获取 subject
4. PUT /api/v1/subjects/{subject_id} - 更新 subject
5. DELETE /api/v1/subjects/{subject_id} - 删除 subject
"""

import sys
import json
from auth_client import AuthClient


def test_search_subjects(auth_client):
    """测试搜索 subjects API"""
    print("=== 测试搜索 Subjects API ===")
    
    session = auth_client.get_authenticated_client()
    base_url = auth_client.base_url
    
    # 测试搜索功能
    search_response = session.get(f"{base_url}/api/v1/subjects?limit=5")
    
    if search_response.status_code == 200:
        search_result = search_response.json()
        print(f"搜索成功！")
        print(f"总记录数: {search_result['total']}")
        print(f"返回记录数: {len(search_result['items'])}")
        if search_result['items']:
            first_item = search_result['items'][0]
            print(f"第一条记录: {first_item}")
        else:
            print(f"第一条记录: 无记录")
        return True
    else:
        print(f"搜索失败: {search_response.status_code} {search_response.text}")
        return False


def test_create_subject(auth_client):
    """测试创建 subject API"""
    print("\n=== 测试创建 Subject API ===")
    
    session = auth_client.get_authenticated_client()
    base_url = auth_client.base_url
    
    # 测试创建 subject
    new_subject = {
        "source": "test",
        "source_id": "12345",
        "name": "测试条目",
        "name_cn": "Test Subject",
        "type": 2,
        "date": "2023-01-01",
        "rank": 1,
        "score": 8.5,
        "image": "https://example.com/image.jpg",
        "summary": "这是一个测试条目"
    }
    
    create_response = session.post(f"{base_url}/api/v1/subjects", json=new_subject)
    
    if create_response.status_code == 200:
        created_subject = create_response.json()
        print(f"创建成功！")
        print(f"创建的条目: {created_subject}")
        return created_subject
    else:
        print(f"创建失败: {create_response.status_code} {create_response.text}")
        return None


def test_get_subject(auth_client, source_id):
    """测试获取 subject API"""
    print(f"\n=== 测试获取 Subject API ===")
    
    session = auth_client.get_authenticated_client()
    base_url = auth_client.base_url
    
    # 测试获取 subject
    get_response = session.get(f"{base_url}/api/v1/subjects/{source_id}?source=test")
    
    if get_response.status_code == 200:
        subject_data = get_response.json()
        print(f"获取成功！")
        print(f"条目信息: {subject_data}")
        return True
    else:
        print(f"获取失败: {get_response.status_code} {get_response.text}")
        return False


def test_update_subject(auth_client, source_id):
    """测试更新 subject API"""
    print(f"\n=== 测试更新 Subject API ===")
    
    session = auth_client.get_authenticated_client()
    base_url = auth_client.base_url
    
    # 测试更新 subject
    update_data = {
        "name": "更新后的测试条目",
        "name_cn": "Updated Test Subject",
        "source": "test",
        "source_id": source_id,
        "score": 9.0
    }
    
    update_response = session.put(f"{base_url}/api/v1/subjects/{source_id}?source=test", json=update_data)
    
    if update_response.status_code == 200:
        updated_subject = update_response.json()
        print(f"更新成功！")
        print(f"更新后的条目: {updated_subject}")
        return True
    else:
        print(f"更新失败: {update_response.status_code} {update_response.text}")
        return False


def test_delete_subject(auth_client, source_id):
    """测试删除 subject API"""
    print(f"\n=== 测试删除 Subject API ===")
    
    session = auth_client.get_authenticated_client()
    base_url = auth_client.base_url
    
    # 测试删除 subject
    delete_response = session.delete(f"{base_url}/api/v1/subjects/{source_id}?source=test")
    
    if delete_response.status_code == 200:
        delete_result = delete_response.json()
        print(f"删除成功！")
        print(f"删除结果: {delete_result['message']}")
        return True
    else:
        print(f"删除失败: {delete_response.status_code} {delete_response.text}")
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
            "search": test_search_subjects(auth_client),
            "create": False,
            "get": False,
            "update": False,
            "delete": False
        }
        
        # 创建一个subject用于后续测试
        created_subject = test_create_subject(auth_client)
        if created_subject:
            test_results["create"] = True
            
            source_id = created_subject["source_id"]
            
            # 测试获取subject
            test_results["get"] = test_get_subject(auth_client, source_id)
            
            # 测试更新subject
            test_results["update"] = test_update_subject(auth_client, source_id)
            
            # 测试删除subject
            test_results["delete"] = test_delete_subject(auth_client, source_id)
        
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
