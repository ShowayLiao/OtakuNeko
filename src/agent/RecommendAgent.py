# src/agent/recommend.py
import json
import os
import streamlit as st
from concurrent.futures import ThreadPoolExecutor

from .base import BaseAgent
from src.BgmServe import bgm_service
from src.vector_store import vector_store
from src.config.personas import ROLES, TEMPLATES
import json_repair

class RecommendAgent(BaseAgent):
    """
    🕵️ 深度推荐 Agent (迁移融合版)
    集成特性：RAG检索 + 库存优先 + 评分过滤 + 状态变色龙(新推转重温) + 并发加速
    """
    def __init__(self, client):
        super().__init__(client)

    def _get_exclusion_set(self):
        """
        [逻辑迁移] 获取排除列表 (看过 + 抛弃)
        用于防止推荐已看过的作品，或者将'新推'修正为'重温'
        """
        full_records = bgm_service.load_local_records()
        # 筛选看过(watched)和抛弃(dropped)
        exclude_list = [x for x in full_records if x.get('status') in ['watched', 'dropped']]
        
        exclude_ids = set()
        exclude_titles = set()
        
        for x in exclude_list:
            if x.get('id'): 
                exclude_ids.add(int(x['id']))
            if x.get('title'):
                exclude_titles.add(x['title'])
                
        return exclude_ids, exclude_titles

    def _load_inventory_strs(self):
        """加载库存 (想看 + 搁置)"""
        # 1. 读取想看 (Wish)
        wish_path = os.path.join(self.dataset_path, "dataset_wish.json")
        wish_list = self._load_json_file(wish_path)
        
        # 2. 读取搁置 (OnHold)
        full_records = bgm_service.load_local_records()
        on_hold_list = [x for x in full_records if x.get('status') == 'on_hold']
        
        # 3. 格式化
        inventory = []
        for x in (wish_list + on_hold_list):
            tags = x.get('tags', [])
            tag_str = f"[{','.join(tags[:3])}]" if tags else ""
            inventory.append(f"《{x['title']}》{tag_str}")
            
        return json.dumps(inventory, ensure_ascii=False)

    def _load_recent_watched_strs(self,recent=730):
        """加载最近看过的番剧 (用于Prompt上下文避免重复)"""
        path = os.path.join(self.dataset_path, "dataset_recent_730.json")
        data = self._load_json_file(path)
        
        if not data:
            full_records = bgm_service.load_local_records()
            watched = [x for x in full_records if x.get('status') == 'watched']
            watched.sort(key=lambda x: x.get('updated_at', ''), reverse=True)
            data = watched[:recent]

        titles = [f"《{x['title']}》" for x in data]
        return json.dumps(titles, ensure_ascii=False)



    def _fetch_recommend_metadata(self, rec_list, exclude_ids, exclude_titles):
        """
        [核心逻辑] 并发抓取 + 评分过滤 + 状态修正
        """
        def fetch_task(item):
            raw_title = item.get('title')
            tag_type = item.get('type')
            
            if not raw_title: return None

            # 1. 调用 Service 搜索
            search_res = bgm_service.search_subject(raw_title)

            # # =========== 🐛 DEBUG START ===========
            # print(f"\n📋返回的原始数据结构:")
            # print(json.dumps(search_res, indent=4, ensure_ascii=False))
            # raise Exception("Debug中断")
            # # ============ 🐛 DEBUG END ============
            
            if not search_res:
                print(f"⚠️ [Search Fail] 搜不到: {raw_title}") # Debug log
                return None 

            # 2. 提取核心数据
            sid = int(search_res['id'])
            final_title = search_res.get('name_cn') or search_res.get('name')
            
            # 🟢 使用新的提取函数
            score = self._extract_score(search_res)
            
            # 3. [过滤逻辑] 
            # 只有 "新推" 且 分数为 N/A 时才考虑是否过滤
            # 为了防止推荐太少，这里我们稍微放宽一点：如果搜到了但没分，暂时保留，显示为 N/A
            # 如果你想要严格过滤（没分就不推），把下面这行取消注释：
            # if tag_type == "新推" and score == 'N/A': return None 

            # 4. [状态变色龙] 新推 -> 重温
            final_type = tag_type
            if tag_type == "新推":
                if sid in exclude_ids:
                    final_type = "重温"
            
            # 5. 组装结果
            imgs = search_res.get('images', {})
            # 兼容 images 可能为 None 的情况
            if not isinstance(imgs, dict): imgs = {} 
            img_url = imgs.get('large') or imgs.get('common') or ""

            return {
                "title": final_title,
                "category": final_type, 
                "type": final_type,     
                "comment": item.get('comment', ''),
                "image": img_url,
                "score": score,
                "id": sid
            }

        # 并发执行
        results = []
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(fetch_task, item) for item in rec_list]
            for future in futures:
                try:
                    res = future.result()
                    if res: results.append(res)
                except Exception as e:
                    print(f"Meta Fetch Error: {e}")
        
        return results

    def render(self, user_query, tags=None, style="cat"):
        """
        🎨 [Frontend] 推荐功能主入口
        """
        if not tags: tags = []
        
        # 1. 准备数据
        exclude_ids, exclude_titles = self._get_exclusion_set()
        
        # RAG
        search_text = f"风格标签: {', '.join(tags)}。 用户描述: {user_query}"
        rag_history = vector_store.search(search_text, top_k=20)
        history_context_str = json.dumps(rag_history, ensure_ascii=False)
        
        # Context
        user_profile = self._load_user_profile()
        inventory_str = self._load_inventory_strs()
        recent_watched_str = self._load_recent_watched_strs()
        
        # 2. Prompt
        persona = ROLES.get(style, ROLES["cat"])
        
        system_prompt = f"你现在的身份是：{persona['description']}\n{persona['system_prompt']}"

        final_prompt = TEMPLATES["recommend_logic"].format(
            role_def=system_prompt,
            user_profile=user_profile,
            user_query=user_query,
            tags=tags,
            history_context_str=history_context_str,
            recent_watched_titles=recent_watched_str,
            inventory_str=inventory_str,
            tone_req=persona["tone_requirements"]
        )

        # 3. UI 流程
        final_reason = ""
        final_display_list = []

        with st.status(f"🕵️ {persona['description']} 正在制定补番计划...", expanded=True) as status:
            
            status.write(f"🔍 已检索到 {len(rag_history)} 部相关历史记录...")
            
            # (A) LLM
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": final_prompt}
            ]
            raw_json_str = ""
            
            try:
                stream = self.run(messages, temperature=1.1, stream=True)
                status.write("🧠 正在筛选最佳匹配...")
                for chunk in stream:
                    if chunk.choices and chunk.choices[0].delta.content:
                        raw_json_str += chunk.choices[0].delta.content
            except Exception as e:
                status.update(label="❌ API 调用失败", state="error")
                st.error(f"LLM Error: {e}")
                return "推荐生成失败"

            # (B) JSON 解析
            combined_items_request = []
            try:
                clean_json = raw_json_str.strip()
                if clean_json.startswith("```json"): clean_json = clean_json[7:]
                if clean_json.endswith("```"): clean_json = clean_json[:-3]
                
                result_data = json_repair.loads(raw_json_str)
                final_reason = result_data.get("reason", "推荐生成完毕。")
                
                # 辅助函数：统一处理 item 格式
                def normalize_item(raw_item, default_type):
                    if isinstance(raw_item, dict):
                        return {
                            "title": raw_item.get("title", "Unknown"),
                            "comment": raw_item.get("comment", ""), # ✅ 确保获取 comment
                            "type": default_type
                        }
                    else:
                        # 如果 AI 只返回了字符串标题
                        return {
                            "title": str(raw_item),
                            "comment": "", # 默认空
                            "type": default_type
                        }

                # 处理 backlog
                for item in result_data.get("backlog", []):
                    combined_items_request.append(normalize_item(item, "填坑"))
                
                # 处理 new_rec
                for item in result_data.get("new_rec", []):
                    combined_items_request.append(normalize_item(item, "新推"))
                    
            except json.JSONDecodeError:
                st.error("AI 返回格式异常")
                return raw_json_str

            # (C) 抓取与过滤
            status.write("📡 正在并发获取评分与海报...")
            
            fetched_data = self._fetch_recommend_metadata(
                combined_items_request, 
                exclude_ids, 
                exclude_titles
            )
            
            # (D) 组装 (3 填坑 + 5 其他)
            backlog_items = [x for x in fetched_data if x['type'] == "填坑"]
            other_items = [x for x in fetched_data if x['type'] in ["新推", "重温"]]
            
            final_display_list = backlog_items[:3]
            final_display_list.extend(other_items[:5])
            
            status.update(label=f"✅ 成功生成 {len(final_display_list)} 部推荐", state="complete", expanded=False)

        # 4. 渲染
        st.success(f"🎯 **推荐理由**\n\n{final_reason}")
        
        if final_display_list:
            # 
            self.render_cards(final_display_list, cols=4)
        else:
            st.warning("⚠️ 未能生成有效推荐，请检查网络或放宽搜索条件。")
        
        return final_reason