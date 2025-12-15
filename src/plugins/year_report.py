# src/plugins/year_report.py
import streamlit as st
from src.plugins.base import BasePlugin
from src.extensions.year_agent import YearAgent # 引用之前的业务类
from src.data_processor import extract_recent_watched

class YearReportPlugin(BasePlugin):
    def __init__(self, client):
        super().__init__(client)
        self.key = "YEAR_REPORT"
        self.agent = YearAgent(client)

    def render_button(self):
        # 1. 注入专属 CSS (只针对这个按钮)
        st.markdown("""
        <style>
            div[data-testid="stVerticalBlock"] > div:has(div#floating-year-btn) {
                position: fixed;
                bottom: 105px; left: 24%; transform: translateX(-50%);
                z-index: 2147483647; pointer-events: none; width: auto;
            }
            div[data-testid="stVerticalBlock"] > div:has(div#floating-year-btn) button {
                pointer-events: auto;
                background-color: #F0F7FF !important; color: #5A7C98 !important;
                border: 1px solid #DDE6ED !important; border-radius: 24px !important;
                padding: 0.5rem 1.5rem !important; font-weight: 600 !important;
                box-shadow: 0 4px 12px rgba(90, 124, 152, 0.15) !important;
                transition: all 0.2s ease !important;
            }
            div[data-testid="stVerticalBlock"] > div:has(div#floating-year-btn) button:hover {
                background-color: #FFFFFF !important; color: #4A6C88 !important;
                border-color: #B0C4DE !important; transform: translateY(-2px);
            }
        </style>
        """, unsafe_allow_html=True)

        # 2. 渲染锚点和按钮
        with st.container():
            st.markdown('<div id="floating-year-btn"></div>', unsafe_allow_html=True)
            st.button(
                "🏆✨ 生成 2025 年度动画报告", 
                on_click=self.handle_click, # 绑定基类的点击事件
                key="btn_year_report"
            )

    def execute(self, chat_container):
        """
        Args:
            chat_container: 用于输出内容的容器 (st.chat_message)
        """
        response_placeholder = chat_container.empty()
        full_response = ""
        profile_cards_data = None
        generated_img_path = None

        try:
            with st.status("🏆 正在生成年度报告...", expanded=True) as status:

                extract_recent_watched(365)  # 确保数据已准备好
                # 调用业务逻辑
                stream = self.agent.generate_report(style="cat") # 这里的 style 可以从 session_state 取
                
                for chunk in stream:
                    if isinstance(chunk, dict) and chunk.get('type') == 'card_data':
                        profile_cards_data = chunk['data']
                        status.write("✅ 数据准备就绪")
                    elif isinstance(chunk, dict) and chunk.get('type') == 'image':
                        generated_img_path = chunk['path']
                        status.write("✅ 海报绘制完成")
                    elif isinstance(chunk, str):
                        full_response += chunk
                        if "```json" not in full_response:
                            response_placeholder.markdown(full_response + "▌")
                
                status.update(label="✅ 生成完毕", state="complete", expanded=False)
            
            response_placeholder.markdown(full_response)

            # 渲染结果 (卡片 + 下载按钮)
            self._render_results(profile_cards_data, generated_img_path)
            
            return full_response

        except Exception as e:
            st.error(f"插件执行错误: {e}")
            return "执行失败"

    def _render_results(self, cards, img_path):
            """辅助方法：渲染卡片和下载按钮"""
            if cards:
                st.divider()
                cols = st.columns(4)
                
                for i, item in enumerate(cards):
                    with cols[i % 4]:
                        # 1. 链接
                        if item.get('id'): 
                            link = f"https://bgm.tv/subject/{item['id']}"
                        else: 
                            import urllib.parse
                            link = f"https://bgm.tv/subject_search/{urllib.parse.quote(item['title'])}?cat=2"
                        
                        # 2. 图片 (宽100%, 高自适应，绝不裁剪)
                        img_src = item.get('image', '')
                        if img_src:
                            img_html = f"<img src='{img_src}' style='width:100%; height:auto; display:block; border-radius:8px 8px 0 0;'>"
                        else:
                            img_html = "<div style='width:100%; height:150px; background:#f4f6f8; display:flex; align-items:center; justify-content:center; color:#999; font-size:12px;'>NO IMG</div>"
                        
                        # 3. HTML 组装
                        # 🔴 关键修改：为了防止 Markdown 把缩进当成代码块，这里把 HTML 顶格写，或者拼成一整行
                        card_html = f"""
    <a href="{link}" target="_blank" style="text-decoration:none; color:inherit; display:block; margin-bottom: 15px;">
    <div style="border:1px solid #EBF1F5; border-radius:8px; background:white; box-shadow: 0 2px 6px rgba(0,0,0,0.04); transition: transform 0.2s;">
        <div style='width:100%; border-radius:8px 8px 0 0; overflow:hidden; background:#f4f6f8;'>
            {img_html}
        </div>
        <div style="padding: 10px; border-top: 1px solid #f0f0f0;">
            <div style="text-align:center; margin-bottom:6px;">
                <span style="background-color:#E3F2FD; color:#1565C0; padding:2px 8px; border-radius:10px; font-size:11px; font-weight:bold;">{item['category']}</span>
            </div>
            <div style="font-size:13px; font-weight:bold; text-align:center; line-height:1.4; color:#333; padding-bottom: 4px;">
                {item['title']}
            </div>
        </div>
    </div>
    </a>
    """
                        # 渲染
                        st.markdown(card_html, unsafe_allow_html=True)

            if img_path:
                st.divider()
                with open(img_path, "rb") as file:
                    st.download_button("💾 下载年度海报", file, "year_report.png", "image/png", type="primary", use_container_width=True)