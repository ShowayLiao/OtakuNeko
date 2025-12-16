import streamlit as st
import os
import time
from dotenv import load_dotenv

# --- 引入自定义模块 ---
from src.services import DataService, LLMService
from src.data_processor import export_categorized_datasets, extract_recent_watched
from src.agent import IntentRouter, ProfileAgent, RecommendAgent, RefinerAgent
from src.vector_store import vector_store
from src.plugins.year_report import YearReportPlugin
from src.BgmServe import bgm_service

# --- 1. 基础配置 & 全局 CSS ---
st.set_page_config(page_title="OtakuNeko", page_icon="🐱", layout="wide")
load_dotenv()

# 🎨 注入全局 CSS (莫兰迪/不饱和风格)
st.markdown("""
<style>
    :root {
        --primary-soft: #EBF3F9;
        --primary-text: #5A7C98;
        --border-color: #DDE6ED;
        --hover-bg: #FFFFFF;
    }
    /* 优化全局按钮 */
    div.stButton > button {
        background-color: var(--primary-soft);
        color: var(--primary-text);
        border: 1px solid var(--border-color);
        border-radius: 12px;
        transition: all 0.2s ease;
    }
    div.stButton > button:hover {
        background-color: var(--hover-bg);
        border-color: var(--primary-text);
        color: #4A6C88;
        transform: translateY(-1px);
        box-shadow: 0 2px 8px rgba(90, 124, 152, 0.1);
    }
    div.stButton > button:active {
        background-color: #E1E9F0;
        transform: translateY(0);
    }
    /* 隐藏部分默认元素 */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
</style>
""", unsafe_allow_html=True)

# 🟢 初始化 Session State
if "messages" not in st.session_state:
    st.session_state.messages = []

# --- 2. 服务与 Agent 初始化 ---
api_key = os.getenv("DEEPSEEK_API_KEY")
if not api_key:
    st.error("❌ 缺少 API Key配置，请检查 .env 文件")
    st.stop()

@st.cache_resource
def init_services():
    return LLMService(api_key=api_key)

llm_service = init_services()

# 实例化 Agents
router = IntentRouter(llm_service.client)
profile_agent = ProfileAgent(llm_service.client)
recommend_agent = RecommendAgent(llm_service.client)
refiner_agent = RefinerAgent(llm_service.client)

# 注册插件
active_plugins = [
    YearReportPlugin(llm_service.client)
]

# 加载聊天所需的记忆数据 (缓存)
@st.cache_data(ttl=300)
def get_cached_memory():
    return DataService.load_and_filter_memory()

memory_data = get_cached_memory()

# --- 3. 侧边栏 (控制台) ---
with st.sidebar:
    st.header("📡 数据同步", help="这里是拉取 Bungumi 你的所有动画收藏")
    if st.button("🔄 一键全量更新"):
        with st.status("🚀 正在执行全量更新流程...", expanded=True) as status:
            status.write("1️⃣ 正在拉取 Bangumi 收藏列表...")
            DataService.perform_sync(deep_sync=False) # 基础同步
            status.write("2️⃣ 正在生成分类数据集...")
            export_categorized_datasets()
            status.write("3️⃣ 正在提取近两年观看记录...")
            extract_recent_watched()
            status.update(label="✅ 全量更新完成", state="complete", expanded=False)
        get_cached_memory.clear()
        st.success("所有数据已更新完毕！")

    with st.expander("🔧 高级维护", expanded=False):
        if st.button("📅 仅重生成近期记录"):
            msg = extract_recent_watched()
            st.caption(f"✅ {msg}")
        if st.button("📦 仅重新分类数据集"):
            msg = export_categorized_datasets()
            st.caption(f"✅ {msg}")

    # === 元数据补全 ===
    st.header("🖼️ 元数据补全", help="补充更新动画的 Staff 和声优信息，影响推荐准确度")
    total_count, pending_count, _ = bgm_service.get_missing_stats()
    st.caption(f"📚 总库: {total_count} | ⏳ 待补: {pending_count}")

    if st.button("🧩 开始补全 (直到完成)", disabled=(pending_count == 0)):
        with st.status("🚀 正在逐个补全数据...", expanded=True) as status:
            processed_count = 0
            while True:
                _, current_pending, next_id = bgm_service.get_missing_stats()
                if current_pending == 0 or not next_id:
                    status.update(label="✅ 补全任务结束", state="complete")
                    break
                
                success, msg = bgm_service.patch_one_item(next_id)
                status.write(f"[{processed_count + 1}] {msg}")
                
                if success: processed_count += 1
                time.sleep(0.5) # 防频控
            
        get_cached_memory.clear()
        st.rerun()

    st.markdown("---")

    # === 助手设置 ===
    st.header("🎭 助手设置")
    persona_options = {"cat": "🐱 毒舌猫娘", "normal": "🧐 专业评论家"}
    selected_style = st.radio(
        "选择语调风格:",
        options=list(persona_options.keys()),
        format_func=lambda x: persona_options[x],
        index=0,
        label_visibility="collapsed"
    )

    st.markdown("---")

    # === 向量库维护 ===
    st.header("🧠 向量知识库", help="管理向量索引")
    if st.button("构建/更新索引"):
        with st.status("🚀 正在启动向量化引擎...", expanded=True) as status:
            try:
                msg = vector_store.build_index(log_func=lambda m: status.write(m))
                status.update(label="✅ 索引构建成功", state="complete")
                st.toast(msg)
            except Exception as e:
                status.update(label="❌ 构建失败", state="error")
                st.error(f"详情: {e}")

    st.markdown("---")
    
    # === 插件入口 (作为 Trigger) ===
    st.header("🧩 扩展插件")
    
    # 辅助函数：侧边栏按钮点击后的回调
    def trigger_plugin_msg(trigger_text):
        st.session_state.messages.append({"role": "user", "content": trigger_text})
    
    for plugin in active_plugins:
        # 定义每个插件的触发关键词
        prompt_text = f"执行插件：{plugin.key}"
        if plugin.key == "✨ 生成 2025 年度动画报告":
            prompt_text = "✨ 生成 2025 年度动画报告"
            
        if st.button(f"📊 {plugin.key}", key=f"plugin_btn_{plugin.key}"):
            trigger_plugin_msg(prompt_text)
            st.rerun()


# --- 4. 主界面逻辑 ---

st.title("🐱 OtakuNeko")
st.caption(f"🚀 Agent Mode Active | 📚 记忆库: {len(memory_data)} 部待看")

# 4.1 渲染历史消息
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 4.2 处理底部输入框
# ⚠️ 注意：这里只负责接收输入并追加到历史，不负责处理。处理逻辑在下面统一进行。
if user_input := st.chat_input("输入'生成我的画像'，或'推荐几部番'..."):
    st.session_state.messages.append({"role": "user", "content": user_input})
    st.rerun() # 强制刷新，交由下面的逻辑处理

# 4.3 核心响应逻辑 (统一状态机)
# 只要历史记录中最后一条是 User 发的，Assistant 就需要响应
if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
    
    last_user_prompt = st.session_state.messages[-1]["content"]

    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        full_response = ""
        
        try:
            # --- Phase A: 插件触发词检测 ---
            # 简单字符串匹配，如果触发词特殊可以改用正则或 Router 里的专门字段
            matched_plugin = None
            if "年度动画报告" in last_user_prompt:
                matched_plugin = next((p for p in active_plugins if p.key == "YEAR_REPORT"), None)
            
            if matched_plugin:
                # 🚀 执行插件逻辑
                with st.status(f"🧩 正在启动 {matched_plugin.key}...", expanded=True) as status:
                    # 插件内部自行处理 UI 渲染，并返回最终 Markdown 结果
                    full_response = matched_plugin.execute(response_placeholder)
                    status.update(label="✅ 执行完成", state="complete", expanded=False)

            # --- Phase B: 常规 Agent 路由 ---
            else:
                # 1. 意图识别
                with st.status("🧠 正在分析意图...", expanded=False) as status:
                    intent, extracted_tags = router.classify(last_user_prompt)
                    status.update(label=f"识别模式: {intent}", state="complete")
                    if intent == "RECOMMEND" and extracted_tags:
                        st.toast(f"已提取特征: {', '.join(extracted_tags[:3])}...")

                # 2. 任务分发
                if intent == "PROFILE":
                    # 🔥 ProfileAgent
                    full_response = profile_agent.render(last_user_prompt, style=selected_style)

                elif intent == "RECOMMEND":
                    # 🔥 RecommendAgent
                    full_response = recommend_agent.render(last_user_prompt, tags=extracted_tags, style=selected_style)
                
                elif intent == "AMBIGUOUS":
                    # 🔥 RefinerAgent (不需要流式)
                    full_response = refiner_agent.clarify(last_user_prompt, style=selected_style)
                    response_placeholder.markdown(full_response)

                else: # CHAT 模式
                    # 🔥 LLMService (流式聊天)
                    # 取最近 8 条对话作为上下文 (排除当前正在处理的这条 User 消息以免重复)
                    context_msgs = st.session_state.messages[-9:-1] 
                    stream = llm_service.get_streaming_response(
                        last_user_prompt, 
                        context_msgs, 
                        memory_data
                    )
                    
                    for chunk in stream:
                        if chunk.choices[0].delta.content:
                            content = chunk.choices[0].delta.content
                            full_response += content
                            response_placeholder.markdown(full_response + "▌")
                    response_placeholder.markdown(full_response)

            # --- Phase C: 存入历史 ---
            # 只有当产生了有效回复时，才追加到 session_state
            if full_response:
                st.session_state.messages.append({"role": "assistant", "content": full_response})

        except Exception as e:
            st.error(f"系统错误: {e}")
            import traceback
            traceback.print_exc()
            st.session_state.messages.append({"role": "assistant", "content": "抱歉，系统处理中断。"})