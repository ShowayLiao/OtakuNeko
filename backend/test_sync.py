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
    
    # 测试同步用户数据（BGM）
    print("\nTesting sync user data (BGM)...")
    sync_url = "http://localhost:8000/api/v1/collections/sync"
    headers = {"Authorization": f"Bearer {token}"}
    sync_data = {"source": "bgm", "subject_type": 2}
    sync_response = requests.post(sync_url, json=sync_data, headers=headers)
    print(f"Sync status code: {sync_response.status_code}")
    print(f"Sync response: {sync_response.text}")
    
    # 测试同步用户数据（豆瓣）
    print("\nTesting sync user data (Douban)...")
    douban_data = [{
      "rating": {"value": "8.5"},
      "type": "movie",
      "title": "测试电影",
      "url": "https://movie.douban.com/subject/123456/",
      "cover_url": "https://example.com/cover.jpg",
      "summary": "测试电影简介",
      "pubdate": "2023-01-01",
      "status": "watched"
    }]
    sync_data_douban = {"source": "douban", "subject_type": 6, "data": douban_data}
    sync_response_douban = requests.post(sync_url, json=sync_data_douban, headers=headers)
    print(f"Sync Douban status code: {sync_response_douban.status_code}")
    print(f"Sync Douban response: {sync_response_douban.text}")
