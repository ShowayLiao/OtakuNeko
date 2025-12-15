import streamlit as st
import os
import json
import re
import threading
import time
from dotenv import load_dotenv

# --- 引入自定义模块 ---
from src.services import DataService, LLMService
from src.scheduler import generate_schedule_ui
from src.bgm_sync import get_missing_stats, patch_one_item
from src.data_processor import export_categorized_datasets, extract_recent_watched
from src.agent import IntentRouter, ProfileAgent, RecommendAgent
from src.vector_store import vector_store

# 🟢 导入插件系统
from src.plugins.year_report import YearReportPlugin 

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
</style>
""", unsafe_allow_html=True)

# 🟢 必须最先初始化 Session State
if "messages" not in st.session_state:
    st.session_state.messages = []

# --- 2. 服务与 Agent 初始化 ---
api_key = os.getenv("DEEPSEEK_API_KEY")
if not api_key:
    st.error("❌ 缺少 API Key配置，请检查 .env 文件")
    st.stop()

@st.cache_resource
def init_services():
    service = LLMService(api_key=api_key)
    return service

llm_service = init_services()
router = IntentRouter(llm_service.client)
profile_agent = ProfileAgent(llm_service.client)
recommend_agent = RecommendAgent(llm_service.client)

# 🟢 插件注册中心 (即插即用)
# 注意：这里传入 client，由插件内部去实例化它需要的 Agent
active_plugins = [
    YearReportPlugin(llm_service.client) 
]

# --- 3. 后台工作线程管理器 (保持原样) ---
class BackgroundWorker:
    def __init__(self):
        self._running = False
        self._thread = None
        self.last_log = "💤 等待启动..."
        self.total_processed = 0
        self.has_new_data = False 

    def start(self):
        if self._running: return
        self._running = True
        print("🚀 [System] 后台线程启动指令已发送...")
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=1.0) 
            self._thread = None
        print("🛑 [System] 后台线程已停止。")
        self.last_log = "⏸️ 已暂停后台任务。"

    def _run_loop(self):
        print("🧵 [Thread] 线程主循环开始运行...")
        self.last_log = "🚀 正在扫描待处理数据..."
        try:
            while self._running:
                _, pending_count, next_id = get_missing_stats()
                if pending_count == 0 or not next_id:
                    msg = "🎉 所有数据已补全！"
                    self.last_log = msg
                    self._running = False
                    break
                
                # print(f"🔍 [Thread] 正在处理 ID: {next_id} ...")
                success, msg = patch_one_item(next_id)
                self.last_log = msg
                
                if success:
                    self.total_processed += 1
                    self.has_new_data = True
                
                for _ in range(15): 
                    if not self._running: break
                    time.sleep(0.1)
        except Exception as e:
            err_msg = f"❌ 线程崩溃: {e}"
            print(err_msg)
            self.last_log = err_msg
            self._running = False

@st.cache_resource
def get_worker():
    return BackgroundWorker()

worker = get_worker()

@st.cache_data(ttl=3600)
def get_cached_memory():
    # 假设 DataService 有这个方法，如果没有请替换为你实际的加载逻辑
    # 这里为了兼容你的代码，暂时注释掉 DataService 的调用，改为直接读取文件或你的逻辑
    # return DataService.load_and_filter_memory()
    # 临时修复：
    return [] 

# --- 4. 界面渲染 ---

# 4.1 侧边栏 (保持原样)
with st.sidebar:
    st.title("🛠️ Neko 控制台")
    
    st.header("📡 数据同步", help="这里是拉取bungumi你的所有动画收藏")
    if st.button("🔄 一键全量更新"):
        with st.status("🚀 正在执行全量更新流程...", expanded=True) as status:
            status.write("1️⃣ 正在拉取 Bangumi 收藏列表...")
            DataService.perform_sync()
            status.write("2️⃣ 正在生成分类数据集...")
            export_categorized_datasets()
            status.write("3️⃣ 正在提取近两年观看记录...")
            extract_recent_watched()
            status.update(label="✅ 全量更新完成", state="complete", expanded=False)
        get_cached_memory.clear()
        st.success("所有数据已更新完毕！")

    with st.expander("🔧 单项手动修复", expanded=False):
        if st.button("📅 仅重生成近期记录"):
            msg = extract_recent_watched()
            st.caption(f"✅ {msg}")
        if st.button("📦 仅重新分类数据集"):
            msg = export_categorized_datasets()
            st.caption(f"✅ {msg}")

    st.markdown("---")
    st.header("🖼️ 元数据补全")
    total_count, pending_count, _ = get_missing_stats()
    st.caption(f"📚 总库: {total_count} | ⏳ 待补: {pending_count}")

    if st.button("🧩 开始补全 (直到完成)", disabled=(pending_count == 0)):
        with st.status("🚀 正在逐个补全数据...", expanded=True) as status:
            processed_count = 0
            while True:
                _, current_pending, next_id = get_missing_stats()
                if current_pending == 0 or not next_id:
                    status.update(label="✅ 补全任务结束", state="complete")
                    break
                status.write(f"🔍 [{processed_count + 1}] 正在处理 ID: {next_id} ...")
                success, msg = patch_one_item(next_id)
                status.write(f"   └─ {msg}")
                if success: processed_count += 1
                time.sleep(0.2)
            get_cached_memory.clear()
            st.rerun()

    st.markdown("---")
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
    st.header("🧠 向量知识库")
    if st.button("构建/更新向量索引"):
        with st.status("🚀 正在启动向量化引擎...", expanded=True) as status:
            try:
                msg = vector_store.build_index(log_func=lambda m: status.write(m))
                status.update(label="✅ 索引构建成功", state="complete")
                st.toast(msg)
            except Exception as e:
                status.update(label="❌ 构建失败", state="error")
                st.write(f"错误详情: {e}")

# 4.2 主界面逻辑

memory_data = get_cached_memory()

st.title("🐱 OtakuNeko")
st.caption(f"🚀 Agent Mode Active | 📚 记忆库: {len(memory_data)} 部")

# 1. 渲染历史消息
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# =========================================================
# 🟢 插件系统：UI 渲染 (放在历史消息之后，输入框之前)
# =========================================================

# 遍历所有插件，渲染它们的悬浮按钮
# 它们会自动使用 CSS 固定在底部，不占用文档流
for plugin in active_plugins:
    plugin.render_button()

# =========================================================
# 🟢 插件系统：执行逻辑 (优先于对话输入框)
# =========================================================

current_plugin_key = st.session_state.get('active_plugin')

if current_plugin_key:
    # 找到对应的插件实例
    target_plugin = next((p for p in active_plugins if p.key == current_plugin_key), None)
    
    if target_plugin:
        # 1. 伪造/显示提示语
        prompt_text = f"正在执行：{target_plugin.key}"
        # 如果是年度总结，显示好听点的名字
        if target_plugin.key == "YEAR_REPORT": 
            prompt_text = "生成 2025 年度动画报告"
            
        st.session_state.messages.append({"role": "user", "content": prompt_text})
        with st.chat_message("user"):
            st.markdown(prompt_text)
            
        # 2. 执行插件逻辑
        with st.chat_message("assistant"):
            # 把控制权完全交给插件，插件负责画图、流式输出等
            final_response = target_plugin.execute(st.empty()) 
            
        # 3. 存入历史
        st.session_state.messages.append({"role": "assistant", "content": final_response})
    
    # 执行完后，重置状态
    del st.session_state['active_plugin']
    # 可选：强制刷新 st.rerun()

# =========================================================
# 🟢 底部输入框 (常规对话)
# =========================================================

if prompt := st.chat_input("输入'生成我的画像'，或'推荐几部番'..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        full_response = ""

        with st.status("🧠 正在分析意图...", expanded=False) as status:
            intent, extracted_tags = router.classify(prompt)
            status.update(label=f"识别模式: {intent}", state="complete")
            if intent == "RECOMMEND" and extracted_tags:
                st.toast(f"已提取特征: {', '.join(extracted_tags[:3])}...")

        try:
            # === PROFILE 模式 (常规画像) ===
            # 注意：年度总结现在由上面的插件系统接管，这里只处理普通的画像生成
            if intent == "PROFILE":
                generated_img_path = None
                profile_cards_data = None
                
                with st.status("🎨 正在全量分析并绘图...", expanded=True) as status:
                    # 调用 ProfileAgent
                    stream = profile_agent.generate_persona_and_grid(style=selected_style)
                    
                    for chunk in stream:
                        if isinstance(chunk, dict) and chunk.get('type') == 'card_data':
                            profile_cards_data = chunk['data']
                            status.write("✅ 数据准备就绪")
                        elif isinstance(chunk, dict) and chunk.get('type') == 'image':
                            generated_img_path = chunk['path']
                            status.write("✅ 绘图完成")
                        elif isinstance(chunk, str):
                            full_response += chunk
                            response_placeholder.markdown(full_response + "▌")
                    status.update(label="✅ 分析完成", state="complete", expanded=False)

                response_placeholder.markdown(full_response)
                
                # 渲染常规画像卡片
                if profile_cards_data:
                    st.divider()
                    st.caption("📊 二次元成分鉴定 (Interactive)")
                    cols = st.columns(5)
                    for i, item in enumerate(profile_cards_data):
                        with cols[i % 5]:
                            # 链接构建
                            if item.get('id'): link = f"https://bgm.tv/subject/{item['id']}"
                            else: 
                                import urllib.parse
                                link = f"https://bgm.tv/subject_search/{urllib.parse.quote(item['title'])}?cat=2"
                            
                            # 图片
                            img_src = item['image'] if item.get('image') else ""
                            if img_src:
                                img_html = f"<div style='width:100%; height:120px; border-radius:6px; overflow:hidden; background:#f4f6f8;'><img src='{img_src}' style='width:100%; height:100%; object-fit:cover;'></div>"
                            else:
                                img_html = "<div style='width:100%; height:120px; background:#f4f6f8; display:flex; align-items:center; justify-content:center; color:#999; font-size:12px;'>NO IMG</div>"
                            
                            # 卡片 HTML
                            st.markdown(f"""
                            <a href="{link}" target="_blank" style="text-decoration:none; color:inherit; display:block;">
                                <div style="border:1px solid #EBF1F5; border-radius:10px; padding:8px; transition:0.2s; background:white; height:100%; box-shadow: 0 2px 6px rgba(0,0,0,0.03);">
                                    {img_html}
                                    <div style="margin-top:8px; text-align:center;"><span style="background-color:#F0F4F8; color:#5A7C98; padding:2px 8px; border-radius:10px; font-size:10px; font-weight:600;">{item['category']}</span></div>
                                    <div style="font-size:12px; font-weight:bold; text-align:center; line-height:1.4; margin-top:6px; height:34px; overflow:hidden; text-overflow:ellipsis; display:-webkit-box; -webkit-line-clamp:2; -webkit-box-orient:vertical; color:#445566;">{item['title']}</div>
                                </div>
                            </a>""", unsafe_allow_html=True)

                if generated_img_path and os.path.exists(generated_img_path):
                    st.divider()
                    with open(generated_img_path, "rb") as file:
                        st.download_button("💾 下载画像长图", file, "profile.png", "image/png", use_container_width=True)

            # === RECOMMEND 模式 ===
            elif intent == "RECOMMEND":
                with st.status("🕵️ 推荐 Agent 启动中...", expanded=True) as status:
                    def update_status(msg, state="running"): status.update(label=msg, state=state)
                    rec_data = recommend_agent.execute(prompt, update_status, tags=extracted_tags, style=selected_style)
                    status.update(label="✅ 完成", state="complete", expanded=False)
                
                if "error" in rec_data:
                    st.error(rec_data["error"])
                else:
                    st.success(f"🎯 **推荐语：** {rec_data['reason']}")
                    cols = st.columns(3)
                    for i, item in enumerate(rec_data['items']):
                        with cols[i % 3]:
                            with st.container(border=True):
                                c1, c2 = st.columns([1, 1.8])
                                with c1: 
                                    if item['image']: st.image(item['image'], width=100)
                                    else: st.markdown("<div style='height:100px; background:#eee;'></div>", unsafe_allow_html=True)
                                with c2:
                                    bg_c = "#EBF3F9" if item['type']=="填坑" else "#F9EBEB"
                                    txt_c = "#5A7C98" if item['type']=="填坑" else "#985A5A"
                                    st.markdown(f"<div style='margin-bottom:4px;'><span style='background-color:{bg_c}; color:{txt_c}; padding:2px 6px; border-radius:4px; font-size:12px;'>{item['type']}</span> <span style='font-size:12px; font-weight:bold;'>⭐{item['score']}</span></div>", unsafe_allow_html=True)
                                    st.markdown(f"**{item['title']}**")
                                    if item['id']: st.link_button("详情", f"https://bgm.tv/subject/{item['id']}", use_container_width=True)

            # === CHAT 模式 ===
            else:
                stream = llm_service.get_streaming_response(prompt, st.session_state.messages[-8:], memory_data)
                for chunk in stream:
                    content = chunk.choices[0].delta.content
                    if content:
                        full_response += content
                        response_placeholder.markdown(full_response + "▌")
                response_placeholder.markdown(full_response)

        except Exception as e:
            st.error(f"Error: {e}")
            import traceback
            traceback.print_exc()

    st.session_state.messages.append({"role": "assistant", "content": full_response})