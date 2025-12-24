import requests

# 测试syncUser API
def test_sync_user():
    print("Testing syncUser API...")
    url = "http://localhost:8000/api/v1/collections/sync"
    params = {"username": "hacci"}
    
    try:
        response = requests.post(url, params=params)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error: {e}")
        return False

# 测试fetchDashboardStats API
def test_dashboard_stats():
    print("\nTesting dashboard stats API...")
    url = "http://localhost:8000/api/v1/dashboard/stats"
    
    try:
        response = requests.get(url)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error: {e}")
        return False

# 测试subjects搜索API
def test_subjects_search():
    print("\nTesting subjects search API...")
    url = "http://localhost:8000/api/v1/subjects/"
    params = {"keyword": "test"}
    
    try:
        response = requests.get(url, params=params)
        print(f"Status Code: {response.status_code}")
        print(f"Response: {response.json()}")
        return response.status_code == 200
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    sync_result = test_sync_user()
    stats_result = test_dashboard_stats()
    search_result = test_subjects_search()
    
    print("\n=== Test Results ===")
    print(f"syncUser API: {'PASS' if sync_result else 'FAIL'}")
    print(f"Dashboard Stats API: {'PASS' if stats_result else 'FAIL'}")
    print(f"Subjects Search API: {'PASS' if search_result else 'FAIL'}")
    
    if sync_result and stats_result and search_result:
        print("\n🎉 All APIs are working correctly!")
    else:
        print("\n❌ Some APIs are not working correctly!")