# src/agent/profile.py
import json
import os
import streamlit as st
from concurrent.futures import ThreadPoolExecutor

from .base import BaseAgent
from src.BgmServe import BangumiService
from src.config.personas import ROLES, TEMPLATES 
from src.utils import get_session_manager, get_session_id
import json_repair

class ProfileAgent(BaseAgent):
    def __init__(self, llm_service, bgm_service: BangumiService):
        super().__init__(llm_service, bgm_service)
        self.bgm_service = bgm_service
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
            full_data = self.bgm_service.load_local_records()
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

    def render(self, prompt, style="cat", session_id=None):
        """
        🎨 [Frontend] 画像生成主入口
        """
        # 动作锁：防止重复请求和僵尸进程
        if st.session_state.get('is_processing_profile'):
            st.warning("⚠️ 二次元成分鉴定正在生成中，请稍候...")
            return "二次元成分鉴定正在生成中，请稍候..."
        
        st.session_state.is_processing_profile = True
        
        # 获取会话管理器实例
        manager = get_session_manager()
        session_id = session_id or get_session_id()
        
        # 在进入忙碌状态前手动刷新心跳
        manager.update_ping(session_id)
        
        try:
            # 设置忙碌状态
            manager.set_busy_status(session_id, True)
            
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
                    stream = self.run(messages, temperature=0.2, stream=True, model=self.llm_service.reasoner_model, session_id=session_id)
                    status.write("🧠 正在深度思考...")
                    for chunk in stream:
                        if chunk.choices and chunk.choices[0].delta.content:
                            raw_json_str += chunk.choices[0].delta.content
                except Exception as e:
                    st.error(f"Error: {e}")
                    return "生成失败"

                # (B) 解析 JSON
                try:
                    # Use robust JSON parsing
                    from src.data_processor import robust_json_parse
                    result_data = robust_json_parse(raw_json_str, {})
                    
                    if not result_data:
                        st.error("AI 返回格式异常")
                        return "生成失败"
                        
                    mapping = result_data.get("mapping", {})
                    # 1. 提取数据 (适配新版 Prompt 结构)
                    analysis = result_data.get("analysis", "暂无深度分析")

                    # 提取称号 (取 tags 列表的第一个作为主称号)
                    tags = result_data.get("tags", [])

                    otaku_score = result_data.get("otaku_score", 0)

                    # 提取成分 (Composition) -> 格式化为 "赛博精神病 (30%), 纯爱 (20%)"
                    comp_data = result_data.get("composition", [])
                    comp_list = [f"{item.get('label', '未知')} ({int(item.get('value', 0)*100)}%)" for item in comp_data]
                    comp_str = "、".join(comp_list) if comp_list else "成分不明"

                    # 假设 result_data 是 LLM 返回的完整 JSON
                    radar_data = result_data.get("radar", {})
                      

                    # 1. 鲁棒性修正: 确保 raw_awards 是字典
                    llm_awards_source = {}
                    if isinstance(mapping, list):
                        for item in mapping:
                            if isinstance(item, dict): llm_awards_source.update(item)
                    elif isinstance(mapping, dict):
                        llm_awards_source = mapping

                     # 2. 提取核心数据 (Title & Reason)
                    # 结构: { "最佳动画": {"title": "xxx", "reason": "xxx"}, ... }
                    llm_parsed_data = {}
                    
                    for cat in self.categories:
                        item_data = llm_awards_source.get(cat, {})
                        
                        # 提取标题
                        raw_title = "N/A"
                        if isinstance(item_data, dict):
                            raw_title = item_data.get("title", "N/A")
                        elif isinstance(item_data, str):
                            raw_title = item_data
                        
                        # 清洗标题
                        clean_title = "N/A"
                        if raw_title and raw_title != "N/A":
                            clean_title = str(raw_title).replace("《", "").replace("》", "").strip()

                        # 提取理由 (Reason)
                        reason = ""
                        if isinstance(item_data, dict):
                            reason = item_data.get("reason", "")
                        
                        # 存入中间字典
                        llm_parsed_data[cat] = {
                            "title": clean_title,
                            "reason": reason
                        }
                except:
                    st.error("解析失败")
                    return raw_json_str

                # (C) 抓取并渲染卡片
                status.write("📡 正在检索元数据...")

                search_mapping = {
                        cat: data['title'] 
                        for cat, data in llm_parsed_data.items() 
                        if data['title'] != "N/A"
                    }

                fetched_results = []
                if search_mapping:
                    fetched_results = self._fetch_card_metadata(search_mapping)


                # 3. 建立查找索引: { "最佳动画": {id:123, image:url...} }
                fetched_lookup = {item['category']: item for item in fetched_results}

                # 4. 最终合并 (Merge LLM Data + Fetched Data)
                card_items = []
                for cat in self.categories:
                    llm_info = llm_parsed_data.get(cat, {})
                    llm_title = llm_info.get("title", "本项空缺")
                    llm_reason = llm_info.get("reason", "AI 未能提供理由")

                    if cat in fetched_lookup:
                        # Case A: 抓取成功 -> 使用抓取的数据 + 注入 LLM 理由
                        item = fetched_lookup[cat]
                        item['comment'] = llm_reason # 核心：把理由注入 comment
                        card_items.append(item)
                    else:
                        # Case B: 没抓到或 N/A -> 使用 LLM 数据构造纯文字卡片
                        card_items.append({
                            "category": cat,
                            "title": llm_title,
                            "image": "", # 无图
                            "score": "",
                            "id": None,
                            "comment": llm_reason # 依然显示理由
                        })

                status.write("🖌️ 正在后台绘制高清长图...")


                # 转换 mapping 为 list (格子数据

                # 🔥 只要加两个参数，饼图和雷达图就有了！
                img_path = self.draw_grid_image(
                    items_data=card_items, 
                    output_filename="profile_grid.png",
                    title_text="OtakuNeko · 二次元成分鉴定",
                    subtitle_text=f"{tags[0]}" if tags else "二次元爱好者",
                    user_name=self.bgm_service.username,
                    radar_data=result_data['radar'],          # 外挂雷达数据
                    composition_data=result_data['composition'], # 外挂饼图数据
                    otaku_score=otaku_score,
                )
                status.update(label="✅ 完成", state="complete", expanded=False)

            # 🟢 4. 关键点：直接调用基类的渲染方法

            # # 显示分析文本
            st.markdown(f"## 🐾 {persona['description']} 的二次元成分鉴定结果")

            # 创建两列布局：左边放图表，右边放核心数据
            col1, col2 = st.columns([1, 1])

            title = tags[0] if tags else "无名路人"

            with col1:
                st.markdown("### 🧬 属性雷达")
                # 调用上面的绘图函数
                self.plot_radar_chart(radar_data)

            with col2:
                st.markdown(f"### 🏷️ **#{title}**")
                # 成分：用 caption 或普通文本，显得精致点
                # 核心指标：垂直居中展示
                st.write("") # 占个空行用来对齐
                st.metric(label="二次元浓度", value=f"{otaku_score}%")
                # 进度条紧跟在 metric 下面
                st.progress(otaku_score / 100)

                st.markdown(f"**🧪 精神成分**：")
                for item in comp_data:
                    # 显示格式：纯爱战神 (40%)
                    st.text(f"{item['label']} ({int(item['value']*100)}%)")
                    st.progress(item['value'])

            st.divider()

            st.markdown("### **🔍 深度分析**")
            st.write(analysis)

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
            
            return analysis
        
        finally:
            # 释放忙碌状态和动作锁
            manager.set_busy_status(session_id, False)
            manager.update_ping(session_id)
            st.session_state.is_processing_profile = False
