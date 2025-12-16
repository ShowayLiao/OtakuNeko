import streamlit as st
import os
import threading
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
    # st.title("🛠️ Neko 控制台")
    
    # === A. 数据同步 ===
    st.header("📡 数据同步",help="这里是拉取bungumi你的所有动画收藏")
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

    # st.markdown("---")

    # === B. 元数据补全 ===
    st.header("🖼️ 元数据补全",help="由于耗时，这里是补充更新动画的staff和声优信息，不进行也可以进行后续的，只是会影响推荐准确度")
    
    # 🟢 修改点 1: 使用 bgm_service 调用方法
    total_count, pending_count, _ = bgm_service.get_missing_stats()
    
    st.caption(f"📚 总库: {total_count} | ⏳ 待补: {pending_count}")

    if st.button("🧩 开始补全 (直到完成)", disabled=(pending_count == 0)):
        with st.status("🚀 正在逐个补全数据...", expanded=True) as status:
            processed_count = 0
            while True:
                # 🟢 修改点 2: 使用 bgm_service 调用方法
                _, current_pending, next_id = bgm_service.get_missing_stats()
                
                if current_pending == 0 or not next_id:
                    status.update(label="✅ 补全任务结束", state="complete")
                    break
                
                # 🟢 修改点 3: 使用 bgm_service 调用方法
                success, msg = bgm_service.patch_one_item(next_id)
                status.write(f"[{processed_count + 1}] {msg}")
                
                if success: processed_count += 1
                time.sleep(0.5) # 稍微防一下频控
            
            get_cached_memory.clear()
            st.rerun()

    st.markdown("---")

    # === C. 助手设置 ===
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

    # === D. 向量库维护 ===
    st.header("🧠 向量知识库",help="这里是管理和维护向量知识库的功能,用于增强检索，如果不进行也可以")
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
    
    # === E. 插件入口 ===
    st.header("🧩 扩展插件")
    # 渲染插件按钮 (YearReportPlugin 会把自己渲染在这里)
    for plugin in active_plugins:
        plugin.render_button()


# --- 4. 主界面逻辑 ---

st.title("🐱 OtakuNeko")
st.caption(f"🚀 Agent Mode Active | 📚 记忆库: {len(memory_data)} 部待看")

# 4.1 渲染历史消息
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
# TODO:插件的实现逻辑有问题，导致无法正确渲染历史消息，暂时注释掉
# 4.2 插件执行逻辑 (优先处理)
current_plugin_key = st.session_state.get('active_plugin')

if current_plugin_key:
    target_plugin = next((p for p in active_plugins if p.key == current_plugin_key), None)
    
    if target_plugin:
        # 1. 伪造用户输入
        prompt_text = f"正在执行：{target_plugin.key}"
        if target_plugin.key == "YEAR_REPORT": 
            prompt_text = "✨ 生成 2025 年度动画报告"
            
        st.session_state.messages.append({"role": "user", "content": prompt_text})
        with st.chat_message("user"):
            st.markdown(prompt_text)
            
        # 2. 执行插件 (UI渲染在插件内部完成)
        with st.chat_message("assistant"):
            response_placeholder = st.empty()
            # 🔥 核心：一句代码调用，所有脏活都在 Agent/Plugin 里
            final_response = target_plugin.execute(response_placeholder)
            
            st.session_state.messages.append({"role": "assistant", "content": final_response})
    
    del st.session_state['active_plugin']
    st.rerun()

# 4.3 底部输入框 & 意图路由
if prompt := st.chat_input("输入'生成我的画像'，或'推荐几部番'..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        # 1. 路由分析
        with st.status("🧠 正在分析意图...", expanded=False) as status:
            intent, extracted_tags = router.classify(prompt)
            status.update(label=f"识别模式: {intent}", state="complete")
            if intent == "RECOMMEND" and extracted_tags:
                st.toast(f"已提取特征: {', '.join(extracted_tags[:3])}...")

        try:
            full_response = ""

            # === 分发任务给对应的 Agent ===
            
            if intent == "PROFILE":
                # 🔥 ProfileAgent 接管
                full_response = profile_agent.render(prompt, style=selected_style)

            elif intent == "RECOMMEND":
                # 🔥 RecommendAgent 接管
                full_response = recommend_agent.render(prompt, tags=extracted_tags, style=selected_style)
            
            elif intent == "AMBIGUOUS":
                # 🔥 RefinerAgent 接管
                full_response = refiner_agent.clarify(prompt, style=selected_style)
                
                # 直接显示回复 (因为 Refiner 是短回复，不需要流式)
                response_placeholder = st.empty()
                response_placeholder.markdown(full_response)

            else: # CHAT 模式
                # 🔥 LLMService 接管 (保持记忆聊天的能力)
                # 使用 services.py 里配置好的 chat_system Prompt
                stream = llm_service.get_streaming_response(prompt, st.session_state.messages[-8:], memory_data)
                
                response_placeholder = st.empty()
                for chunk in stream:
                    if chunk.choices[0].delta.content:
                        content = chunk.choices[0].delta.content
                        full_response += content
                        response_placeholder.markdown(full_response + "▌")
                response_placeholder.markdown(full_response)

        except Exception as e:
            st.error(f"系统错误: {e}")
            import traceback
            traceback.print_exc()
            full_response = "抱歉，由于系统内部错误，处理中断。"

    # 存入历史
    st.session_state.messages.append({"role": "assistant", "content": full_response})