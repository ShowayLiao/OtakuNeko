# src/agent/recommend.py
import json
import os
import streamlit as st
from concurrent.futures import ThreadPoolExecutor

from .base import BaseAgent
from src.BgmServe import BangumiService
from src.vector_store import get_vector_store, VectorStoreError
from src.config.personas import ROLES, TEMPLATES
from src.utils import get_session_manager, get_session_id
import json_repair

class RecommendAgent(BaseAgent):
    """
    🕵️ 深度推荐 Agent (迁移融合版)
    集成特性：RAG检索 + 库存优先 + 评分过滤 + 状态变色龙(新推转重温) + 并发加速
    """
    def __init__(self, llm_service, bgm_service: BangumiService):
        super().__init__(llm_service, bgm_service)
        self.bgm_service = bgm_service


    def _get_exclusion_set(self):
        """
        [逻辑迁移] 获取排除列表 (看过 + 抛弃)
        用于防止推荐已看过的作品，或者将'新推'修正为'重温'
        """
        
        full_records = self.bgm_service.load_local_records()
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
        wish_all = self._fetch_dataset(file_path=wish_path, status_filter="wish", limit=0)
        on_hold_path = os.path.join(self.dataset_path, "dataset_on_hold.json")
        hold_all = self._fetch_dataset(file_path=on_hold_path, status_filter="on_hold", limit=0)
        combined = wish_all + hold_all
        return self._extract_data(combined, "title", "tags","summary","director","script","cv","year","month","studio")
        

    
        

    def _fetch_recommend_metadata(self, rec_list, exclude_ids, exclude_titles):
        """
        [业务逻辑] 推荐列表组装 (基于公共基类)
        """
        # 1. 准备标题列表
        titles = [item.get('title') for item in rec_list if item.get('title')]
        
        # 2. 调用基类批量获取 (返回字典映射)
        fetched_map = self._batch_fetch_card_items(titles)
        
        final_results = []
        
        # 3. 遍历原始推荐列表，回填数据并过滤
        for rec_item in rec_list:
            raw_title = rec_item.get('title')
            base_card = fetched_map.get(raw_title) # 从缓存字典里取
            
            # 如果没搜到，直接跳过
            if not base_card: continue
            
            # --- 业务逻辑开始 ---
            
            sid = base_card['id']
            # A. ID 过滤 (如果已看过则跳过)
            if sid in exclude_ids:
                # 这里有一个特殊逻辑：如果是“新推”但看过了，改为“重温”；
                # 如果是“填坑”但看过了，直接过滤掉 (假设)
                # 按照你源代码的逻辑：
                if rec_item.get('type') == "新推":
                    rec_item['type'] = "重温" # 修改类型
                else:
                    pass

            # B. 分数过滤 (原代码注释掉的部分，这里保持一致)
            if rec_item.get('type') == "新推" and base_card['score'] == 'N/A': continue

            # --- 回填字段 ---
            # 必须使用 .copy()，因为 fetched_map 里的对象可能是引用，
            final_item = base_card.copy()
            
            final_item['type'] = rec_item.get('type')
            final_item['category'] = final_item['type'] # 保持兼容
            final_item['comment'] = rec_item.get('comment', '')
            
            # 清理内部字段
            final_item.pop('_raw_search_key', None)
            
            final_results.append(final_item)
            
        return final_results

    def render(self, user_query, tags=None, style="cat", session_id=None):
        """
        🎨 [Frontend] 推荐功能主入口
        """
        if not tags: tags = []
        
        # 动作锁：防止重复推荐请求
        if st.session_state.get('is_processing_recommendation'):
            print(f"[动作锁] Session {session_id} 拦截了重复请求")
            return "推荐生成中，请稍候..."
        
        st.session_state.is_processing_recommendation = True
        
        # 获取会话管理器实例
        manager = get_session_manager()
        session_id = session_id or get_session_id()
        
        # 在进入忙碌状态前手动刷新心跳
        manager.update_ping(session_id)
        
        try:
            # 设置忙碌状态
            manager.set_busy_status(session_id, True)
            
            # 1. 准备数据
            exclude_ids, exclude_titles = self._get_exclusion_set()
            print(f"[动作锁] Session {session_id} 开始推荐请求")
        
            # RAG (Enabled)
            search_text = f"风格标签: {', '.join(tags)}。 用户描述: {user_query}"
            rag_history = []
            # 创建一个status容器用于显示向量同步进度
            with st.status("🔄 正在检查向量索引...", expanded=True) as vector_status:
                try:
                    # 使用当前用户的用户名获取LocalVectorStore实例
                    username = st.session_state.user_name if hasattr(st.session_state, 'user_name') else "default_user"
                    vector_store = get_vector_store(username)
                    rag_history = vector_store.search(search_text, top_k=20, log_func=lambda m: vector_status.write(m))
                    vector_status.update(label="✅ 向量索引准备完成", state="complete", expanded=False)
                except VectorStoreError as e:
                    vector_status.update(label="❌ 向量索引处理失败", state="error")
                    st.error(str(e))
                    return f"推荐生成失败: {str(e)}"
            history_context_str = json.dumps(rag_history, ensure_ascii=False)
            
            # Context
            user_profile = self._load_user_profile()
            inventory_str = self._load_inventory_strs()
            recent_watched_str = self._load_recent_watched_strs(730,"title","id")
            
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
                    stream = self.run(messages, temperature=0.8, stream=True, session_id=session_id)
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
                    # Use robust JSON parsing
                    from src.data_processor import robust_json_parse
                    result_data = robust_json_parse(raw_json_str, {})
                    
                    if not result_data:
                        st.error("AI 返回格式异常")
                        return raw_json_str
                        
                    final_reason = result_data.get("reason", "推荐生成完毕。")
                    
                    # 辅助函数：统一处理 item 格式
                    def normalize_item(raw_item, default_type):
                        # print(raw_item)
                        if isinstance(raw_item, dict):
                            return {
                                "title": raw_item.get("title", "Unknown"),
                                "comment": raw_item.get("reason", ""), # ✅ 确保获取 comment
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
                        
                except Exception as e:
                    st.error(f"JSON 解析失败: {e}")
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
        finally:
            # 释放忙碌状态和动作锁
            manager.set_busy_status(session_id, False)
            manager.update_ping(session_id)
            st.session_state.is_processing_recommendation = False