import json
import os
import textwrap
from concurrent.futures import ThreadPoolExecutor
# 🟢 需要补充引入 PIL 库，因为我们要在这里重写绘图逻辑
from PIL import Image, ImageDraw, ImageFont 

# 假设这些常量在父类文件里，如果引用不到，建议在这里重新定义或者从配置引入
# 这里为了方便直接定义，你可以根据实际情况调整
GRID_IMAGE_PATH = "static/images/grid_profile.png" 

from src.agent import ProfileAgent

class YearAgent(ProfileAgent):
    def __init__(self, client):
        super().__init__(client)
        # 覆写：年度总结专用的 12 个奖项
        self.categories = [
            "最佳动画", "最佳原创", "最佳改编", "最佳画面", 
            "最佳音乐", "最想安利", "最意难平", "最被低估", 
            "最被过誉", "最欢乐", "最抽象", "最炒作"
        ]

    def _load_target_data(self):
        file_path = "data/datasets/dataset_recent_365.json"
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []

    # 🟢 核心修改：在子类中直接重写这个绘图方法
    # 这样就不需要修改父类 ProfileAgent 的代码了
    def _draw_grid_image_from_data(self, items_data, title_text="2025 年度动画赏"):
        print("🎨 [YearAgent] 开始绘制年度海报...")
        
        # --- 布局逻辑 (针对年度总结优化) ---
        count = len(items_data)
        # 强制使用 4列 x 3行 (12个)
        cols = 4 
        rows = 3
            
        cell_w, cell_h = 200, 360 
        margin = 20
        header_h = 80 
        
        total_w = cols * (cell_w + margin) + margin
        total_h = rows * (cell_h + margin) + margin + header_h
        
        bg_color = (30, 30, 35)       
        card_bg_color = (45, 45, 50)  
        text_color = (240, 240, 240)  
        accent_color = (255, 100, 100) 
        
        canvas = Image.new('RGB', (total_w, total_h), bg_color)
        draw = ImageDraw.Draw(canvas)
        
        font_path = "msyh.ttc" 
        try:
            title_font = ImageFont.truetype(font_path, 40)
            tag_font = ImageFont.truetype(font_path, 20)
            name_font = ImageFont.truetype(font_path, 18)
        except:
            title_font = ImageFont.load_default()
            tag_font = ImageFont.load_default()
            name_font = ImageFont.load_default()

        # 🟢 这里使用我们传入的 title_text
        draw.text((margin, 20), f"OtakuMate · {title_text}", font=title_font, fill=text_color)

        for i, item in enumerate(items_data):
            cat = item['category']
            title = item['title']
            img_url = item['image']
            
            col = i % cols
            row = i // cols
            x = margin + col * (cell_w + margin)
            y = header_h + row * (cell_h + margin)
            
            draw.rectangle([x, y, x + cell_w, y + cell_h], fill=card_bg_color)
            
            text_area_h = 70 
            img_area_h = cell_h - text_area_h
            
            if img_url:
                # 调用父类的下载方法 (这个可以复用，不用重写)
                img = self._download_image(img_url)
                if img:
                    try:
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
                    except: pass
            else:
                draw.rectangle([x, y, x + cell_w, y + img_area_h], fill=(60, 60, 65))
                draw.text((x + cell_w//2 - 30, y + img_area_h//2 - 10), "No Image", font=name_font, fill=(150,150,150))

            tag_w, tag_h = 80, 28
            draw.rectangle([x, y, x + tag_w, y + tag_h], fill=accent_color)
            draw.text((x + 5, y + 2), cat, font=tag_font, fill=(0,0,0))
            
            text_start_y = y + img_area_h + 5
            wrapped_title = textwrap.fill(title, width=11) 
            lines = wrapped_title.split('\n')
            display_text = lines[0] + "\n" + lines[1][:9] + "..." if len(lines) > 2 else wrapped_title
            draw.text((x + 5, text_start_y), display_text, font=name_font, fill=text_color, spacing=4)

        os.makedirs(os.path.dirname(GRID_IMAGE_PATH), exist_ok=True)
        # 保存路径也可以改个名字，防止覆盖
        year_path = "static/images/year_report_2025.png"
        canvas.save(year_path)
        return year_path

    def generate_report(self, style="cat"):
        # 1. 加载数据
        watched_list = self._load_target_data()
        if not watched_list:
            def empty_gen(): yield "🚫 近期无数据，无法生成年度总结。"
            return empty_gen()

        mini_data = [{"t": x['title'], "s": x.get('score', 'N/A'), "g": x.get('tags', [])[:3]} for x in watched_list]
        data_str = json.dumps(mini_data, ensure_ascii=False)

        if style == "cat":
            role_desc = "毒舌又傲娇的二次元猫娘评论家 🐱"
            tone_req = "- **口癖**：句尾带“喵”！\n- **态度**：对他的年度选择进行点评。"
            start_msg = "🐱 正在审视你的年度片单喵...\n\n"
        else:
            role_desc = "专业二次元年度赏评委会主席 🧐"
            tone_req = "- **口吻**：庄重、专业、客观。"
            start_msg = "🧐 正在进行年度奖项评选...\n\n"

        prompt = f"""
        # Role: {role_desc}
        
        # Data (Recent Watch History): 
        {data_str}

        # 🎯 Mission: 
        你现在是【2025年度动画赏】的首席评审官。请基于上述观影数据，完成“年度成分审计”与“荣誉颁奖”。

        # Phase 1: 数据洞察 (Internal Thinking)
        在生成回答前，请先分析：
        1. **成分构成**：统计这一年他看了多少部番，什么类型占比最高（是沉迷异世界、还是偏爱硬核科幻、亦或是日常废萌？）。
        2. **评分逻辑**：分析高分作品（Score > 8）的共同基因，找出他的“审美舒适区”。
        3. **奖项匹配**：不要随机分配！要根据作品的实际素质（作画、剧本、音乐）去匹配下方的奖项。

        # Phase 2: 奖项提名 (Mapping Task)
        请从列表中评选出以下奖项（每项 1 部，**必须**是列表里的作品）。
        奖项列表：{json.dumps(self.categories, ensure_ascii=False)}

        # Phase 3: 撰写《2025 年度动画鉴赏报告》 (Analysis Output)
        请撰写一篇有理有据、逻辑严密的年度总结报告。
        
        **文章结构与内容要求：**
        
        1. **📊 年度成分解构**：
           - 开篇先根据 Phase 1 的分析，一针见血地指出他这一年的“二次元成分”。
           - 例如：“这一年你显然是个‘重口味剧情党’，高分作全集中在悬疑类...” 或者 “今年的你急需治愈，日常系作品占据了半壁江山...”。
        
        2. **🏆 核心奖项颁奖词 (重中之重)**：
           - **不要只报菜名！** 对于你选出的重点奖项（如最佳动画、最佳原创、最意难平），必须写出**颁奖词**。
           - **归因分析**：解释**“为什么这部作品能拿这个奖”**。是作画张数爆炸？是剧本逻辑封神？还是单纯的整活太抽象？
           - 结合用户的评分进行佐证（例如：“虽然大家都说烂，但你给了 9 分，说明这部作品的电波正好对上了你...”）。

        3. **📝 结语**：
           - 用一句话总结他的 2025 动画生活。

        **语气风格要求：**
        {tone_req}
        
        - **字数**：不少于 800 字，分析要深入透彻。

        # Output Format (JSON Only):
        {{
            "mapping": {{ "奖项名": "作品名", ... }},
            "analysis": "你的深度分析文本..."
        }}
        """

        try:
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": f"你现在的身份是：{role_desc}"},
                    {"role": "user", "content": prompt}
                ],
                temperature=1.2,
                response_format={"type": "json_object"}, 
                stream=True,
                timeout=120.0 
            )
        except Exception as e:
            def err_gen(): yield f"❌ API Error: {e}"
            return err_gen()

        def process_stream():
            full_content = ""
            yield start_msg
            
            try:
                for chunk in response:
                    if chunk.choices and chunk.choices[0].delta.content:
                        full_content += chunk.choices[0].delta.content
                
                clean_json = full_content.strip()
                if clean_json.startswith("```json"): clean_json = clean_json[7:]
                if clean_json.endswith("```"): clean_json = clean_json[:-3]
                
                result = json.loads(clean_json)
                raw_mapping = result.get("mapping", {})
                
                ordered_mapping = {}
                for cat in self.categories:
                    ordered_mapping[cat] = raw_mapping.get(cat, "N/A")
                
                analysis = result.get("analysis", "")
                yield analysis + "\n\n"
                
                yield "📡 正在同步元数据..."
                items_data = self._fetch_profile_data(ordered_mapping)
                yield {"type": "card_data", "data": items_data}
                
                yield "🎨 正在绘制年度海报..."
                
                # 🟢 调用子类自己的绘图方法 (Override)
                # 注意：这里调用的是 self._draw...，因为我们在本类定义了它，
                # 所以 Python 会优先使用本类的方法，而不是父类的。
                img_path = self._draw_grid_image_from_data(items_data, title_text="2025 年度动画赏")
                
                yield {"type": "image", "path": img_path}

            except Exception as e:
                import traceback
                traceback.print_exc()
                yield f"❌ 处理错误: {str(e)}"

        return process_stream()