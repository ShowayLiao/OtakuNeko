# src/services.py
import os
import json
import time
import datetime
from openai import OpenAI
from src.bgm_sync import sync_bangumi_to_local
from src.prompt_manager import get_system_prompt

# 常量定义
DATA_FILE = os.path.join("data", "bangumi_full_records.json")
SYNC_INTERVAL = 43200  # 12小时




class DataService:
    @staticmethod
    def should_sync():
        """判断是否需要同步"""
        if not os.path.exists(DATA_FILE):
            return True, "📂 初次初始化数据..."
        
        mtime = os.path.getmtime(DATA_FILE)
        if time.time() - mtime > SYNC_INTERVAL:
            return True, "🔄 数据已过期，准备同步 Bangumi..."
            
        return False, ""

        # return True,"测试..."

    @staticmethod
    def perform_sync():
        """执行同步操作"""
        return sync_bangumi_to_local()

    @staticmethod
    def load_and_filter_memory():
        """
        核心数据清洗逻辑：
        读取文件 -> 剔除已看/抛弃/低分 -> 返回适合 LLM 的 List
        """
        if not os.path.exists(DATA_FILE):
            return []

        try:
            with open(DATA_FILE, "r", encoding='utf-8') as f:
                data = json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []

        valid_candidates = []
        for item in data:
            status = item.get('status')
            score = item.get('score', 0)

            # 1. 剔除已看和抛弃
            if status in ['watched', 'dropped']:
                continue
            
            # 2. 剔除低分 (除非是想看 wish 且还没分)
            if score > 0 and score < 6.0:
                continue

            # 3. 字段瘦身
            valid_candidates.append({
                "title": item['title'],
                "score": item['score'],
                "status": item['status'],
                "tags": item.get('tags', [])[:3],
                "summary": item.get('summary', '')[:80]
            })

        # 排序优化：优先展示 'watching' 和 'on_hold'
        valid_candidates.sort(key=lambda x: 0 if x['status'] in ['watching', 'on_hold'] else 1)
        
        # 限制数量防止 Token 爆炸
        return valid_candidates[:40]

class LLMService:
    def __init__(self, api_key, base_url="https://api.deepseek.com"):
        self.client = OpenAI(api_key=api_key, base_url=base_url)

    def get_streaming_response(self, user_query, history_messages, memory_data):
        """
        组装 Prompt 并发起流式请求
        """
        # 1. 准备 System Prompt
        now_str = datetime.datetime.now().strftime("%Y年%m月%d日 %A")
        memory_str = json.dumps(memory_data, ensure_ascii=False)
        sys_content = get_system_prompt(now_str, memory_str)

        # 2. 组装消息链
        messages = [{"role": "system", "content": sys_content}] + \
                   history_messages + \
                   [{"role": "user", "content": user_query}]

        # 3. 发起请求
        return self.client.chat.completions.create(
            model="deepseek-chat",
            messages=messages,
            temperature=1.3,
            stream=True
        )