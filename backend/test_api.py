import requests
import json

# 测试登录
print("Testing login...")
login_url = "http://localhost:8000/api/v1/auth/login"
login_data = {"username": "testuser1"}
login_response = requests.post(login_url, json=login_data)
print(f"Login status code: {login_response.status_code}")
print(f"Login response: {login_response.json()}")

if login_response.status_code == 200:
    # 获取 JWT 令牌
    token = login_response.json()["access_token"]
    print(f"\nToken: {token}")
    
    # 测试获取收藏列表
    print("\nTesting get collections...")
    collections_url = "http://localhost:8000/api/v1/collections"
    headers = {"Authorization": f"Bearer {token}"}
    collections_response = requests.get(collections_url, headers=headers)
    print(f"Collections status code: {collections_response.status_code}")
    print(f"Collections response: {collections_response.json()}")
