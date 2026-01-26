#!/usr/bin/env python3
"""
豆瓣收藏导入功能测试脚本

测试app/api/v1/collections.py中的豆瓣导入功能
"""

import sys
import json
import requests


class DoubanImportTester:
    def __init__(self, base_url="http://localhost:8000"):
        self.base_url = base_url
        self.session = requests.Session()
        self.access_token = None
    
    def login(self):
        """登录获取访问令牌"""
        print("=== 登录测试 ===")
        login_url = f"{self.base_url}/api/v1/auth/login"
        login_data = {
            "username": "test_user",
            "nickname": "测试用户",
            "sign": "这是一个测试签名"
        }
        
        response = self.session.post(login_url, json=login_data)
        if response.status_code == 200:
            result = response.json()
            self.access_token = result.get("access_token")
            print(f"✅ 登录成功！")
            print(f"Token: {self.access_token}")
            return True
        else:
            print(f"❌ 登录失败: {response.status_code} {response.text}")
            return False
    
    def test_douban_import(self, douban_file):
        """测试豆瓣收藏导入功能"""
        print("\n=== 测试豆瓣导入功能 ===")
        
        # 读取豆瓣数据文件
        print(f"📁 读取豆瓣数据文件: {douban_file}")
        try:
            with open(douban_file, 'r', encoding='utf-8') as f:
                douban_data = json.load(f)
            print(f"✅ 读取成功，包含 {len(douban_data.get('interest', []))} 条记录")
        except Exception as e:
            print(f"❌ 读取文件失败: {e}")
            return False
        
        # 提取interest数组
        interest_list = douban_data.get('interest', [])
        if not interest_list:
            print("❌ 数据中没有找到interest数组")
            return False
        
        # 构建请求数据
        request_data = {
            "subject_type": None,  # 不指定类型，导入所有类型
            "data": interest_list
        }
        
        # 设置请求头
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }
        
        # 发送请求
        import_url = f"{self.base_url}/api/v1/collections/upload/douban"
        print(f"🚀 发送请求到: {import_url}")
        print(f"📊 导入记录数: {len(interest_list)}")
        
        response = self.session.post(import_url, json=request_data, headers=headers)
        
        # 处理响应
        if response.status_code == 200:
            result = response.json()
            print(f"✅ 导入成功！")
            print(f"📈 导入结果: {result}")
            return True
        else:
            print(f"❌ 导入失败: {response.status_code}")
            print(f"💬 响应内容: {response.text}")
            return False
    
    def run_test(self, douban_file):
        """运行完整测试流程"""
        if not self.login():
            return False
        
        return self.test_douban_import(douban_file)


if __name__ == "__main__":
    # 豆瓣数据文件路径
    douban_file = r"e:\HACCI\Documents\tools\OtakuNeko\tofu[208745052].json"
    
    tester = DoubanImportTester()
    tester.run_test(douban_file)
