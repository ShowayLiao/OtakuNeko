# src/agent.py
import json
import os
import requests
import io
import textwrap
import time
import httpx # 引入 httpx 处理网络错误
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from PIL import Image, ImageDraw, ImageFont
from concurrent.futures import ThreadPoolExecutor
from openai import OpenAI
from src.data_processor import load_source_data
from src.bgm_sync import search_subject
from src.vector_store import vector_store

PROFILE_PATH = "data/user_profile_summary.txt"
GRID_IMAGE_PATH = "data/profile_grid.png"

# 定义通用的请求头
IMAGE_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Referer": "https://bgm.tv/"
}

class IntentRouter:
    def __init__(self, client: OpenAI):
        self.client = client

    def classify(self, user_input):
        print(f"🧠 [Router] 收到指令: {user_input[:20]}...")
        
        system_prompt = """
        你是 OtakuMate 的中控大脑。请分析用户的输入，提取意图并输出 JSON 格式。
        
        可选的意图 (intent) 类型：
        1. PROFILE: 生成画像、喜好总结、年度总结、成分表。
        2. RECOMMEND: 求推荐番剧、剧荒、找番、有什么好看的。
        3. GENERATE: 规划排期、生成日历。
        4. CHAT: 其他闲聊。

        ⚠️ 必须严格遵守以下 JSON 格式输出：
        {
            "intent": "类型", 
            "tags": ["标签1", "标签2"] 
        }

        逻辑规则：
        - 如果 intent 是 "RECOMMEND"：请根据用户描述，提取或联想至少 10 个相关的二次元风格标签。
        - 如果是其他 intent：tags 字段留空数组 []。
        """
        
        try:
            # 🟢 关键修复：增加 timeout=10，防止路由卡死
            print("🧠 [Router] 发送请求给 DeepSeek...")
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_input}
                ],
                temperature=0.1,
                response_format={"type": "json_object"},
                timeout=10.0 # 10秒超时，防止卡住
            )
            content = response.choices[0].message.content
            print(f"🧠 [Router] 收到响应: {content}")
            
            data = json.loads(content)
            intent = data.get("intent", "CHAT").strip().upper()
            tags = data.get("tags", [])
            
            if intent not in ['PROFILE', 'RECOMMEND', 'GENERATE', 'CHAT']:
                return 'CHAT', []
            return intent, tags
            
        except Exception as e:
            print(f"❌ [Router] 路由失败 (已回退到 CHAT): {e}")
            # 出错或超时直接当做普通聊天，不要卡住页面
            return 'CHAT', []

class ProfileAgent:
    def __init__(self, client: OpenAI):
        self.client = client
        self.categories = [
            "最治愈", "最搞笑", "最感动", "最热血", "最轻松",
            "最虐心", "最三角", "最震撼", "最抽象", "最写实",
            "最恐怖", "最电波", "最恋爱", "最战斗", "最奇幻",
            "最科幻", "最悬疑", "最智斗", "最讨厌", "最小众"
        ]

    def _load_watched_data(self):
        file_path = "data/datasets/dataset_watched.json"
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        all_data = load_source_data()
        return [x for x in all_data if x.get('status') == 'watched']

    def _download_image(self, url):
        """下载图片转 PIL"""
        if not url: return None
        session = requests.Session()
        retries = Retry(total=3, backoff_factor=0.5, status_forcelist=[500, 502, 503, 504])
        session.mount('http://', HTTPAdapter(max_retries=retries))
        session.mount('https://', HTTPAdapter(max_retries=retries))
        try:
            resp = session.get(url, headers=IMAGE_HEADERS, timeout=10)
            if resp.status_code == 200:
                return Image.open(io.BytesIO(resp.content))
        except: pass
        return None

    def _fetch_subject_detail(self, subject_id):
        url = f"https://api.bgm.tv/v0/subjects/{subject_id}"
        headers = {"User-Agent": "OtakuMate/1.0"}
        try:
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                return resp.json()
        except: pass
        return None

    # 🟢 新增：智能模糊匹配算法
    def _find_best_match(self, query_title, local_db):
        """
        在本地库中寻找最佳匹配项
        策略：
        1. 精确匹配
        2. 忽略大小写匹配
        3. 子串匹配 (AI 标题是 DB 标题的一部分，或者反过来)
        """
        if not query_title or query_title == "N/A": return None
        
        # 1. 精确匹配 (Hash Map O(1))
        if query_title in local_db:
            return local_db[query_title]

        # 准备数据进行遍历匹配
        query_norm = query_title.lower().strip()
        
        # 2. 遍历查找 (O(N)) - 因为 watched 列表通常 < 2000，速度很快
        # 优先级：完全包含 > 部分重叠
        
        candidates = []
        for db_title, item in local_db.items():
            db_norm = db_title.lower().strip()
            
            # Case A: AI 标题是 DB 标题的子串 (例如 AI: "Fate HF", DB: "剧场版 Fate HF")
            if query_norm in db_norm:
                # 记录匹配长度差，差越小越精确
                diff = len(db_norm) - len(query_norm)
                candidates.append((diff, item))
                continue
                
            # Case B: DB 标题是 AI 标题的子串 (罕见，但防止 AI 加了奇怪后缀)
            if db_norm in query_norm:
                diff = len(query_norm) - len(db_norm)
                candidates.append((diff, item))
                continue

        # 如果有候选，返回长度差最小的那个 (最接近的)
        if candidates:
            candidates.sort(key=lambda x: x[0])
            return candidates[0][1]

        return None

    def _fetch_profile_data(self, mapping):
        print("🔍 启动智能模糊检索模式 (Fuzzy Match)...")
        
        # 构建本地查找表
        watched_list = self._load_watched_data()
        local_db = {item['title']: item for item in watched_list}
        
        tasks = []
        for cat in self.categories:
            title = mapping.get(cat, "N/A")
            tasks.append((cat, title))

        def fetch_task(args):
            cat, title = args
            item = {
                "category": cat,
                "title": title,
                "image": "",
                "score": "N/A",
                "id": None
            }
            if title == "N/A" or not title: return item
            
            # 🟢 使用智能匹配替代直接 key lookup
            match_item = self._find_best_match(title, local_db)
            
            if match_item:
                # ✅ 命中本地数据
                sid = match_item.get('id')
                item['title'] = match_item.get('title') # 修正为本地准确标题
                
                if sid:
                    item['id'] = sid
                    item['score'] = match_item.get('score', 'N/A')
                    
                    # 尝试用 ID 获取高清图
                    detail = self._fetch_subject_detail(sid)
                    if detail:
                        imgs = detail.get('images') or {}
                        item['image'] = imgs.get('large') or imgs.get('common') or ""
                    else:
                        item['image'] = match_item.get('image', '')
                    return item

            # 🟡 依然没命中 (兜底搜索)
            print(f"⚠️ 本地彻底未命中，网络搜索兜底: {title}")
            data = search_subject(title)
            if data:
                imgs = data.get('images') or {}
                item['image'] = imgs.get('large') or imgs.get('common') or ""
                item['score'] = data.get('score', 'N/A')
                item['id'] = data.get('id')
                item['title'] = data.get('name_cn') or data.get('name') # 修正标题
            
            return item

        results = []
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(fetch_task, tasks))
            
        return results

    def _draw_grid_image_from_data(self, items_data):
        print("🎨 开始绘制像素...")
        cols = 5
        rows = 4
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

        draw.text((margin, 20), "OtakuMate · 二次元成分鉴定", font=title_font, fill=text_color)

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
            
            if not img_url:
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
        canvas.save(GRID_IMAGE_PATH)
        return GRID_IMAGE_PATH

    def save_profile_to_disk(self, text):
        with open(PROFILE_PATH, 'w', encoding='utf-8') as f:
            f.write(text)

    def generate_persona_and_grid(self, style="cat"):
        watched_list = self._load_watched_data()
        if not watched_list:
            def empty_gen(): yield "🚫 无数据，无法生成。"
            return empty_gen()

        mini_data = [{"t": x['title'], "s": x['score'], "g": x.get('tags', [])[:3]} for x in watched_list]
        data_str = json.dumps(mini_data, ensure_ascii=False)

        # 🟢 升级版 Prompt 配置
        if style == "cat":
            role_desc = "毒舌又傲娇的二次元猫娘评论家 🐱"
            start_msg = "🐱 正在嗅探你的成分喵（猫耳抖动中）...\n\n"
            # 猫娘的“思维链”要求
            tone_req = """
            - **人设核心**：你是一只见过大世面的猫娘，对铲屎官（用户）的品味总是各种嫌弃，但看到真正的好作品也会忍不住摇尾巴。
            - **口癖强制**：句尾必须带“喵”！语气要傲娇（Tsundere），比如“哼，别以为我不知道你在想什么”。
            - **攻击性**：对于媚宅、废萌、无脑爽番，要毫不留情地用猫爪拍打（毒舌吐槽）；对于有深度的作品，可以勉强承认“还不赖”。
            - **心理分析**：把用户的观影喜好和他的现实生活状态联系起来，比如“看这么多异世界，现实里一定很想逃避工作吧喵”。
            """
        else:
            role_desc = "专业、理性且洞察力极强的资深二次元主编/影评人 🧐"
            start_msg = "🧐 正在查阅您的观影记录，构建审美模型...\n\n"
            # 专家的“思维链”要求
            tone_req = """
            - **人设核心**：你不需要卖萌，你是权威。你的分析应当像一篇发表在《Animage》或《Newtype》上的深度专栏。
            - **分析维度**：
              1. **评分逻辑**：分析用户打出高分(9-10)和低分(1-5)的共同点，找出他的“审美G点”和“雷点”。
              2. **题材光谱**：判断他是“单一食性”（只看某类）还是“杂食党”。
              3. **叙事偏好**：他更看重剧情逻辑（硬核），还是更看重角色与画风（氛围党）？
            - **语言风格**：使用精准的评论术语（如：叙事节奏、演出效果、世界观构建、角色弧光）。
            """

        prompt = f"""
        # Role: {role_desc}
        
        # User Data (Raw History):
        {data_str}

        # Task 1: 成分提取 (Grid Mapping)
        从列表中选出最符合以下 20 个标签的动画（每项 1 部，**严禁重复**，优先选择高分作）：
        标签：{json.dumps(self.categories, ensure_ascii=False)}

        # Task 2: 灵魂侧写 (Deep Analysis)
        请基于用户的阅片记录，写一段不少于 **600字** 的深度分析报告。
        
        **分析逻辑 (必须遵循):**
        1.  **审美舒适区判定**：通过他打高分的作品，总结他的核心取向（例如：是喜欢“黑深残”的哲学思考，还是“日常系”的治愈，亦或是“超展开”的电波？）。
        2.  **雷点/避坑侦测**：如果列表中有低分或抛弃的作品，分析他讨厌什么（例如：讨厌圣母主角、讨厌强行煽情、讨厌谜语人？）。
        3.  **潜在性格映射**：**这是重点！** 像心理侧写师一样，推测这种审美背后的性格特质（例如：理想主义者、孤独的观察者、渴望热血的中二病、或者由于现实压力大而寻求奶头乐的社畜）。
        
        **语气要求:**
        {tone_req}

        # Output Format (JSON Only):
        {{
            "mapping": {{ "标签名": "作品名", ... }},
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
            def err_gen(): yield f"❌ API 请求启动失败: {e}"
            return err_gen()

        def process_stream():
            full_content = ""
            yield start_msg
            
            try:
                for chunk in response:
                    if chunk.choices and chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        full_content += content
                
                clean_json = full_content.strip()
                if clean_json.startswith("```json"): clean_json = clean_json[7:]
                if clean_json.endswith("```"): clean_json = clean_json[:-3]
                
                if not clean_json: raise ValueError("生成内容为空")

                result = json.loads(clean_json)
                mapping = result.get("mapping", {})
                analysis = result.get("analysis", "分析生成失败。")
                
                yield analysis + "\n\n"
                
                yield "📡 正在本地数据库进行智能匹配..."
                items_data = self._fetch_profile_data(mapping)
                
                yield {"type": "card_data", "data": items_data}
                
                yield "🎨 正在后台绘制高清存档图..."
                img_path = self._draw_grid_image_from_data(items_data)
                yield {"type": "image", "path": img_path}
                
                self.save_profile_to_disk(analysis)

            except Exception as e:
                import traceback
                traceback.print_exc()
                yield f"❌ 处理错误: {str(e)}"

        return process_stream()

class RecommendAgent:
    """
    🕵️ 深度推荐 Agent (RAG + 风格化 + 并发加速版)
    """
    def __init__(self, client: OpenAI):
        self.client = client

    def _load_profile(self):
        if os.path.exists(PROFILE_PATH):
            with open(PROFILE_PATH, 'r', encoding='utf-8') as f:
                return f.read()[:2000]
        return "用户是一位二次元爱好者。"

    def _load_dataset(self, filename):
        path = f"data/datasets/{filename}"
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return []
    
    # 🟢 新增：加载最近记录
    def _load_recent_watched(self):
        path = "data/datasets/dataset_recent_730.json"
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                # 再次精简，只转成字符串列表
                data = json.load(f)
                return [f"《{x['title']}》" for x in data]
        return []

    def _get_exclusion_set(self):
        watched = self._load_dataset("dataset_watched.json")
        dropped = self._load_dataset("dataset_dropped.json")
        exclude_ids = set()
        for x in watched + dropped:
            if x.get('id'): exclude_ids.add(int(x['id']))
        exclude_titles = set(x['title'] for x in watched + dropped)
        return exclude_ids, exclude_titles

    def _get_full_backlog(self):
        wish = self._load_dataset("dataset_wish.json")
        doing = self._load_dataset("dataset_doing.json")
        on_hold = [x for x in doing if x['status'] == 'on_hold']
        def simplify(lst):
            return [f"《{x['title']}》(标签:{','.join(x.get('tags',[])[:3])})" for x in lst]
        return simplify(wish), simplify(on_hold)
    
    def _rag_retrieve(self, user_query, tags, top_k=20):
        search_text = f"风格标签: {', '.join(tags)}。 用户描述: {user_query}"
        results = vector_store.search(search_text, top_k=top_k)
        return results
    
    def _fetch_subject_detail(self, subject_id):
        """通过 ID 获取条目详情（包含准确评分）"""
        url = f"https://api.bgm.tv/v0/subjects/{subject_id}"
        headers = {"User-Agent": "OtakuMate/1.0"}
        try:
            resp = requests.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                return resp.json()
        except:
            pass
        return None

    def _extract_score(self, subject_data):
        if not subject_data: return 'N/A'
        rating = subject_data.get('rating')
        if rating and isinstance(rating, dict):
            score = rating.get('score')
            if score and score > 0: return score
        score = subject_data.get('score')
        if score and score > 0: return score
        return 'N/A'

    def execute(self, user_query, status_callback, tags=None, style="normal"):
        if not tags: tags = []
        
        # Step 0: 准备去重数据
        exclude_ids, exclude_titles = self._get_exclusion_set()

        # Step 1: 本地 RAG
        status_callback(f"🔦 正在检索记忆库...", state="running")
        relevant_history = self._rag_retrieve(user_query, tags, top_k=20)
        history_context_str = json.dumps(relevant_history, ensure_ascii=False)
        
        # Step 2: 准备库存
        wish_strs, hold_strs = self._get_full_backlog()
        
        # 🟢 加载最近记录
        recent_watched_titles = []
        if hasattr(self, '_load_recent_watched'):
            recent_watched_titles = self._load_recent_watched()

        # Step 3: 构建 Prompt
        status_callback("🧠 猫娘嗅探你的喜好（摇动耳朵）...", state="running")
        user_profile = self._load_profile()
        
        if style == "cat":
            role_def = "你是 OtakuMate，一只毒舌又傲娇的二次元猫娘管家 🐱。"
            tone_req = "整体推荐语要傲娇，句尾带'喵'。短评要毒舌。如果推荐了老番，记得说是'重温经典'。"
        else:
            role_def = "你是 OtakuMate，一位专业、理性的二次元管家。"
            tone_req = "整体专业。短评一针见血。如果推荐了已看过的作品，侧重分析重温价值。"

        final_prompt = f"""
        # Role
        {role_def}

        # User Profile
        {user_profile}
        
        # User Request
        需求: "{user_query}" (Tag: {tags})

        # Reference (相似喜好 - 可以与这些类似的作品，但推荐的绝不能与这些重复)
        {history_context_str}
        * 强调！！！ 推荐的绝不能与参考内容重复！！！
        
        # Recent History (最近已看 - 推荐的绝不能与这些重复)
        {json.dumps(recent_watched_titles, ensure_ascii=False)}
        * 强调！！！ 推荐的绝不能与最近已看重复！！！

        # Inventory
        - [Wish/Hold]: {json.dumps(wish_strs[:50], ensure_ascii=False)}

        # Mission
        请推荐 2 组动画，Output JSON Format:
        1. **backlog** (3部): 从库存挑选。
        2. **new_rec** (11部): 推荐高质量作品。
        3. **reason**: "{tone_req}"
        
        **JSON Data Structure Restriction**:
        Lists MUST contain objects, NOT strings.
        CORRECT: [{{"title": "Name", "comment": "..."}}]
        WRONG: ["Name", ...]

        # Output JSON Only:
        {{
            "reason": "...",
            "backlog": [...],
            "new_rec": [...]
        }}
        """

        try:
            response = self.client.chat.completions.create(
                model="deepseek-chat",
                messages=[{"role": "user", "content": final_prompt}],
                response_format={"type": "json_object"},
                temperature=1.1,
                timeout=60
            )
            result_json = json.loads(response.choices[0].message.content)
        except Exception as e:
            return {"error": f"LLM 决策失败: {e}"}

        # === Step 4: 并发结果回填 ===
        status_callback("📡 正在极速抓取数据 (并发模式)...", state="running")
        
        def fetch_meta_task(entry, tag_type):
            # 🛡️ 容错处理
            if isinstance(entry, str):
                title = entry
                comment = "AI未提供短评"
            elif isinstance(entry, dict):
                title = entry.get('title')
                comment = entry.get('comment', '')
            else:
                return None 

            if not title: return None

            # 基础数据结构
            item_data = {
                "title": title, "type": tag_type, "comment": comment,
                "score": "N/A", "image": "", "id": None
            }

            # 1. 标题去重 (字符串匹配)
            if tag_type == "新推" and title in exclude_titles:
                pass 

            # 2. 搜索 ID
            s_res = search_subject(title)
            if s_res:
                sid = int(s_res['id'])
                
                # 获取详情
                detail_info = self._fetch_subject_detail(sid)
                source_data = detail_info if detail_info else s_res

                item_data['title'] = source_data.get('name_cn') or source_data.get('name')
                item_data['score'] = self._extract_score(source_data)
                item_data['id'] = sid
                images = source_data.get('images') or {}
                item_data['image'] = images.get('common', '') or images.get('large', '')

                # 🟢 核心修改：分数过滤逻辑
                # 如果分数是 N/A 或者 0，直接丢弃该结果
                if item_data['score'] == 'N/A' or item_data['score'] == 0:
                    # 也可以额外检查 rating.total < 50 这种，但 N/A 通常已经涵盖了冷门条目
                    return None

                # 3. 状态变色龙
                if tag_type == "新推":
                    exclude_ids_set, _ = self._get_exclusion_set()
                    if sid in exclude_ids_set:
                        item_data['type'] = "重温"
            else:
                # 搜不到的也丢弃，因为拿不到分数
                return None

            return item_data

        tasks = []
        for entry in result_json.get('backlog', [])[:3]: 
            tasks.append((entry, "填坑"))
        
        # 新推取全部 (AI 给了 11 个)
        for entry in result_json.get('new_rec', []): 
            tasks.append((entry, "新推"))

        results = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            future_to_entry = {executor.submit(fetch_meta_task, t[0], t[1]): t for t in tasks}
            
            for future in future_to_entry:
                try:
                    data = future.result()
                    if data: results.append(data)
                except Exception as e:
                    print(f"Task Error: {e}")

        # === Step 5: 排序与组装 ===
        backlog_items = [x for x in results if x['type'] == "填坑"]
        new_items = [x for x in results if x['type'] == "新推"]
        rewatch_items = [x for x in results if x['type'] == "重温"]
        
        # 组装逻辑：3个填坑 + 6个(新推/重温)
        # 如果填坑不足3个，可以多拿点新推补上吗？
        # 目前保持：填坑最多3个，新推+重温最多6个，总共9个
        
        final_list = backlog_items[:3]
        pool = new_items + rewatch_items
        final_list.extend(pool[:6]) 

        return {
            "reason": result_json.get("reason", "推荐生成完毕"),
            "items": final_list
        }