# src/plugins/base.py
import streamlit as st

class BasePlugin:
    """所有悬浮插件的基类"""
    
    def __init__(self, client):
        self.client = client
        self.key = "base_plugin" # 唯一标识符

    def render_button(self):
        """渲染悬浮按钮的 UI 和 CSS"""
        pass

    def handle_click(self):
        """处理点击事件（通常是设置 session_state）"""
        st.session_state['active_plugin'] = self.key

    def execute(self):
        """执行核心逻辑（生成报告、流式输出等）"""
        pass