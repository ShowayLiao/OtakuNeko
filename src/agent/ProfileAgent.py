# src/agent/profile.py
import json
import os
import streamlit as st
from concurrent.futures import ThreadPoolExecutor

from .base import BaseAgent
from src.BgmServe import bgm_service 
from src.config.personas import ROLES, TEMPLATES 
import json_repair

class ProfileAgent(BaseAgent):
    def __init__(self, client):
        super().__init__(client)
        # 定义画像需要的20个维度
        self.categories = [
            "最治愈", "最搞笑", "最感动", "最热血", "最轻松",
            "最虐心", "最三角", "最震撼", "最抽象", "最写实",
            "最恐怖", "最电波", "最恋爱", "最战斗", "最奇幻",
            "最科幻", "最悬疑", "最智斗", "最讨厌", "最小众"
        ]

    def _load_watched_data(self):
        """读取用户已看列表"""
        path = os.path.join(self.dataset_path, "dataset_watched.json")
        data = self._load_json_file(path)
        if not data:
            full_data = bgm_service.load_local_records()
            data = [x for x in full_data if x.get('status') == 'watched']
        return data

    def _fetch_card_metadata(self, mapping):
        """
        [业务逻辑] 映射表组装 (基于公共基类)
        mapping格式: {"有些胃疼": "白色相簿2", "热血战斗": "天元突破"}
        """
        # 1. 准备标题列表
        titles = list(mapping.values())
        
        # 2. 调用基类批量获取
        fetched_map = self._batch_fetch_card_items(titles)
        
        final_results = []
        
        # 3. 遍历映射表回填
        for category, raw_title in mapping.items():
            base_card = fetched_map.get(raw_title)
            
            if base_card:
                # 复制对象
                final_item = base_card.copy()
                
                # --- 回填字段 ---
                final_item['category'] = category
                # 这里 Card 模式下，type 可能不需要，或者等于 category
                final_item['type'] = category 
                # comment 保持为空
                
                final_item.pop('_raw_search_key', None)
                final_results.append(final_item)
            else:
                # ⚠️ 特殊处理：如果 Card 模式下没搜到，
                # 原逻辑是完全丢弃，还是显示一个只有标题的空卡片？
                # 原逻辑中 if search_res: ... else ... 似乎隐含了没搜到就不返回
                # 如果你想保留没搜到的项（显示个红叉），可以在这里处理
                pass
                
        return final_results

    def render(self, prompt, style="cat"):
        """
        🎨 [Frontend] 画像生成主入口
        """
        response_placeholder = st.empty()
        
        # 1. 准备数据
        watched_list = self._load_watched_data()
        if not watched_list:
            st.error("❌ 无数据，请先同步。")
            return "无数据"

        # 2. 准备 Prompt (从配置加载)
        mini_data = json.dumps(watched_list, ensure_ascii=False)
        persona = ROLES.get(style, ROLES["cat"])
        
        system_prompt = f"你现在的身份是：{persona['description']}\n{persona['system_prompt']}"
        try:
            user_prompt = TEMPLATES["profile_analysis"].format(
                role_desc=persona["description"],
                data_str=mini_data,
                categories_json=json.dumps(self.categories, ensure_ascii=False),
                tone_req=persona["tone_requirements"]
            )
        except KeyError as e:
            return f"❌ 配置错误: 缺少 {e}"

        # 3. 执行 UI 流程
        with st.status(f"🎨 {persona['description']} 正在生成...", expanded=True) as status:
            
            # (A) LLM 分析
            status.write(persona.get("start_msg", "正在分析..."))
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            
            # 调用基类 LLM
            raw_json_str = ""
            try:
                stream = self.run(messages, temperature=1.2, stream=True,model="deepseek-reasoner")
                status.write("🧠 正在深度思考...")
                for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        raw_json_str += chunk.choices[0].delta.content
            except Exception as e:
                st.error(f"Error: {e}")
                return "生成失败"

            # (B) 解析 JSON
            try:
                clean_json = raw_json_str.strip()
                if clean_json.startswith("```json"): clean_json = clean_json[7:]
                if clean_json.endswith("```"): clean_json = clean_json[:-3]
                
                result_data = json_repair.loads(raw_json_str)
                mapping = result_data.get("mapping", {})
                analysis = result_data.get("analysis", "")
                
                # 显示分析文本
                final_text = f"{persona.get('start_msg','')}{analysis}"
                response_placeholder.markdown(final_text)

            except:
                st.error("解析失败")
                return raw_json_str

            # (C) 抓取并渲染卡片
            status.write("📡 正在检索元数据...")
            card_items = self._fetch_card_metadata(mapping)

            status.write("🖌️ 正在后台绘制高清长图...")
            img_path = self.draw_grid_image(
                items_data=card_items,
                output_filename="profile_grid.png",
                cols=5,
                title_text="OtakuMate · 二次元成分鉴定"
            )
            
            status.update(label="✅ 完成", state="complete", expanded=False)

        # 🟢 4. 关键点：直接调用基类的渲染方法
        final_text = f"{persona.get('start_msg','')}{analysis}"
        response_placeholder.markdown(final_text)

        if card_items:
            # 显示 HTML 卡片网格 (交互式)
            st.divider()
            st.caption("📊 二次元成分鉴定表 (交互版)")
            self.render_cards(card_items, cols=5)
            
            # 🟢 显示下载图片的按钮
            if img_path and os.path.exists(img_path):
                st.divider()
                with open(img_path, "rb") as file:
                    st.download_button(
                        label="💾 下载高清鉴定图 (PNG)",
                        data=file,
                        file_name="anime_profile.png",
                        mime="image/png",
                        use_container_width=True
                    )
        
        return final_text