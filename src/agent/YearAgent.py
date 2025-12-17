# src/agent/year_report.py
import json
import os
import streamlit as st
from .ProfileAgent import ProfileAgent
from src.BgmServe import bgm_service
from src.config.personas import ROLES, TEMPLATES
import json_repair

class YearAgent(ProfileAgent):
    # No custom __init__ needed, it will inherit from ProfileAgent.
    # We will override the categories directly in the class body.
    categories = [
        "最佳动画", "最佳原创", "最佳改编", "最佳画面", 
        "最佳音乐", "最想安利", "最意难平", "最被低估", 
        "最被过誉", "最欢乐", "最抽象", "最炒作"
    ]

    def render(self, style="cat", response_placeholder=None):
        """
        🎨 年度总结全流程渲染 (逻辑优化版)
        """
        final_text = ""
        card_items = []
        img_path = None
        
        # --- 0. 定义趣味关键词池 (不变) ---
        keywords_list = [
            "电子榨菜品鉴师", "深夜胃药受害者", "作画警察", "异世界泥头车", 
            "高贵路人", "纯爱战神", "牛头人", "百合营业", "赛博案底", 
            "剧情难民", "乐子人", "省经费战士", "催眠大师"
        ]

        # --- 1. 准备数据 (不变) ---
        watched_list = self._load_recent_watched_strs(365,"title","id","score","tags","cv","summary","year","month")
        if not watched_list:
            st.error("🚫 近期无数据，无法生成年度总结。")
            return "近期无数据，无法生成年度总结。"
        mini_data = json.dumps(watched_list, ensure_ascii=False)

        # --- 2. 准备 Prompt & System Prompt (不变) ---
        persona = ROLES.get(style, ROLES["cat"])
        # print("Year Report Persona:", persona)
        try:
            user_prompt = TEMPLATES["year_report_analysis"].format(
                role_desc=persona["description"],
                data_str=mini_data,
                categories_json=json.dumps(self.categories, ensure_ascii=False),
                tone_req=persona["tone_requirements"],
                keywords_list=str(keywords_list)
            )

        except KeyError as e:
            st.error(f"配置错误: {e}")
            return "System Error"
        system_prompt = f"你现在的身份是：{persona['description']}\n{persona['system_prompt']}"

        # --- 3. 执行 UI 流程 ---
        with st.status(f"🏆 {persona['description']} 正在评选年度大奖...", expanded=True) as status:
            
            # (A) LLM 分析 (不变)
            status.write(persona.get("start_msg", "正在分析..."))
            messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
            
            raw_json_str = ""
            try:
                stream = self.run(messages, temperature=1.5, stream=True, model=self.llm_service.reasoner_model)
                status.write("🧠 正在分析 CV 重复度与追番时间轴...")
                for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        raw_json_str += chunk.choices[0].delta.content
            except Exception as e:
                st.error(f"API Error: {e}")
                return "生成失败"

            # (B) 解析 JSON & 构建中间数据结构 (✨ 重构核心)
            try:
                # Use robust JSON parsing
                from src.data_processor import robust_json_parse
                result_data = robust_json_parse(raw_json_str, {})
                
                if not result_data:
                    st.error("AI 返回格式异常")
                    return "生成失败"
                
                # print("Year Report LLM Raw Output:", result_data)
                
                # 提取基础信息
                user_stats = result_data.get("user_stats", {})
                raw_awards = result_data.get("awards_mapping", {})
                report = result_data.get("analysis_report", {})

                # 1. 鲁棒性修正: 确保 raw_awards 是字典
                llm_awards_source = {}
                if isinstance(raw_awards, list):
                    for item in raw_awards:
                        if isinstance(item, dict): llm_awards_source.update(item)
                elif isinstance(raw_awards, dict):
                    llm_awards_source = raw_awards

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

                # 3. 构造 Markdown 输出 (不变)
                tags_str = " ".join([f"`{t}`" for t in user_stats.get("yearly_tags", [])])
                stats_md = ""
                if comment_tags := user_stats.get("comment_tags", [])[0]:
                    stats_md += f"- 🏷️ **年度称号**：{comment_tags}\n"
                # if top_cv := user_stats.get("top_cv"):
                    # stats_md += f"- 🎙️ **年度声优**：{top_cv.get('name')} ({top_cv.get('count')}部) — *{top_cv.get('comment')}*\n"
                if busy_month := user_stats.get("busiest_month"):
                    stats_md += f"- 📅 **最忙月份**：{busy_month.get('month')}月 — *{busy_month.get('comment')}*\n"
                if Anime_tag := user_stats.get("Anime_tag"):
                    stats_md += f"- 🏭 **核心成分**：{Anime_tag.get('tag', 'N/A')[0]}、{Anime_tag.get('tag', 'N/A')[1]}、{Anime_tag.get('tag', 'N/A')[2]} — *{Anime_tag.get('comment', '')}*\n"

                final_text = (
                    f"## {report.get('title', '2025 年度动画报告')}\n\n{tags_str}\n\n"
                    f"### 📊 年度成分审计\n{stats_md}\n{report.get('intro', '')}\n\n---\n"
                    f"### 🏆 深度评析\n{report.get('body', '')}\n\n> {report.get('conclusion', '')}"
                )
                if response_placeholder: response_placeholder.markdown(final_text)

            except Exception as e:
                st.error(f"数据解析异常: {e}")
                return raw_json_str

            # (C) 抓取元数据 & 合并数据 (✨ 重构核心)
            try:
                status.write("📡 正在准备奖杯与海报...")
                
                # 1. 准备搜索映射表: 仅包含非 N/A 的标题
                # 格式: {"最佳动画": "药屋少女", ...}
                search_mapping = {
                    cat: data['title'] 
                    for cat, data in llm_parsed_data.items() 
                    if data['title'] != "N/A"
                }

                # 2. 批量联网抓取 (返回 List[Dict])
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

                # (D) 绘制图片 (不变)
                status.write("🖌️ 正在绘制 2025 年度海报...")
                img_path = self.draw_grid_image(
                    items_data=card_items,
                    output_filename="year_report_2025.png",
                    cols=4, 
                    title_text="OtakuNeko · 2025年度动画认证：",
                    subtitle_text=f"{user_stats.get('comment_tags', ['2025年度成分鉴定'])[0]}：{user_stats.get('Anime_tag', {}).get('tag', ['N/A'])[0]}、{user_stats.get('Anime_tag', {}).get('tag', ['N/A'])[1]}、{user_stats.get('Anime_tag', {}).get('tag', ['N/A'])[2]}",
                    user_name=bgm_service.username
                )
                status.update(label="✅ 年度总结生成完毕", state="complete", expanded=False)

            except Exception as e:
                status.update(label="⚠️ 生成过程中遇到部分问题", state="error", expanded=True)
                st.error(f"海报或数据处理失败: {str(e)}")

        # --- 4. 结果展示区 (简化版) ---
        if card_items:
            st.divider()
            
            # ✨ 直接渲染卡片，因为 card_items 里的 comment 已经被正确赋值为“颁奖理由”了
            self.render_cards(card_items, cols=4)
            
            if img_path and os.path.exists(img_path):
                st.divider()
                col1, col2 = st.columns([3, 1])
                with col1: st.success("✨ 你的年度二次元成分报告已生成！")
                with col2:
                    with open(img_path, "rb") as file:
                        st.download_button(
                            label="💾 下载海报 (PNG)", data=file,
                            file_name="2025_anime_awards.png", mime="image/png", use_container_width=True
                        )
        else:
            st.warning("⚠️ 未能生成奖项卡片")
        
        return final_text