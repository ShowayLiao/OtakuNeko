# src/services.py
import os
import json
import time
import datetime
from typing import List, Dict, Any, Tuple
from openai import OpenAI

# 🟢 引入统一的数据服务单例
from src.BgmServe import BangumiService
from src.config.personas import TEMPLATES

class DataService:
    """
    数据协调服务：负责判断同步时机、调用底层同步、以及为 LLM 准备上下文数据
    """
    
    SYNC_INTERVAL = 43200  # 12小时 (12 * 60 * 60)
    
    # Cache for memory data
    _memory_cache = None
    _memory_cache_time = 0
    _cache_ttl = 300  # 5 minutes cache TTL

    @staticmethod
    def should_sync(bgm_service: BangumiService) -> Tuple[bool, str]:
        """判断是否需要自动同步"""
        data_path = bgm_service.data_path
        
        # 1. 文件不存在，强制同步
        if not os.path.exists(data_path):
            return True, "📂 初次初始化数据..."
        
        # 2. 文件过期，需要同步
        try:
            mtime = os.path.getmtime(data_path)
            if time.time() - mtime > DataService.SYNC_INTERVAL:
                return True, "🔄 数据已过期，准备自动同步..."
        except OSError:
            return True, "⚠️ 读取文件状态失败，准备重试..."
            
        return False, ""
    
    @staticmethod
    def invalidate_cache():
        """Invalidate the memory cache"""
        DataService._memory_cache = None
        DataService._memory_cache_time = 0

    @staticmethod
    def perform_sync(bgm_service: BangumiService, deep_sync=True):
        """执行同步操作 (代理到 bgm_service)"""
        return bgm_service.run_sync(deep_sync=deep_sync)

    @staticmethod
    def load_and_filter_memory(bgm_service: BangumiService) -> List[Dict[str, Any]]:
        """
        核心数据清洗逻辑：
        为 LLM 的 [CHAT] 模式准备“待看/在看”清单。
        逻辑：
        1. 读取全量数据
        2. 剔除已看(watched)/抛弃(dropped) -> 剩下的就是 Wish/Watching/OnHold
        3. 剔除低分垃圾作
        4. 字段瘦身，减少 Token 消耗
        """
        # Check cache first
        current_time = time.time()
        if (DataService._memory_cache is not None and 
            current_time - DataService._memory_cache_time < DataService._cache_ttl):
            return DataService._memory_cache
        
        try:
            # 直接利用 Service 读取，无需自己 open file
            all_records = bgm_service.load_local_records()
            if not all_records:
                return []

            valid_candidates = []
            
            for item in all_records:
                status = item.get('status')
                score = item.get('score', 0)

                # 1. 过滤状态: 只保留 在看(3), 想看(1), 搁置(4)
                #    原逻辑是剔除 watched/dropped，效果一样
                if status in ['watched', 'dropped']:
                    continue
                
                # 2. 剔除已评分且分低的 (可能是搁置的烂片)
                #    注意：score 为 0 表示未评分 (通常是新番或想看)
                if score > 0 and score < 6.0:
                    continue

                # 3. 字段瘦身 (只保留 LLM 需要的核心信息)
                valid_candidates.append({
                    "title": item['title'],
                    "score": item['score'],
                    "status": item['status'], # watching / wish / on_hold
                    "tags": item.get('tags', [])[:3], # 只取前3个标签
                    "summary": (item.get('summary') or '')[:100] # 限制简介长度
                })

            # 4. 排序优化：优先展示 'watching'(在看) 和 'on_hold'(搁置)
            #    让 LLM 优先聊这些，而不是沉在底下的几千个 'wish'
            status_priority = {'watching': 0, 'on_hold': 1, 'wish': 2}
            valid_candidates.sort(key=lambda x: status_priority.get(x['status'], 99))
            
            # 5. 截断：最多返回前 40 条，防止 System Prompt 过长
            result = valid_candidates[:40]
            
            # Update cache
            DataService._memory_cache = result
            DataService._memory_cache_time = current_time
            
            return result
        except Exception as e:
            print(f"⚠️ 数据清洗过程中出现错误: {e}")
            import traceback
            traceback.print_exc()
            return []


class LLMService:
    """
    LLM 交互服务：负责组装 Prompt 并调用 OpenAI 兼容接口
    """
    def __init__(self, api_key: str, base_url: str, chat_model: str, reasoner_model: str):
        # Validate API key
        if not api_key or not api_key.strip():
            raise ValueError("API key is required and cannot be empty")
        
        # Validate base URL
        if not base_url or not base_url.strip():
            raise ValueError("Base URL is required and cannot be empty")
        
        # Validate model names
        if not chat_model or not chat_model.strip():
            raise ValueError("Chat model name is required and cannot be empty")
        if not reasoner_model or not reasoner_model.strip():
            raise ValueError("Reasoner model name is required and cannot be empty")
        
        self.client = OpenAI(api_key=api_key.strip(), base_url=base_url.strip())
        self.chat_model = chat_model.strip()
        self.reasoner_model = reasoner_model.strip()

        print("🤖 LLMService Initialized:")
        print(f"   - Base URL: {base_url}")
        print(f"   - Chat Model: {self.chat_model}")
        print(f"   - Reasoner Model: {self.reasoner_model}")

    def _build_system_prompt(self, memory_data: List[Dict]) -> str:
        """内部方法：构建动态 System Prompt"""
        
        # 1. 准备参数
        now_str = datetime.datetime.now().strftime("%Y年%m月%d日 %A")
        memory_str = json.dumps(memory_data, ensure_ascii=False)
        
        # 2. 🟢 从配置模板加载并填充
        try:
            return TEMPLATES["chat_system"].format(
                now_str=now_str, 
                memory_str=memory_str
            )
        except KeyError:
            # 兜底：万一配置文件里没写
            return f"你是一个二次元助手。当前时间: {now_str}。请根据用户数据回答。"

    def get_streaming_response(self, user_query: str, history_messages: List[Dict], memory_data: List[Dict]):
        """
        组装 Prompt 并发起流式请求
        Args:
            user_query: 用户最新输入
            history_messages: 上下文历史 [{"role":..., "content":...}]
            memory_data: 由 DataService 清洗过的上下文数据
        """
        # 1. 动态生成 System Prompt
        sys_content = self._build_system_prompt(memory_data)

        # 2. 组装消息链 (System -> History -> User)
        # 注意：这里我们不仅包含历史，还把 System Prompt 放在最前面
        messages = [{"role": "system", "content": sys_content}]
        
        # 过滤 history 中的非法字段 (Streamlit 的 session state 可能包含额外字段)
        for msg in history_messages:
            if msg.get("role") in ["user", "assistant"]:
                messages.append({
                    "role": msg["role"], 
                    "content": str(msg["content"])
                })
        
        messages.append({"role": "user", "content": user_query})

        # 3. 发起请求
        try:
            return self.client.chat.completions.create(
                model=self.chat_model,
                messages=messages,
                temperature=1.3, # 稍微高一点的温度，让闲聊更有趣
                stream=True,
                timeout=30
            )
        except Exception as e:
            # 如果是温度参数错误，降级到 1.0 重试
            if "temperature" in str(e).lower() and ("400" in str(e) or "invalid" in str(e).lower()):
                print(f"[LLMService] Temperature 降级重试 (1.3 -> 1.0)")
                try:
                    return self.client.chat.completions.create(
                        model=self.chat_model,
                        messages=messages,
                        temperature=1.0,
                        stream=True,
                        timeout=30
                    )
                except Exception as retry_error:
                    e = retry_error  # 使用重试后的错误继续处理
            
            # Improved error handling with detailed logging
            error_msg = f"❌ 连接 LLM 失败: {str(e)}"
            print(f"[LLMService] Error in get_streaming_response: {error_msg}")
            import traceback
            traceback.print_exc()
            
            # 简单的错误处理生成器，防止前端崩溃
            def error_gen():
                yield type('obj', (object,), {'choices': [type('obj', (object,), {'delta': type('obj', (object,), {'content': error_msg})})]})
            return error_gen()