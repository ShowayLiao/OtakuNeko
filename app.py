import os
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
import streamlit as st
import time
import signal
from dotenv import load_dotenv

# --- 引入自定义模块 ---
from src.services import DataService, LLMService
from src.data_processor import export_categorized_datasets, extract_recent_watched
from src.agent import IntentRouter, ProfileAgent, RecommendAgent, RefinerAgent
from src.vector_store import vector_store
from src.plugins.year_report import YearReportPlugin
from src.BgmServe import BangumiService
import shutil


def install_custom_font():
    """
    将项目内的字体文件安装到 Linux 系统的用户字体目录
    """
    # 1. 配置路径
    # 你的字体文件在项目里的路径 (请确保文件名完全一致)
    font_source = "./font/AlibabaPuHuiTi-3-65-Medium.ttf" 
    
    # Linux 用户级字体目录 (Streamlit Cloud 允许写这里)
    font_dir = os.path.expanduser("~/.fonts")
    
    # 目标路径
    font_dest = os.path.join(font_dir, "AlibabaPuHuiTi-3-65-Medium.ttf")

    # 2. 如果已经安装过，就跳过 (避免每次运行都复制)
    if os.path.exists(font_dest):
        return

    print(f"🔧 [Font] 正在安装字体: {font_source} ...")
    
    try:
        # 创建目录
        os.makedirs(font_dir, exist_ok=True)
        
        # 复制文件
        shutil.copy(font_source, font_dest)
        
        # 3. 核心步骤：刷新 Linux 字体缓存
        # 这一步非常关键，不执行的话系统不知道有新字体
        os.system("fc-cache -fv")
        
        print("✅ [Font] 字体安装成功，缓存已刷新！")
        
    except Exception as e:
        print(f"❌ [Font] 字体安装失败: {e}")

install_custom_font()

# --- 1. 基础配置 & 全局 CSS ---
st.set_page_config(page_title="OtakuNeko", page_icon="🐱", layout="wide")
load_dotenv()

# 确保核心数据目录存在
if not os.path.exists("data"):
    os.makedirs("data")

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

# --- 辅助函数：安全更新 .env 文件 ---

# ---------------------------------------------------------
# 🛠️ 辅助函数：更新 .env 文件
# ---------------------------------------------------------
def update_env_file(key, value):
    """简单的 .env 文件更新逻辑"""
    env_path = ".env"
    # 读取现有内容
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    else:
        lines = []

    # 更新或添加
    key_exists = False
    new_lines = []
    for line in lines:
        if line.strip().startswith(f"{key}="):
            new_lines.append(f"{key}={value}\n")
            key_exists = True
        else:
            new_lines.append(line)
    
    if not key_exists:
        new_lines.append(f"{key}={value}\n")

    # 写入
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(new_lines)

# ---------------------------------------------------------
# 🎨 核心组件：合并后的登录与配置向导
# ---------------------------------------------------------
@st.dialog("👋 欢迎来到 OtakuNeko", width="large")
def initial_setup_dialog():
    st.markdown("请配置您的身份信息与 AI 服务以初始化系统。")
    st.warning("⚠️ 注意：Web 模式下，刷新页面会导致配置丢失，请妥善保存您的 Key。", icon="🔒")
    
    # 使用标签页
    tab_account, tab_ai = st.tabs(["👤 账号绑定 (必填)", "🧠 AI 模型配置"])

    # === Tab 1: Bangumi 账号 ===
    with tab_account:
        st.info("我们需要您的 Bangumi ID 来同步收藏数据。", icon="ℹ️")
        col_u1, col_u2 = st.columns([2, 1])
        with col_u1:
            # ❌ 绝对不要读环境变量来预填！让用户每次都自己填
            input_user = st.text_input("Bangumi ID", value="", placeholder="例如: 123456", help="请填写个人主页 URL 末尾的 ID")
        with col_u2:
            input_token = st.text_input("Access Token (可选)", value="", type="password")

    # === Tab 2: AI 模型 ===
    with tab_ai:
        provider_mode = st.radio("选择 AI 服务商", ["DeepSeek", "自定义"], horizontal=True)
        
        # 初始化变量
        input_ds_key = ""
        input_custom_url = ""
        input_custom_key = ""
        input_model_chat = ""
        input_model_reasoner = ""

        if provider_mode == "DeepSeek":
            # ❌ 绝对不要 value=os.getenv(...)，必须留空！
            input_ds_key = st.text_input("DeepSeek API Key", value="", type="password", placeholder="sk-...")
            st.caption("您的 Key 仅存储在当前浏览器的临时内存中，不会保存到服务器。")
        else:
            input_custom_url = st.text_input("API Base URL", value="", placeholder="https://api.example.com/v1")
            input_custom_key = st.text_input("API Key", value="", type="password")
            c1, c2 = st.columns(2)
            with c1:
                input_model_chat = st.text_input("对话模型名", value="", placeholder="gpt-4o-mini")
            with c2:
                input_model_reasoner = st.text_input("推理模型名", value="", placeholder="gpt-4o")

    st.markdown("---")
    
    # === 提交按钮 ===
    if st.button("🚀 进入系统", type="primary", use_container_width=True):
        # 1. 基础校验 (逻辑不变)
        errors = []
        if not input_user.strip(): errors.append("❌ Bangumi ID 不能为空")
        
        if provider_mode == "DeepSeek" and not input_ds_key.strip():
            errors.append("❌ 请输入 DeepSeek API Key")
        elif provider_mode != "DeepSeek":
            if not input_custom_url.strip() or not input_custom_key.strip():
                errors.append("❌ 自定义服务的 URL 和 Key 不能为空")
        
        if errors:
            for e in errors: st.error(e)
            return

        # 2. 验证并实例化 Service
        with st.spinner("正在验证账户..."):
            temp_service = BangumiService(username=input_user.strip(), token=input_token.strip())
            
            if not temp_service.username:
                st.error("❌ ID 格式错误！请填入数字 ID 或英文 ID。")
                return
            
            # 3. 🔥 关键修改：只更新 Session，不写文件！
            st.session_state.bgm_service = temp_service
            st.session_state.user_name = temp_service.username
            st.session_state.is_logged_in = True
            
            # 4. 把 Key 存入环境变量（仅限当前进程内存，不写文件）
            # 这样你的 LLMService 读 os.getenv 依然能读到，但只对当前用户有效
            if provider_mode == "DeepSeek":
                os.environ["DEEPSEEK_API_KEY"] = input_ds_key.strip()
                st.session_state.provider = "DeepSeek"
            else:
                os.environ["CUSTOM_API_BASE_URL"] = input_custom_url.strip()
                os.environ["CUSTOM_API_KEY"] = input_custom_key.strip()
                os.environ["CUSTOM_MODEL_CHAT"] = input_model_chat.strip()
                os.environ["CUSTOM_MODEL_REASONER"] = input_model_reasoner.strip()
                st.session_state.provider = "Custom"

            st.success("配置已就绪！")
            time.sleep(0.5)
            st.rerun()

# --- 2. 服务与 Agent 初始化 ---
load_dotenv(override=True) # 强制重载，确保读取最新修改

# --- 智能 Provider 选择 ---

# 1. 检测哪些 provider 有 key
available_providers = []
if os.getenv("DEEPSEEK_API_KEY"):
    available_providers.append("DeepSeek")
if os.getenv("CUSTOM_API_KEY"):
    available_providers.append("Custom")

# 检查是否已登录/配置
if "bgm_service" not in st.session_state or not st.session_state.get("is_logged_in"):
    # 尝试自动登录：如果环境变量里有 ID 且有 Key，可以尝试自动跳过弹窗（可选）
    # 但为了安全性，通常建议首次打开都确认一下，或者直接强制弹窗
    initial_setup_dialog()
    
    # 🛑 核心：如果没有完成登录，停止渲染主界面背景
    st.stop()

# 3. 确定默认选择
# 如果 session 里有，用 session 的；否则用列表里第一个
default_provider_index = 0
if "provider" in st.session_state and st.session_state.provider in available_providers:
    default_provider_index = available_providers.index(st.session_state.provider)

# 动态选择 Provider
with st.sidebar:
    st.header("🤖 AI 提供商")
    selected_provider = st.selectbox(
        "选择语言模型服务:",
        options=available_providers,
        index=default_provider_index,
        label_visibility="collapsed"
    )
    st.session_state.provider = selected_provider # 将选择持久化到 session

# 根据选择确定 API Key, Base URL 和模型名称
if selected_provider == "Custom":
    api_key = os.getenv("CUSTOM_API_KEY")
    base_url = os.getenv("CUSTOM_API_BASE_URL", "https://api.openai.com/v1")
    chat_model = os.getenv("CUSTOM_MODEL_CHAT", "gpt-3.5-turbo")
    reasoner_model = os.getenv("CUSTOM_MODEL_REASONER", "gpt-4-turbo")
else: # 默认为 DeepSeek
    api_key = os.getenv("DEEPSEEK_API_KEY")
    base_url = "https://api.deepseek.com"
    chat_model = "deepseek-chat"
    reasoner_model = "deepseek-reasoner"

@st.cache_resource
def init_services():
    return LLMService(
        api_key=api_key, 
        base_url=base_url, 
        chat_model=chat_model, 
        reasoner_model=reasoner_model
    )

llm_service = init_services()

# 实例化 Agents
router = IntentRouter(llm_service,st.session_state.bgm_service)
profile_agent = ProfileAgent(llm_service,st.session_state.bgm_service)
recommend_agent = RecommendAgent(llm_service,st.session_state.bgm_service)
refiner_agent = RefinerAgent(llm_service,st.session_state.bgm_service)

# 注册插件
active_plugins = [
    YearReportPlugin(llm_service, st.session_state.bgm_service)
]

# 加载聊天所需的记忆数据 (缓存)
@st.cache_data(ttl=300)
def get_cached_memory():
    return DataService.load_and_filter_memory(st.session_state.bgm_service)

memory_data = get_cached_memory()

# --- 3. 侧边栏 (控制台) ---
with st.sidebar:
    st.header("📡 数据同步", help="这里是拉取 Bungumi 你的所有动画收藏")
    if st.button("🔄 一键全量更新"):
        with st.status("🚀 正在执行全量更新流程...", expanded=True) as status:
            status.write("1️⃣ 正在拉取 Bangumi 收藏列表...")
            DataService.perform_sync(st.session_state.bgm_service, deep_sync=False) # 基础同步
            status.write("2️⃣ 正在生成分类数据集...")
            export_categorized_datasets(bgm_service=st.session_state.bgm_service)
            status.write("3️⃣ 正在提取近两年观看记录...")
            extract_recent_watched(bgm_service=st.session_state.bgm_service)
            status.update(label="✅ 全量更新完成", state="complete", expanded=False)
        get_cached_memory.clear()
        DataService.invalidate_cache()  # Also invalidate the internal cache
        from src.data_processor import clear_dataset_cache
        clear_dataset_cache()  # Clear dataset cache
        st.success("所有数据已更新完毕！")

    with st.expander("🔧 高级维护", expanded=False):
        if st.button("📅 仅重生成近期记录"):
            msg = extract_recent_watched(st.session_state.bgm_service,730)
            msg += extract_recent_watched(st.session_state.bgm_service,365)
            st.caption(f"✅ {msg}")
        if st.button("📦 仅重新分类数据集"):
            msg = export_categorized_datasets(bgm_service=st.session_state.bgm_service)
            st.caption(f"✅ {msg}")

    # === 元数据补全 ===
    st.header("🖼️ 元数据补全", help="补充更新动画的 Staff 和声优信息，影响推荐准确度")
    total_count, pending_count, _ = st.session_state.bgm_service.get_missing_stats()
    st.caption(f"📚 总库: {total_count} | ⏳ 待补: {pending_count}")

    if st.button("🧩 开始补全 (直到完成)", disabled=(pending_count == 0)):
        with st.status("🚀 正在逐个补全数据...", expanded=True) as status:
            processed_count = 0
            while True:
                _, current_pending, next_id = st.session_state.bgm_service.get_missing_stats()
                if current_pending == 0 or not next_id:
                    status.update(label="✅ 补全任务结束", state="complete")
                    break
                
                success, msg = st.session_state.bgm_service.patch_one_item(next_id)
                status.write(f"[{processed_count + 1}] {msg}")
                
                if success: processed_count += 1
                time.sleep(0.5) # 防频控
            
        get_cached_memory.clear()
        DataService.invalidate_cache()  # Also invalidate the internal cache
        st.rerun()
    
    # # === 向量库维护 ===
    
    # st.header("🧠 向量知识库", help="管理向量索引，用于提取推荐标签")
    # if st.button("构建/更新索引"):
    #     with st.status("🚀 正在启动向量化引擎...", expanded=True) as status:
    #         try:
    #             msg = vector_store.build_index(log_func=lambda m: status.write(m))
    #             status.update(label="✅ 索引构建成功", state="complete")
    #             st.toast(msg)
    #         except Exception as e:
    #             status.update(label="❌ 构建失败", state="error")
    #             st.error(f"详情: {e}")
    
    st.markdown("---")

    # === 助手设置 ===
    st.header("🎭 助手设置")
    persona_options = {"cat": "🐱 傲娇猫娘", "normal": "🧐 专业评论家", "tender_cat": "🐱 柔情猫娘","maodie": "😼 圆头耄耋"}
    selected_style = st.radio(
        "选择语调风格:",
        options=list(persona_options.keys()),
        format_func=lambda x: persona_options[x],
        index=0,
        label_visibility="collapsed"
    )

    st.markdown("---")

    # === 插件入口 (作为 Trigger) ===
    st.header("🧩 扩展插件")
    
    # 辅助函数：侧边栏按钮点击后的回调
    def trigger_plugin_msg(trigger_text):
        st.session_state.messages.append({"role": "user", "content": trigger_text})
          
    for plugin in active_plugins:
        # 获取按钮显示的文字，优先用 btn_label，没有则用 key
        label = getattr(plugin, 'btn_label', f"📊 {plugin.key}")
        
        # 获取触发文本，优先用 trigger_text
        trigger = getattr(plugin, 'trigger_text', f"执行插件：{plugin.key}")

        if st.button(label, key=f"plugin_btn_{plugin.key}"):
            trigger_plugin_msg(trigger)
            st.rerun()
    
    st.markdown("---")

    # === 关闭 & 修改 Key ===

    
    with st.sidebar:
        col1, col2 = st.columns([3, 1])
        with col1:
            if st.button("❌ 关闭程序"):
                st.toast("正在关闭 OtakuNeko，请关闭浏览器标签页...", icon="👋")
                # 稍微延迟一下，让用户能看到上面的提示
                time.sleep(1)
                # 获取当前程序的进程ID (PID)，然后杀掉自己
                os.kill(os.getpid(), signal.SIGTERM)
        with col2:
            if st.button("✏️", help="修改 API Key"):
                configure_api_key_dialog()

    with st.sidebar:
        st.markdown("---") # 分割线
        


# --- 4. 主界面逻辑 ---

st.title("🐱 OtakuNeko")
st.caption(f"🚀 Agent Mode Active | 📚 记忆库: {len(memory_data)} 部待看")

# 4.1 渲染历史消息
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 4.2 处理底部输入框
# ⚠️ 注意：这里只负责接收输入并追加到历史，不负责处理。处理逻辑在下面统一进行。
if user_input := st.chat_input("输入'鉴别成分'，或'推荐几部番'..."):
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
            # --- Phase A: 插件触发词检测 (通用化重构) ---
            matched_plugin = None
            
            for plugin in active_plugins:
                # 1. 获取插件定义的触发词 (如果没有定义，默认用 None 跳过)
                # 兼容性处理：优先用 trigger_text，其次尝试匹配 key
                trigger = getattr(plugin, 'trigger_text', None)
                
                # 2. 匹配逻辑
                # 这里使用 "in" 包含匹配，允许用户输入 "请帮我生成年度动画报告" 也能触发
                # 如果想要更严格，可以用 last_user_prompt.strip() == trigger
                if trigger and trigger in last_user_prompt:
                    matched_plugin = plugin
                    break  # 找到一个匹配的插件就停止，避免冲突
            
            if matched_plugin:
                # 🚀 执行插件逻辑
                # 获取插件名称用于显示，如果没有 label 就用 key
                plugin_name = getattr(matched_plugin, 'btn_label', matched_plugin.key)
                
                with st.status(f"🧩 正在启动插件 [{plugin_name}]...", expanded=True) as status:
                    # 插件内部自行处理 UI 渲染，并返回最终 Markdown 结果
                    # 传入 status 容器，允许插件内部更新 "正在抓取..." 这种状态
                    full_response = matched_plugin.execute(response_placeholder,style = selected_style)
                    
                    status.update(label=f"✅ {plugin_name} 执行完成", state="complete", expanded=False)

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