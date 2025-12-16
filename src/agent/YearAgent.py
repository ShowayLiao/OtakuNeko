# src/agent/year_report.py
import json
import os
import streamlit as st
from .ProfileAgent import ProfileAgent
from src.BgmServe import bgm_service
from src.config.personas import ROLES, TEMPLATES

class YearAgent(ProfileAgent):
    def __init__(self, client):
        super().__init__(client)
        # 1. 覆写：年度总结专用的 12 个奖项
        self.categories = [
            "最佳动画", "最佳原创", "最佳改编", "最佳画面", 
            "最佳音乐", "最想安利", "最意难平", "最被低估", 
            "最被过誉", "最欢乐", "最抽象", "最炒作"
        ]

    def render(self, style="cat"):
        """
        🎨 年度总结全流程渲染
        Returns:
            str: 最终生成的分析文本 (用于存入聊天记录)
        """
        response_placeholder = st.empty()
        final_text = ""
        card_items = []  # 🟢 1. 提前初始化，防止后面引用报错
        img_path = None
        
        # 1. 准备数据
        watched_list = self._load_recent_watched_strs(recent=365)
        if not watched_list:
            st.error("🚫 近期无数据，无法生成年度总结。")
            return "近期无数据，无法生成年度总结。"

        mini_data = json.dumps(
            watched_list, 
            ensure_ascii=False
        )

        # 2. 准备 Prompt
        if style == "cat":
            role_desc = "毒舌又傲娇的二次元猫娘评论家 🐱"
            tone_req = "- **口癖**：句尾带“喵”！\n- **态度**：对他的年度选择进行点评。"
            start_msg = "🐱 正在审视你的年度片单喵...\n\n"
        else:
            role_desc = "专业二次元年度赏评委会主席 🧐"
            tone_req = "- **口吻**：庄重、专业、客观。"
            start_msg = "🧐 正在进行年度奖项评选...\n\n"

        # 从配置加载 Prompt
        try:
            user_prompt = TEMPLATES["year_report_analysis"].format(
                role_desc=role_desc,
                data_str=mini_data,
                categories_json=json.dumps(self.categories, ensure_ascii=False),
                tone_req=tone_req
            )
        except KeyError as e:
            st.error(f"配置错误: {e}")
            return "System Error"

        system_prompt = f"你现在的身份是：{role_desc}"

        # 3. 执行 UI 流程 (带进度条)
        with st.status(f"🏆 {role_desc} 正在评选年度大奖...", expanded=True) as status:
            
            # (A) LLM 分析
            status.write(start_msg.strip())
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            raw_json_str = ""
            try:
                stream = self.run(messages, temperature=1.2, stream=True,model="deepseek-reasoner")
                status.write("🧠 正在撰写颁奖词...")
                for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        raw_json_str += chunk.choices[0].delta.content
            except Exception as e:
                st.error(f"API Error: {e}")
                return "生成失败"

            # (B) 解析 JSON
            try:
                clean_json = raw_json_str.strip()
                if clean_json.startswith("```json"): clean_json = clean_json[7:]
                if clean_json.endswith("```"): clean_json = clean_json[:-3]
                
                result_data = json.loads(clean_json)
                
                # 按 categories 顺序排序
                raw_mapping = result_data.get("mapping", {})
                ordered_mapping = {k: raw_mapping.get(k, "N/A") for k in self.categories}
                
                analysis = result_data.get("analysis", "")
                final_text = f"{start_msg}{analysis}"
                
                # 实时更新文本
                response_placeholder.markdown(final_text)

            except:
                st.error("JSON 解析失败")
                return raw_json_str

            try:
                # (C) 抓取元数据
                status.write("📡 正在准备奖杯与海报...")
                if 'ordered_mapping' in locals(): # 确保上一步成功
                    card_items = self._fetch_card_metadata(ordered_mapping)
                else:
                    raise ValueError("JSON解析未能生成有效映射")

                # (D) 绘制图片
                status.write("🖌️ 正在绘制 2025 年度海报...")
                img_path = self.draw_grid_image(
                    items_data=card_items,
                    output_filename="year_report_2025.png",
                    cols=4, 
                    title_text="OtakuMate · 2025 年度动画赏"
                )
                
                status.update(label="✅ 年度总结生成完毕", state="complete", expanded=False)
            
            except Exception as e:
                # 🔴 关键：捕获错误并打印，防止程序直接中断退出
                status.update(label="⚠️ 生成过程中遇到部分问题", state="error", expanded=True)
                st.error(f"海报或数据处理失败: {str(e)}")

        if card_items:
            st.divider()
            st.caption("🏆 2025 年度获奖名单")
            self.render_cards(card_items, cols=4)
            
            # 渲染下载按钮
            if img_path and os.path.exists(img_path):
                st.divider()
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.info("✨ 你的年度二次元成分报告已生成！")
                with col2:
                    with open(img_path, "rb") as file:
                        st.download_button(
                            label="💾 下载海报 (PNG)",
                            data=file,
                            file_name="2025_anime_awards.png",
                            mime="image/png",
                            use_container_width=True
                        )
        else:
            # 这里的输出现在应该能看到了
            st.warning("⚠️ 未能生成奖项卡片（可能是元数据抓取失败）")
            print("⚠️ 警告：card_items 为空")
        
        return final_text