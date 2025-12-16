# src/plugins/year_report.py
import streamlit as st
from .base import BasePlugin
from src.agent.YearAgent import YearAgent

class YearReportPlugin(BasePlugin):
    def __init__(self, client):
        super().__init__(client)
        self.key = "YEAR_REPORT"
        self.agent = YearAgent(client)

    def render_button(self):
        """渲染悬浮按钮 (UI)"""
        # 1. 注入专属 CSS (只针对这个按钮，使其悬浮在左侧边栏底部上方)
        st.markdown("""
        <style>
            div[data-testid="stSidebar"] div[data-testid="stVerticalBlock"] > div:has(div#floating-year-btn) {
                position: fixed;
                bottom: 20px;
                left: 20px;
                width: 260px; /* Sidebar width adjustment */
                z-index: 999;
                pointer-events: none;
            }
            div[data-testid="stSidebar"] div[data-testid="stVerticalBlock"] > div:has(div#floating-year-btn) button {
                pointer-events: auto;
                width: 100%;
                background-color: #F0F7FF !important; 
                color: #5A7C98 !important;
                border: 1px solid #DDE6ED !important; 
                border-radius: 12px !important;
                padding: 0.5rem 1rem !important; 
                font-weight: 600 !important;
                box-shadow: 0 4px 12px rgba(90, 124, 152, 0.15) !important;
                transition: all 0.2s ease !important;
            }
            div[data-testid="stSidebar"] div[data-testid="stVerticalBlock"] > div:has(div#floating-year-btn) button:hover {
                background-color: #FFFFFF !important; 
                color: #4A6C88 !important;
                border-color: #B0C4DE !important; 
                transform: translateY(-2px);
            }
        </style>
        """, unsafe_allow_html=True)

        # 2. 渲染锚点和按钮 (放在 Sidebar 中)
        with st.sidebar:
            st.markdown('<div id="floating-year-btn"></div>', unsafe_allow_html=True)
            if st.button("🏆 生成 2025 年度动画报告", key="btn_year_report"):
                st.session_state['active_plugin'] = self.key
                st.rerun()

    def execute(self, chat_container):
        """
        插件执行逻辑
        Args:
            chat_container: 主界面的 st.empty() 容器，虽然 Agent 内部使用了 st.write，
                            但这个参数保留以符合接口规范。
        """
        # 直接调用 Agent 的 render 方法
        # 这里的 style 参数可以根据 session_state 动态获取，默认 "cat"
        style = "cat" # 或者 st.session_state.get('selected_style', 'cat')
        
        return self.agent.render(style=style)