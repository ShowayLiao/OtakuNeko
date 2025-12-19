# src/agent/router.py
import json
import streamlit as st
from .base import BaseAgent
from src.config.personas import TEMPLATES
from src.utils import get_session_manager, get_session_id

class IntentRouter(BaseAgent):
    def __init__(self, llm_service, bgm_service):
        super().__init__(llm_service, bgm_service)
        self.bgm_service = bgm_service

    def classify(self, user_input, session_id=None):
        # 获取会话管理器实例
        manager = get_session_manager()
        session_id = session_id or get_session_id()
        
        # 在进入忙碌状态前手动刷新心跳
        manager.update_ping(session_id)
        
        try:
            # 设置忙碌状态
            manager.set_busy_status(session_id, True)
            
            print(f"🧠 [Router] 收到指令: {user_input[:20]}...")
        
            # 从配置加载 Prompt
            system_prompt = TEMPLATES["router_system"]
        
            # 🟢 使用基类的 run 方法，它会自动选择正确的模型
            response = self.run(
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input}
                ],
                temperature=0.1, # 路由需要精确，温度设低
                response_format={"type": "json_object"},
                stream=False,
                timeout=10,
                session_id=session_id
            )
            
            content = response.choices[0].message.content
            print(f"🧠 [Router] 判决: {content}")
            
            data = json.loads(content)
            intent = data.get("intent", "CHAT").strip().upper()
            tags = data.get("tags", [])
            
            # 安全检查：确保是合法意图
            valid_intents = ['PROFILE', 'RECOMMEND', 'GENERATE', 'CHAT', 'AMBIGUOUS']
            if intent not in valid_intents:
                return 'CHAT', []
                
            return intent, tags
            
        except Exception as e:
            print(f"❌ [Router] 路由失败 (已回退到 CHAT): {e}")
            return 'CHAT', []
        finally:
            # 释放忙碌状态
            manager.set_busy_status(session_id, False)
            manager.update_ping(session_id)