import requests
import json

# 测试1：正确的source值
def test_valid_source():
    print("=== 测试1：正确的source值 ===")
    url = "http://localhost:8000/api/v1/collections/sync"
    headers = {
        "Content-Type": "application/json"
    }
    
    data = {
        "source": "bgm",
        "subject_type": 2
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        print(f"响应状态码: {response.status_code}")
        print(f"响应内容: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 401:
            print("✅ 测试1通过：正确返回401未认证错误，而非500错误")
        else:
            print(f"❌ 测试1失败，状态码: {response.status_code}")
    except Exception as e:
        print(f"❌ 测试1失败: {str(e)}")
    print()

# 测试2：无效的source值
def test_invalid_source():
    print("=== 测试2：无效的source值 ===")
    url = "http://localhost:8000/api/v1/collections/sync"
    headers = {
        "Content-Type": "application/json"
    }
    
    data = {
        "source": "invalid_source",
        "subject_type": 2
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        print(f"响应状态码: {response.status_code}")
        print(f"响应内容: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 400:
            print("✅ 测试2通过：正确返回400错误，提示无效的source值")
        else:
            print(f"❌ 测试2失败，状态码: {response.status_code}")
    except Exception as e:
        print(f"❌ 测试2失败: {str(e)}")
    print()

# 测试3：缺少source值
def test_missing_source():
    print("=== 测试3：缺少source值 ===")
    url = "http://localhost:8000/api/v1/collections/sync"
    headers = {
        "Content-Type": "application/json"
    }
    
    data = {
        "subject_type": 2
    }
    
    try:
        response = requests.post(url, headers=headers, json=data)
        print(f"响应状态码: {response.status_code}")
        print(f"响应内容: {json.dumps(response.json(), indent=2)}")
        
        if response.status_code == 422:
            print("✅ 测试3通过：正确返回422错误，提示缺少必填的source字段")
        else:
            print(f"❌ 测试3失败，状态码: {response.status_code}")
    except Exception as e:
        print(f"❌ 测试3失败: {str(e)}")
    print()

# 运行所有测试
if __name__ == "__main__":
    print("开始测试同步API接口...")
    print("=" * 50)
    test_valid_source()
    test_invalid_source()
    test_missing_source()
    print("=" * 50)
    print("测试完成！")
