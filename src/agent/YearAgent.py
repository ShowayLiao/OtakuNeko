# src/agent/YearAgent.py
import json
import os
import streamlit as st
from datetime import datetime, timedelta
from .ProfileAgent import ProfileAgent
from src.BgmServe import BangumiService
from src.config.personas import ROLES, TEMPLATES
from src.data_processor import robust_json_parse
from src.utils import get_session_manager, get_session_id, optimize_anime_data

class YearAgent(ProfileAgent):
    def __init__(self, llm_service, bgm_service: BangumiService):
        super().__init__(llm_service, bgm_service)
        self.bgm_service = bgm_service
        # 定义年度报告需要的12个奖项类别
        self.categories = [
            "最佳动画", "最佳原创", "最佳改编", "最佳画面", 
            "最佳音乐", "最想安利", "最意难平", "最被低估", 
            "最被过誉", "最欢乐", "最抽象", "最炒作"
        ]

    def _load_recent_watched_data(self, days=365):
        """
        加载过去指定天数的观看数据
        :param days: 天数，默认365天
        :return: 过滤后的观看数据列表
        """
        path = os.path.join(self.dataset_path, "dataset_watched.json")
        data = self._load_json_file(path)
        if not data:
            full_data = self.bgm_service.load_local_records()
            data = [x for x in full_data if x.get('status') == 'watched']
        
        # 过滤过去365天的数据
        if days > 0:
            now = datetime.now()
            cutoff_date = now - timedelta(days=days)
            filtered_data = []
            
            for item in data:
                updated_at_str = item.get('updated_at', '')
                if updated_at_str:
                    try:
                        # 处理带时区的ISO格式日期
                        if '+' in updated_at_str or '-' in updated_at_str:
                            updated_at = datetime.fromisoformat(updated_at_str.replace('Z', '+00:00'))
                        else:
                            updated_at = datetime.strptime(updated_at_str, '%Y-%m-%d %H:%M:%S')
                        
                        # 转换为naive datetime进行比较
                        updated_at_naive = updated_at.replace(tzinfo=None)
                        if updated_at_naive >= cutoff_date:
                            filtered_data.append(item)
                    except Exception:
                        # 如果日期解析失败，保留该记录
                        filtered_data.append(item)
            
            return filtered_data
        
        return data

    def render(self, style="cat", response_placeholder=None):
        """
        🎨 年度总结全流程渲染
        """
        # 动作锁：防止重复请求和僵尸进程
        if st.session_state.get('is_processing_year_report'):
            st.warning("⚠️ 年度总结正在生成中，请稍候...")
            return "年度总结正在生成中，请稍候..."
        
        st.session_state.is_processing_year_report = True
        
        # 获取会话管理器实例
        manager = get_session_manager()
        session_id = get_session_id()
        
        # 在进入忙碌状态前手动刷新心跳
        manager.update_ping(session_id)
        
        try:
            # 设置忙碌状态
            manager.set_busy_status(session_id, True)
            
            final_text = ""
            card_items = []
            img_path = None
            
            # --- 0. 定义趣味关键词池 ---
            keywords_list = [
                "电子榨菜品鉴师", "深夜胃药受害者", "作画警察", "异世界泥头车", 
                "高贵路人", "纯爱战神", "牛头人", "百合营业", "赛博案底", 
                "剧情难民", "乐子人", "省经费战士", "催眠大师"
            ]

            # --- 1. 准备数据 ---
            watched_list = self._load_recent_watched_data(365)
            if not watched_list:
                st.error("🚫 近期无数据，无法生成年度总结。")
                return "近期无数据，无法生成年度总结。"
            
            # 提取需要的字段
            recent_data = []
            for item in watched_list:
                recent_data.append({
                    "id": item.get('id'),
                    "title": item.get('title'),
                    "score": item.get('score', 'N/A'),
                    "tags": item.get('tags', []),
                    "cv": item.get('cv', []),
                    "summary": item.get('summary', '')[:100],
                    "year": item.get('year'),
                    "month": item.get('month')
                })
            
            # 应用Token优化
            optimized_data = optimize_anime_data(recent_data, st.session_state.get('token_optimization_enabled', True))
            data_str = json.dumps(optimized_data, ensure_ascii=False)

            # --- 2. 准备 Prompt & System Prompt ---
            persona = ROLES.get(style, ROLES["cat"])
            
            try:
                user_prompt = TEMPLATES["year_report_analysis"].format(
                    role_desc=persona["description"],
                    data_str=data_str,
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
                # UI反馈：显示保护提示
                status.write("🛡️ 服务器已为您锁定位置，正在深度分析中...")
                
                # (A) LLM 分析
                status.write(persona.get("start_msg", "正在分析..."))
                messages = [{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}]
                
                raw_json_str = ""
                try:
                    stream = self.run(messages, temperature=0.2, stream=True, model=self.llm_service.reasoner_model)
                    status.write("🧠 正在分析 CV 重复度与追番时间轴...")
                    for chunk in stream:
                        if chunk.choices and chunk.choices[0].delta.content:
                            raw_json_str += chunk.choices[0].delta.content
                except Exception as e:
                    st.error(f"API Error: {e}")
                    return "生成失败"

                # (B) 解析 JSON & 构建中间数据结构
                try:
                    result_data = robust_json_parse(raw_json_str, {})
                    
                    if not result_data:
                        st.error("AI 返回格式异常")
                        return "生成失败"
                    
                    # 验证输出格式
                    required_keys = ["user_stats", "radar", "composition", "awards_mapping", "analysis_report"]
                    for key in required_keys:
                        if key not in result_data:
                            st.error(f"AI 返回数据缺少必要字段: {key}")
                            return "生成失败"
                    
                    # 提取基础信息
                    user_stats = result_data.get("user_stats", {})
                    raw_awards = result_data.get("awards_mapping", {})
                    report = result_data.get("analysis_report", {})
                    radar_data = result_data.get("radar", {})
                    composition_data = result_data.get("composition", [])

                    # 1. 鲁棒性修正: 确保 raw_awards 是字典
                    llm_awards_source = {}
                    if isinstance(raw_awards, list):
                        for item in raw_awards:
                            if isinstance(item, dict): llm_awards_source.update(item)
                    elif isinstance(raw_awards, dict):
                        llm_awards_source = raw_awards

                    # 2. 提取核心数据 (Title & Reason)
                    llm_parsed_data = self._parse_llm_awards_json(result_data, self.categories)

                    # 3. 构造 Markdown 输出
                    stats_md = ""
                    if comment_tags := user_stats.get("comment_tags", []):
                        if comment_tags:
                            stats_md += f"- 🏆 **年度称号**：{comment_tags[0]}\n"
                    if busy_month := user_stats.get("busiest_month"):
                        stats_md += f"- 📅 **最忙月份**：{busy_month.get('month')}月 — *{busy_month.get('comment')}*\n"
                    
                    final_text = (
                        f"## {report.get('title', '2025 年度动画报告')}\n\n"
                        f"### 📊 年度成分审计\n{stats_md}\n{report.get('intro', '')}\n\n---\n"
                        f"### 🏆 深度评析\n{report.get('body', '')}\n\n> {report.get('conclusion', '')}"
                    )
                    if response_placeholder: response_placeholder.markdown(final_text)

                except Exception as e:
                    st.error(f"数据解析异常: {e}")
                    return raw_json_str

                # (C) 抓取元数据 & 合并数据
                try:
                    status.write("📡 正在准备奖杯与海报...")
                    
                    # 1. 准备搜索映射表: 仅包含非 N/A 的标题
                    search_mapping = {
                        cat: data['title'] 
                        for cat, data in llm_parsed_data.items() 
                        if data['title'] != "N/A"
                    }

                    # 2. 批量联网抓取 (返回 List[Dict])
                    fetched_results = []
                    if search_mapping:
                        fetched_results = self._fetch_card_metadata(search_mapping)
                    
                    # 3. 建立查找索引
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

                    # (D) 绘制图片
                    status.write("🖌️ 正在绘制 2025 年度海报...")
                    img_path = self.draw_grid_image(
                        items_data=card_items,
                        output_filename="year_report_2025.png",
                        cols=4, 
                        title_text="OtakuNeko · 2025年度动画认证：",
                        subtitle_text=f"{user_stats.get('comment_tags', ['2025年度成分鉴定'])[0]}",
                        user_name=self.bgm_service.username,
                        radar_data=radar_data,
                        composition_data=composition_data,
                        otaku_score=user_stats.get('otaku_score', 0)
                    )
                    status.update(label="✅ 年度总结生成完毕", state="complete", expanded=False)

                except Exception as e:
                    status.update(label="⚠️ 生成过程中遇到部分问题", state="error", expanded=True)
                    st.error(f"海报或数据处理失败: {str(e)}")

            # --- 4. 结果展示区 ---
            
            # 创建两列布局：左边放雷达图，右边放核心数据
            col1, col2 = st.columns([1, 1])
            
            with col1:
                st.markdown("### 🧬 属性雷达")
                # 调用上面的绘图函数
                self.plot_radar_chart(radar_data)
            
            with col2:
                st.markdown(f"### 🏷️ **#{user_stats.get('comment_tags', ['2025年度成分鉴定'])[0]}**")
                # 核心指标：垂直居中展示
                st.write("") # 占个空行用来对齐
                st.metric(label="二次元浓度", value=f"{user_stats.get('otaku_score', 0)}%")
                # 进度条紧跟在 metric 下面
                st.progress(user_stats.get('otaku_score', 0) / 100)
                
                st.markdown(f"**🧪 精神成分**：")
                for item in composition_data:
                    # 显示格式：纯爱战神 (40%)
                    st.text(f"{item['label']} ({int(item['value']*100)}%)")
                    st.progress(item['value'])
            
            if card_items:
                st.divider()
                
                # 直接渲染卡片
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
        
        finally:
            # 释放忙碌状态和动作锁
            manager.set_busy_status(session_id, False)
            manager.update_ping(session_id)
            st.session_state.is_processing_year_report = False