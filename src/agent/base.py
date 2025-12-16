# src/agent/base.py
import json
import os
import streamlit as st
from openai import OpenAI
import urllib.parse
from PIL import Image, ImageDraw, ImageFont
import textwrap
from src.BgmServe  import bgm_service
import textwrap
from concurrent.futures import ThreadPoolExecutor

class BaseAgent:
    """
    Agent 基类
    职责：
    1. 提供通用的 LLM 交互方法
    2. 提供通用的 Streamlit 渲染接口 (render)
    3. 默认实现基础的“闲聊”功能
    """
    def __init__(self, client: OpenAI):
        self.client = client
        # 定义配置文件路径，子类可以复用
        self.profile_path = "data/user_profile_summary.txt"
        self.dataset_path = "data/datasets"
        self.font_path = "msyh.ttc"

    def _load_json_file(self, filepath):
        """通用工具：读取 JSON"""
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []

    def _load_user_profile(self):
        """通用工具：读取用户画像"""
        if os.path.exists(self.profile_path):
            with open(self.profile_path, 'r', encoding='utf-8') as f:
                return f.read()[:2000]
        return "用户是一位普通的二次元爱好者。"

    def run(self, messages, temperature=0.7, stream=True, model="deepseek-chat"):
        """
        🧠 [Backend] 核心思考逻辑
        默认行为：调用 LLM 进行普通对话
        """
        try:
            response = self.client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                stream=stream,
                timeout=60
            )
            return response
        except Exception as e:
            print(f"❌ LLM Error: {e}")
            return None

    def render(self, prompt: str, history: list, context_data=None):
        """
        🎨 [Frontend] UI 渲染逻辑
        
        Args:
            prompt: 用户的当前输入
            history: 历史对话记录 (st.session_state.messages)
            context_data: 可选的上下文数据 (如 RAG 检索结果)
        
        Returns:
            str: 最终生成的完整回复文本 (用于存入 session_state)
        """
        # 1. 准备 UI 容器
        response_placeholder = st.empty()
        full_response = ""

        # 2. 准备上下文 (如果提供了额外的 context_data，比如 RAG 检索到的动画列表)
        system_content = "你是一个二次元助手 OtakuNeko。"
        if context_data:
            # 简单的把数据转字符串塞进去，子类可以覆盖这个逻辑
            data_str = json.dumps(context_data[:5], ensure_ascii=False) if isinstance(context_data, list) else str(context_data)
            system_content += f"\n\n参考数据:\n{data_str}"

        # 3. 构建消息链
        # 过滤 history，只取最近的 N 条，并转换为 API 格式
        api_messages = [{"role": "system", "content": system_content}]
        for msg in history[-8:]:
            api_messages.append({"role": msg["role"], "content": msg["content"]})
        
        api_messages.append({"role": "user", "content": prompt})

        # 4. 调用后端逻辑 (流式)
        stream = self.run(api_messages, stream=True)

        # 5. 执行渲染循环
        if stream:
            try:
                for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        full_response += content
                        # 实时刷新 UI
                        response_placeholder.markdown(full_response + "▌")
            except Exception as e:
                st.error(f"生成中断: {e}")
                full_response += "\n[System Error: 连接中断]"
        
        # 6. 渲染最终结果 (去掉光标)
        response_placeholder.markdown(full_response)
        
        return full_response
    
    # src/agent/base.py

    def render_cards(self, items: list, cols=3):
        """
        🎨 响应式卡片网格渲染 (Native Streamlit Version)
        """
        if not items: return

        # 创建网格列
        grid_cols = st.columns(cols)

        for i, item in enumerate(items):
            with grid_cols[i % cols]:
                # --- 1. 数据提取与清洗 (保留原逻辑) ---
                title = item.get('title', '未知作品')
                
                # 标签处理
                tag = item.get('category') or item.get('type') or 'Anime'
                
                # 评分处理
                score = item.get('score')
                score_display = ""
                if score and score != 'N/A' and score != 0:
                    score_display = f"⭐ {score}"

                # 图片处理 (兼容字典或字符串)
                img_val = item.get('image', '')
                if isinstance(img_val, dict):
                    img_url = img_val.get('large') or img_val.get('common') or ''
                else:
                    img_url = str(img_val) if img_val else ''

                # 链接构建
                subject_id = item.get('id')
                if subject_id:
                    link_url = f"https://bgm.tv/subject/{subject_id}"
                else:
                    import urllib.parse
                    safe_title = urllib.parse.quote(str(title))
                    link_url = f"https://bgm.tv/subject_search/{safe_title}?cat=2"

                # 颜色逻辑 (保留原有配色风格)
                if tag == "填坑":
                    bg_c, txt_c = "#E8F5E9", "#2E7D32" # 绿色
                elif tag == "重温":
                    bg_c, txt_c = "#FFF3E0", "#EF6C00" # 橙色
                else:
                    bg_c, txt_c = "#E3F2FD", "#1565C0" # 默认蓝

                # --- 2. 渲染 UI (Native Streamlit Style) ---
                with st.container(border=True):
                    # 采用左图右文布局 (1:1.8 比例)
                    c1, c2 = st.columns([1, 1.8])
                    
                    # 左侧：封面图
                    with c1:
                        if img_url:
                            # use_container_width 替代了 width=100%，自适应容器
                            st.image(img_url, use_container_width=True)
                        else:
                            # 无图占位
                            st.markdown(
                                "<div style='aspect-ratio: 2/3; background:#f4f6f8; display:flex; align-items:center; justify-content:center; color:#ccc; border-radius:4px; font-size:12px;'>No Img</div>", 
                                unsafe_allow_html=True
                            )

                    # 右侧：信息区
                    with c2:
                        # 标签 + 评分行 (HTML渲染以保持样式紧凑)
                        st.markdown(
                            f"""<div style='margin-bottom:6px; line-height:1;'>
                                <span style='background-color:{bg_c}; color:{txt_c}; padding:2px 6px; border-radius:4px; font-size:10px; font-weight:bold; vertical-align:middle;'>{tag}</span> 
                                <span style='font-size:11px; font-weight:bold; color:#f59e0b; margin-left:4px; vertical-align:middle;'>{score_display}</span>
                            </div>""", 
                            unsafe_allow_html=True
                        )
                        
                        # 标题 (加粗)
                        st.markdown(f"**{title}**")

                        # 短评 (如果有则显示为注释样式)
                        comment = item.get('comment', '').strip()
                        if comment and comment != "AI未提供短评":
                            # 限制显示长度，避免卡片过长
                            st.caption(f"_{comment}_")

                        # 底部按钮
                        st.link_button("详情", link_url, use_container_width=True)

    
    # ==========================================================
    # 🎨 通用绘图组件 (Draw Grid Image)
    # ==========================================================

    def draw_grid_image(self, items_data, output_filename="grid_output.png", cols=5, title_text="OtakuMate · 成分鉴定"):
        """
        🎨 通用方法：将数据列表绘制成网格长图并保存
        Args:
            items_data: 包含 {'category', 'title', 'image'} 的列表
            output_filename: 保存的文件名
            cols: 列数
            title_text: 图片顶部的大标题
        Returns:
            str: 保存的图片绝对路径
        """
        print(f"🎨 [BaseAgent] 开始绘制图片: {title_text}...")
        
        # 1. 布局计算
        count = len(items_data)
        rows = (count + cols - 1) // cols
        
        cell_w, cell_h = 200, 360 
        margin = 20
        header_h = 100 # 标题区域高度
        
        total_w = cols * (cell_w + margin) + margin
        total_h = rows * (cell_h + margin) + margin + header_h
        
        # 2. 颜色配置 (莫兰迪暗色系)
        bg_color = (30, 30, 35)       
        card_bg_color = (45, 45, 50)  
        text_color = (240, 240, 240)  
        accent_color = (255, 100, 100) 
        
        canvas = Image.new('RGB', (total_w, total_h), bg_color)
        draw = ImageDraw.Draw(canvas)
        
        # 3. 加载字体
        try:
            title_font = ImageFont.truetype(self.font_path, 40)
            tag_font = ImageFont.truetype(self.font_path, 20)
            name_font = ImageFont.truetype(self.font_path, 18)
        except:
            # 兜底字体
            title_font = ImageFont.load_default()
            tag_font = ImageFont.load_default()
            name_font = ImageFont.load_default()

        # 4. 绘制标题
        draw.text((margin, 30), title_text, font=title_font, fill=text_color)

        # 5. 循环绘制卡片
        for i, item in enumerate(items_data):

            # 兼容不同字段名
            cat = item.get('category') or item.get('type') or ""
            raw_title = item.get('title', 'Unknown')

            if raw_title is None:
                title = "Unknown"
            else:
                title = str(raw_title)

            img_url = item.get('image')
            
            col = i % cols
            row = i // cols
            x = margin + col * (cell_w + margin)
            y = header_h + row * (cell_h + margin)
            
            # 卡片背景
            draw.rectangle([x, y, x + cell_w, y + cell_h], fill=card_bg_color)
            
            text_area_h = 70 
            img_area_h = cell_h - text_area_h
            
            # 绘制图片
            has_img = False
            if img_url:
                # 调用 Service 下载图片 (返回 PIL 对象)
                img = bgm_service.download_image(img_url)
                if img:
                    try:
                        # 居中裁剪算法 (Center Crop)
                        img_ratio = img.width / img.height
                        target_ratio = cell_w / img_area_h
                        if img_ratio > target_ratio:
                            new_h = img_area_h
                            new_w = int(new_h * img_ratio)
                            img = img.resize((new_w, new_h), Image.LANCZOS)
                            left = (new_w - cell_w) // 2
                            img = img.crop((left, 0, left + cell_w, new_h))
                        else:
                            new_w = cell_w
                            new_h = int(new_w / img_ratio)
                            img = img.resize((new_w, new_h), Image.LANCZOS)
                            top = (new_h - img_area_h) // 2
                            img = img.crop((0, top, cell_w, top + img_area_h))
                        
                        canvas.paste(img, (x, y))
                        has_img = True
                    except Exception as e:
                        print(f"图片处理失败: {e}")
            
            # 无图占位
            if not has_img:
                draw.rectangle([x, y, x + cell_w, y + img_area_h], fill=(60, 60, 65))
                draw.text((x + cell_w//2 - 30, y + img_area_h//2 - 10), "No Image", font=name_font, fill=(150,150,150))

            # 绘制标签 (左上角)
            if cat:
                tag_w = len(cat) * 20 + 10 # 简单估算宽度
                tag_h = 28
                draw.rectangle([x, y, x + tag_w, y + tag_h], fill=accent_color)
                draw.text((x + 5, y + 2), cat, font=tag_font, fill=(0,0,0))
            
            # 绘制标题 (底部)
            text_start_y = y + img_area_h + 5
            # 自动换行
            wrapped_title = textwrap.fill(title, width=11) 
            lines = wrapped_title.split('\n')
            # 最多显示2行
            display_text = lines[0]
            if len(lines) > 1:
                display_text += "\n" + (lines[1][:9] + "..." if len(lines[1]) > 9 else lines[1])
            
            draw.text((x + 5, text_start_y), display_text, font=name_font, fill=text_color, spacing=4)

        # 6. 保存文件
        save_path = os.path.join("data", output_filename)
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        canvas.save(save_path)
        print(f"✅ 图片已保存: {save_path}")
        return save_path
    
    # 🟢 [新增] 健壮的分数提取函数
    def _extract_score(self, subject_data):
        """
        从 bgm_service 返回的数据中安全提取分数
        兼容: 
        1. {'score': 8.5} (API v0)
        2. {'rating': {'score': 8.5}} (Legacy API)
        3. 8.5 (Direct value)
        """
        if not subject_data: return 'N/A'
        
        score = None
        
        # 情况1: 直接在根目录的 score 字段
        raw_score = subject_data.get('score')
        
        if isinstance(raw_score, (int, float)):
            score = raw_score
        elif isinstance(raw_score, dict):
            # 情况2: score 是一个字典 {'score': 8.5, 'total': ...}
            score = raw_score.get('score')
        
        # 情况3: 在 rating 字段里 (旧版数据常见)
        if not score:
            rating = subject_data.get('rating')
            if isinstance(rating, dict):
                score = rating.get('score')

        # 最终校验
        if score and isinstance(score, (int, float)) and score > 0:
            return round(score, 1) # 保留一位小数
            
        return 'N/A'
    
    def _fetch_dataset(self, file_path: str = None, status_filter: str = None, limit: int = 0, days: int = 0) -> list:
        """
        📂 通用数据加载 (基类公共方法 - 增强版)
        
        策略: 
        1. 若提供 file_path，优先尝试读取 JSON 文件。
        2. 若文件读取为空，且提供了 status_filter，则从数据库加载。
        3. 支持 status 过滤、时间范围过滤 (days)、数量限制 (limit)。
        4. 返回原始 List[Dict]，不做字段裁剪。

        :param file_path: JSON 文件路径
        :param status_filter: 状态过滤 (如 'watched', 'on_hold')
        :param limit: 数量限制 (0为不限制)
        :param days: 时间范围限制，提取最近 X 天的记录 (0为不限制)
        """
        from datetime import datetime, timedelta

        data = []

        # --- 1. 优先读取文件 ---
        if file_path:
            data = self._load_json_file(file_path)

        # --- 2. 数据库兜底逻辑 ---
        if not data and status_filter:
            try:
                # A. 加载全量
                full_records = bgm_service.load_local_records()
                
                # B. 状态过滤
                filtered_records = [x for x in full_records if x.get('status') == status_filter]
                
                # C. 时间范围过滤 (新增逻辑 🟢)
                if days > 0:
                    now = datetime.now()
                    cutoff_date = now - timedelta(days=days)
                    time_filtered = []
                    
                    for item in filtered_records:
                        updated_at_str = item.get('updated_at', '')
                        if not updated_at_str: continue
                        
                        try:
                            # 截取日期部分 (YYYY-MM-DD) 进行解析，兼容性更好
                            date_str = updated_at_str[:10]
                            item_date = datetime.fromisoformat(date_str)
                            
                            if item_date >= cutoff_date:
                                time_filtered.append(item)
                        except:
                            continue # 解析失败则跳过
                    
                    filtered_records = time_filtered

                # D. 排序 (始终按时间倒序)
                filtered_records.sort(key=lambda x: x.get('updated_at', ''), reverse=True)
                
                # E. 数量截取
                if limit > 0:
                    data = filtered_records[:limit]
                else:
                    data = filtered_records
                    
            except Exception as e:
                print(f"❌ [BaseAgent] 读取本地数据库失败: {e}")

        return data
    
    def _extract_data(self, items: list, *fields) -> str:
        """
        🧬 动态提取数据 (支持 *args 传入任意多个字段)
        
        :param items: 数据列表
        :param fields: 需要提取的字段名 (字符串)。
                       例如: "title", "director", "cv"
        :return: JSON 字符串列表
        """
        import json

        formatted_list = []
        if not items:
            return json.dumps([], ensure_ascii=False)

        for item in items:
            parts = []
            
            # 🔄 遍历用户传入的每一个字段名 (*args)
            for field in fields:
                # 1. 安全获取值
                val = item.get(field)
                
                # 2. 空值跳过 (根据需求，也可以填 "无")
                if not val and val != 0: 
                    continue
                
                # 3. 类型自动处理
                if isinstance(val, list):
                    #如果是列表 (如 tags: []), 转成字符串 "[A,B]"
                    val_str = f"[{','.join(str(x) for x in val)}]"
                else:
                    # 如果是普通值 (如 year: 2025, cv: "xxx"), 直接转字符串
                    val_str = str(val).strip()
                
                # 4. 存入片段
                # 这里做了一个小优化：如果提取的不是标题，加上 Key 前缀方便 AI 理解
                # (你可以根据喜好决定要不要加这个 field+":")
                if field == 'title':
                    parts.append(f"《{val_str}》")
                else:
                    # 例如: "director:今井友紀子"
                    parts.append(f"{field}:{val_str}")
            
            # 5. 将该条目的所有字段用空格或 | 拼起来
            if parts:
                formatted_list.append(" ".join(parts))

        return json.dumps(formatted_list, ensure_ascii=False)
    
    def _batch_fetch_card_items(self, titles: list) -> dict:
        """
        🏭 [公共工厂] 批量并发抓取并生成基础卡片 Item
        
        :param titles: 需要搜索的标题列表 ["标题A", "标题B"]
        :return: 字典映射 {"原标题": {基础卡片数据}, ...}
        """
        # 去重，避免重复请求
        unique_titles = list(set([t for t in titles if t]))
        results_map = {}

        def fetch_single(raw_title):
            # 1. 调用 Service 搜索
            search_res = bgm_service.search_subject(raw_title,"id","name_cn","name","images","score")
            
            if not search_res:
                print(f"⚠️ [Fetch Fail] 搜不到: {raw_title}")
                return raw_title, None

            # 2. 提取核心数据
            imgs = search_res.get('images', {})
            if not isinstance(imgs, dict): imgs = {}
            img_url = imgs.get('large') or imgs.get('common') or ""

            # 3. 构造基础卡片 (预留业务字段)
            item = {
                "id": int(search_res['id']),
                # 优先用中文名
                "title": search_res.get('name_cn') or search_res.get('name'),
                "image": img_url,
                # 复用你之前的提取分数逻辑
                "score": self._extract_score(search_res),
                
                # ⏳ 待子类填充的字段
                "type": "",      
                "category": "",
                "comment": "",
                
                # 保留原始搜索词，方便子类回溯
                "_raw_search_key": raw_title 
            }
            return raw_title, item

        # 4. 并发执行
        with ThreadPoolExecutor(max_workers=5) as executor:
            # 使用 map 可以稍微简化代码，但为了处理 None 方便，这里用 submit 列表也可以
            # 这里为了简单直接用 map 获取结果迭代器
            futures = [executor.submit(fetch_single, t) for t in unique_titles]
            for future in futures:
                try:
                    r_title, r_item = future.result()
                    if r_item:
                        results_map[r_title] = r_item
                except Exception as e:
                    print(f"❌ Meta Fetch Error: {e}")

        return results_map
    
    def _load_recent_watched_strs(self,recent=730):
        """加载最近看过的番剧 (用于Prompt上下文避免重复)"""
        path = os.path.join(self.dataset_path, f"dataset_recent_{recent}.json")
        recent_all = self._fetch_dataset(file_path=path, status_filter="watched", limit=0, days=recent)
        return self._extract_data(recent_all, "title","id")