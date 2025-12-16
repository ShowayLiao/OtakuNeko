import streamlit as st
from .base import BasePlugin # 假设你有一个基类，如果没有可以去掉继承
from src.agent.YearAgent import YearAgent # 假设你的 YearAgent 在这里

class YearReportPlugin:
    def __init__(self, client):
        # 1. 基础属性配置
        self.key = "YEAR_REPORT"                # 程序的唯一标识 ID
        self.btn_label = "🏆 2025 年度动画报告"   # 侧边栏按钮显示的文字
        self.trigger_text = "✨ 生成 2025 年度动画报告" # 点击后发送给对话框的指令
        
        # 2. 初始化内部 Agent
        self.agent = YearAgent(client)

    def execute(self, response_placeholder):
        """
        执行插件逻辑
        :param response_placeholder:用于流式输出或状态显示的 st.empty() 容器
        :return: Final Markdown string (用于存入历史记录)
        """
        # 1. 动态获取当前风格 (从 session_state)
        # 默认为 'cat'，如果未设置
        style = st.session_state.get('selected_style', 'cat')
        
        # 2. 调用 Agent 进行渲染
        # 注意：Agent 内部应该处理 heavy lifting (绘图、数据分析)
        # 并利用 response_placeholder 更新进度 (如果 Agent 支持传参)
        try:
            # 假设 YearAgent.render 接收 style 参数，并返回最终的 markdown 结果
            # 如果你的 YearAgent 需要显示进度条，建议传 response_placeholder 进去
            final_report_markdown = self.agent.render(
                style=style,
                response_placeholder=response_placeholder
            )
            return final_report_markdown
            
        except Exception as e:
            # 错误兜底
            error_msg = f"❌ 年度报告生成失败: {str(e)}"
            st.error(error_msg)
            return error_msg