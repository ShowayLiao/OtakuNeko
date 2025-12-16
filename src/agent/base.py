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

    # def _generate_card_html(self, item):
    #     """
    #     🎨 生成单张卡片的 HTML (包含评分与短评 - 最终修复版)
    #     """
    #     # 1. 数据提取与清洗
    #     title = item.get('title', '未知作品')
    #     # 标签处理
    #     tag = item.get('category') or item.get('type') or 'Anime'
        
    #     # 评分处理 (过滤 N/A 和 0)
    #     score = item.get('score')
    #     show_score = False
    #     if score and score != 'N/A' and score != 0:
    #         show_score = True
            
    #     # 短评处理 (过滤无效短评)
    #     comment = item.get('comment', '').strip()
    #     show_comment = True if (comment and comment != "AI未提供短评") else False

    #     # 图片处理 (兼容字典或字符串)
    #     img_val = item.get('image', '')
    #     if isinstance(img_val, dict):
    #         img_url = img_val.get('large') or img_val.get('common') or ''
    #     else:
    #         img_url = str(img_val) if img_val else ''
            
    #     subject_id = item.get('id')

    #     # 链接构建
    #     if subject_id:
    #         link = f"https://bgm.tv/subject/{subject_id}"
    #     else:
    #         import urllib.parse
    #         safe_title = urllib.parse.quote(str(title))
    #         link = f"https://bgm.tv/subject_search/{safe_title}?cat=2"

    #     # 2. 构建 HTML 组件 (使用 textwrap.dedent 彻底解决缩进问题)

    #     # [图片组件]
    #     if img_url:
    #         img_div = textwrap.dedent(f"""
    #             <div style='width:100%; height:130px; border-radius:8px 8px 0 0; overflow:hidden; background:#f4f6f8; position: relative;'>
    #                 <img src='{img_url}' style='width:100%; height:100%; object-fit:cover; transition: transform 0.3s;'>
    #             </div>
    #         """).strip()
    #     else:
    #         img_div = textwrap.dedent(f"""
    #             <div style='width:100%; height:130px; background:#f4f6f8; display:flex; align-items:center; justify-content:center; color:#999; font-size:12px; border-radius:8px 8px 0 0;'>
    #                 NO IMG
    #             </div>
    #         """).strip()

    #     # [评分组件]
    #     score_html = ""
    #     if show_score:
    #         score_html = f"<span style='color:#f59e0b; font-weight:700; font-size:11px; margin-left:6px; display:flex; align-items:center;'>⭐ {score}</span>"

    #     # [短评组件]
    #     comment_html = ""
    #     if show_comment:
    #         comment_html = textwrap.dedent(f"""
    #             <div style="margin-top:8px; padding:6px 8px; background:#F7FAFC; border-radius:6px; border:1px solid #EDF2F7;">
    #                 <div style="font-size:11px; color:#5D6D7E; line-height:1.4; font-style:italic; display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; overflow:hidden;">
    #                     “{comment}”
    #                 </div>
    #             </div>
    #         """).strip()

    #     # [标签颜色] (可选：根据类型改变颜色)
    #     tag_bg = "#E3F2FD"
    #     tag_color = "#1565C0"
    #     if tag == "填坑":
    #         tag_bg = "#E8F5E9" # 绿色
    #         tag_color = "#2E7D32"
    #     elif tag == "重温":
    #         tag_bg = "#FFF3E0" # 橙色
    #         tag_color = "#EF6C00"

    #     # 3. 组装最终 HTML
    #     html_template = textwrap.dedent(f"""
    #         <a href="{link}" target="_blank" style="text-decoration:none; color:inherit; display:block; margin-bottom:16px;">
    #             <div style="border:1px solid #EBF1F5; border-radius:10px; background:white; box-shadow: 0 4px 6px rgba(0,0,0,0.02); overflow: hidden; height:100%; transition: transform 0.2s ease;">
                    
    #                 {img_div}
                    
    #                 <div style="padding:10px;">
                        
    #                     <div style="display:flex; align-items:center; justify-content:center; margin-bottom:6px;">
    #                         <span style="background-color:{tag_bg}; color:{tag_color}; padding:2px 8px; border-radius:10px; font-size:10px; font-weight:bold;">{tag}</span>
    #                         {score_html}
    #                     </div>

    #                     <div style="font-size:13px; font-weight:bold; text-align:center; line-height:1.4; color:#2C3E50; height:36px; overflow:hidden; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical;">
    #                         {title}
    #                     </div>

    #                     {comment_html}

    #                 </div>
    #             </div>
    #         </a>
    #     """)
        
    #     return html_template.strip()
    
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
            title = item.get('title', 'Unknown')
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