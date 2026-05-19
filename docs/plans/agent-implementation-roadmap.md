# OtakuNeko 开发实施路线图

> **用途**：Agent 可读、可执行的任务清单。每个任务包含：目标文件、改动内容、验收方式、依赖关系。
> **基准**：`docs/interview-assessment-report.md` + `docs/business-driven-improvement-plan.md`
> **总任务数**：17（分 4 个 Phase）
> **环境**：Windows + Python 3.12 + uv 包管理器

---

## 全局前置约定

### 项目根路径
```
e:\HACCI\Documents\tools\OtakuNeko
```

### 后端代码根路径
```
e:\HACCI\Documents\tools\OtakuNeko\backend\app
```

### 依赖管理
- 所有新依赖用 `uv add <package>` 添加到 `backend/pyproject.toml`
- 不要在 `backend/requirements.txt` 中手动编辑
- 安装依赖：`cd backend && uv sync`

### 验证方式
- 所有代码变更后运行：`cd backend && uv run pytest tests/ -x -v`（如果 tests 目录已存在）
- Phase 1-2 期间，用 type check 验证：`cd backend && uv run pyright app/`
- **禁止在沙箱中运行**，所有命令由用户在本地终端执行

---

# Phase 1：保命级（Tier 1，1-2 周）

> **目标**：修复致命安全问题，引入 RAG 和 Agent Memory，奠定 Agent 工程基础。
> **依赖链**：`安全修复 → Graph 复用 → Agent Memory → RAG 基础`（安全修复和清理调试代码可并行，其余串行）

---

## 任务 P1-01：安全修复 — JWT 密钥与环境变量

**关联评估项**：T1-#4（安全修复）
**优先级**：🔴 P0（最高）
**预估耗时**：30 分钟
**依赖**：无

### 现状问题
`backend/app/core/security.py:9` — JWT SECRET_KEY 硬编码 fallback：
```python
SECRET_KEY = settings.OPENAI_API_KEY or "your-secret-key-change-this-in-production"
```

### 执行步骤

#### 1.1 修改 `backend/app/core/config.py`

在 `Settings` 类中新增字段，位置插在 `DEBUG` 和 `OPENAI_API_KEY` 之间：

```python
# 新增：JWT 安全配置
JWT_SECRET_KEY: str = ""  # 生产环境必须设置，无默认值
CORS_ORIGINS: str = "http://localhost:3000,http://localhost:3001,http://localhost:3002,http://localhost:3003"
```

#### 1.2 修改 `backend/app/core/security.py`

**删除第 9 行**（原 `SECRET_KEY = settings.OPENAI_API_KEY or ...`），替换为：

```python
SECRET_KEY = settings.JWT_SECRET_KEY
if not SECRET_KEY:
    raise ValueError(
        "JWT_SECRET_KEY is not set. "
        "Set it via environment variable or .env file. "
        "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
    )
```

同时将 `decode_access_token` 函数中的 `logging.info("[DEBUG] ...")` 改为 `logging.debug(...)`。

#### 1.3 修改 `backend/.env.example`

新增以下行（插在 `OPENAI_API_KEY` 之后）：

```
# JWT 安全密钥（生产环境必须设置，生成方式：python -c "import secrets; print(secrets.token_urlsafe(32))"）
JWT_SECRET_KEY=dev-jwt-secret-change-in-production
```

#### 1.4 修改 `backend/app/main.py`

第 99-103 行的 CORS 配置，将硬编码的 `allow_origins` 改为从配置读取：

**当前**：
```python
allow_origins=["http://localhost:3000", "http://localhost:3001", "http://localhost:3002", "http://localhost:3003"],
```

**改为**：
```python
allow_origins=[origin.strip() for origin in settings.CORS_ORIGINS.split(",") if origin.strip()],
```

### 验收方式
1. 在 `backend/.env` 中确保有 `JWT_SECRET_KEY=...` 一行
2. 启动服务 `uv run uvicorn app.main:app --reload`
3. 服务应正常启动，无 `ValueError`
4. 调用任意需要 JWT 的 API（如 `/api/v1/users/me`），确认认证仍正常工作

---

## 任务 P1-02：清理调试代码

**关联评估项**：T1-#5（清理调试代码）
**优先级**：🔴 P0
**预估耗时**：15 分钟
**依赖**：无（可与 P1-01 并行）

### 需要修改的文件和位置

#### 2.1 `backend/app/api/deps.py`

| 行号 | 当前代码 | 改为 |
|------|---------|------|
| L44 | `print("[DEBUG] decode_access_token returned None")` | `logger.debug("decode_access_token returned None")` |
| L47 | `print(f"[DEBUG] JWT payload: {payload}")` | `logger.debug(f"JWT payload: {payload}")` |
| L51 | `print("[DEBUG] payload.get('sub') returned None")` | `logger.debug("payload.get('sub') returned None")` |
| L53 | `print(f"[DEBUG] user_id_str: {user_id_str}, type: {type(user_id_str)}")` | `logger.debug(f"user_id_str: {user_id_str}")` |
| L58 | `print(f"[DEBUG] user_id after conversion: {user_id}, type: {type(user_id)}")` | `logger.debug(f"user_id after conversion: {user_id}")` |
| L60 | `print(f"[DEBUG] ValueError when converting user_id_str to int: {e}")` | `logger.debug(f"ValueError converting user_id_str: {e}")` |

**额外**：在 `deps.py` 文件顶部（import 区之后）添加：
```python
from app.core.logging import get_logger
logger = get_logger(__name__)
```

#### 2.2 `backend/app/api/v1/dashboard.py`

第 35~36 行：
```python
# 当前
print(f"[获取用户统计数据] 错误: {str(e)}")
print(traceback.format_exc())

# 改为
logger.error(f"Failed to get user stats: {e}", exc_info=True)
```

同时将 `import traceback` 删除，新增：
```python
from app.core.logging import get_logger
logger = get_logger(__name__)
```

### 验收方式
1. `cd backend && grep -r "print(" app/` 应返回 0 结果（或仅有非调试用途的 print）
2. 代码中不再出现 `print("[DEBUG]`

---

## 任务 P1-03：Graph 编译复用 ✅ 已完成 (2026-05-12)

**关联评估项**：T1-#2（Graph 复用）
**优先级**：🔴 P0
**预估耗时**：30 分钟
**依赖**：P1-01

### 现状问题
`backend/app/agents/graph.py` — `ChatWorkflow.stream_chat()` 方法每次请求都调用 `workflow.compile()`，导致不必要的 CPU 开销。

### 执行步骤

#### 3.1 重写 `backend/app/agents/graph.py`

**核心思路**：将 tools 列表、call_model 节点、workflow 编译全部移到 `__init__` 中，`stream_chat` 只管执行。

新 `graph.py` 实现要点：
- `__init__` 中：初始化 `self.llm`（使用 `ChatOpenAI`），绑定 tools，构建 StateGraph，调用 `self.app = workflow.compile()` 一次
- `stream_chat` 中：直接调用 `self.app.astream_events(...)` 流式执行（不再有 llm 初始化、tool 绑定、graph 构建、compile）
- 保留原有的三种 SSE 事件类型（`message_chunk`、`tool_start`、`tool_end`）
- 保留 `on_chat_model_stream` 中过滤空 content 和 tool_call token 的逻辑
- 保留 `on_tool_end` 中 Message 序列化的兜底逻辑

#### 3.2 同步修改 `backend/app/api/v1/agent.py`

第 49 行 `workflow = ChatWorkflow(api_key=api_key, base_url=base_url)` 由于 graph 已预编译，这个实例可以复用了——但目前每次请求的 `ChatWorkflow` 带有不同用户的 API key，所以每次创建仍然合理。不需要改 agent.py 的调用方式。

### 验收方式
1. 启动服务，发送 Agent 聊天请求，确认 SSE 流式输出正常
2. 确认 tool_start / tool_end 事件仍然正常发送
3. 日志中不应出现 graph 编译相关报错

---

## 任务 P1-04：Agent Memory — Checkpoint 持久化 ✅ 已完成 (2026-05-12)

**关联评估项**：T1-#1（Agent Memory）
**优先级**：🔴 P0
**预估耗时**：1 小时
**依赖**：P1-03（依赖 graph 编译到 __init__ 的结构）

### 目标
引入 LangGraph 的 `SqliteSaver`（从 `langgraph.checkpoint.sqlite` 导入），使 Agent 具备：
1. 对话状态跨请求持久化
2. 断点恢复能力
3. 对话摘要压缩（Summary Node）

### 执行步骤

#### 4.1 修改 `backend/app/agents/graph.py`

在 `__init__` 中：
- 初始化 `self.checkpointer = SqliteSaver.from_conn_string("checkpoints.db")`
- 在 `workflow.compile(checkpointer=self.checkpointer)` 时传入 checkpointer

在 `stream_chat` 中：
- 方法签名新增 `thread_id: str` 参数（用于区分不同对话线程）
- `astream_events` 调用时传入 `config={"configurable": {"thread_id": thread_id}}`

#### 4.2 修改 `backend/app/api/v1/agent.py`

在 `stream_generator` 中：
- 生成或接收 `thread_id`（可从 ChatRequest schema 新增字段，或在前端用 UUID 生成后传入）
- 调用 `workflow.stream_chat(..., thread_id=thread_id)` 时传入 thread_id

#### 4.3 修改 `backend/app/schemas/agent.py`

`ChatRequest` 类新增字段：
```python
thread_id: Optional[str] = None  # 对话线程 ID，用于持久化对话状态
```

#### 4.4 新增依赖
```bash
cd backend && uv add langgraph-checkpoint-sqlite
```

### 验收方式
1. 同一 thread_id 的两次请求，Agent 应"记得"上一轮的对话内容
2. 重启服务后，同一 thread_id 的对话状态不丢失（checkpoint.db 文件持久化）
3. `backend/checkpoints.db` 文件存在且不为空

> **📌 2026-05-18 更新**：P1-04 已通过合并 `pr-test-branch` 的 `memory/` 模块完成最终方案。改为三层架构：`InMemorySaver`（LangGraph 状态流转）+ `ShortTermMemory`（JSON 持久化）+ `LongTermMemory`（LLM 提炼 + BM25/Vector 检索）。详见 [logs/2026-05-18-log.md](file:///e:/HACCI/Documents/tools/OtakuNeko/logs/2026-05-18-log.md)。

---

## 任务 P1-05：向量数据库 + RAG 基础

**关联评估项**：T1-#3（RAG）
**优先级**：🔴 P0
**预估耗时**：2 小时
**依赖**：P1-01（需要 API Key 调用 embedding）

### 目标
构建动漫条目的语义索引，新增 `semantic_search_anime` tool，实现语义级别的动漫发现。

### 执行步骤

#### 5.1 新增依赖
```bash
cd backend && uv add chromadb openai
```

#### 5.2 新增 `backend/app/services/embedding_service.py`

```python
"""Embedding 调用封装"""
from openai import AsyncOpenAI
from app.core.config import settings

async def get_embedding(texts: list[str], model: str = "text-embedding-3-small") -> list[list[float]]:
    """批量获取文本的 embedding 向量"""
    client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    response = await client.embeddings.create(model=model, input=texts)
    return [item.embedding for item in response.data]
```

#### 5.3 新增 `backend/app/services/vector_service.py`

- `build_anime_index(db: AsyncSession)` — 从 Subject 表读取所有动漫条目，构建 `(name + name_cn + summary)` 的文本，调用 embedding，存入 ChromaDB（collection 名：`anime_subjects`）
- `search_similar_anime(query: str, top_k: int = 10)` — 对用户 query 做 embedding，在 ChromaDB 中做余弦相似度检索
- 增量更新函数（后续 Celery 定时调用）：`incremental_update(db)` — 只对新/变更的 Subject 做 embedding

ChromaDB 使用 **persistent client** 模式，数据目录 `backend/chroma_data/`。

#### 5.4 新增 `backend/app/agents/tools.py` 中的 tool

新增 `semantic_search_anime` tool：

```python
@tool
async def semantic_search_anime(query: str, top_k: int = 5) -> dict:
    """
    Semantic search for anime using natural language descriptions.
    
    Use this tool when the user describes what kind of anime they want 
    in natural language (e.g. "healing slice-of-life anime like Yuru Camp").
    Returns anime entries ranked by semantic similarity to the query.
    
    Args:
        query: Natural language description of the desired anime
        top_k: Number of results to return (default 5)
    
    Returns:
        List of matching anime with similarity scores
    """
    ...
```

#### 5.5 在 `backend/app/agents/graph.py` 的 tools 列表中添加 `semantic_search_anime`

### 索引构建
首次使用需要手动运行一次索引构建（后续由 Celery 定时执行）：
```bash
cd backend && uv run python -c "
import asyncio
from app.db.database import AsyncSessionLocal
from app.services.vector_service import build_anime_index

async def build():
    async with AsyncSessionLocal() as db:
        await build_anime_index(db)

asyncio.run(build())
"
```

### 验收方式
1. 索引构建脚本运行成功（`chroma_data/` 目录生成）
2. 发送 Agent 聊天请求如"推荐治愈系日常动画"，Agent 应调用 `semantic_search_anime` tool
3. 返回的动漫列表应与语义相关（而非仅关键词匹配）

---

# Phase 2：竞争力级（Tier 2，2-4 周）

> **目标**：Agent 架构从 ReAct 升级到 Plan+Execute，补齐可观测性和异步任务系统。
> **依赖链**：在 Phase 1 全部完成的基础上进行。

---

## 任务 P2-06：Agent 架构升级 — Plan-and-Execute

**关联评估项**：T2-#6（Plan+Execute）
**优先级**：🟡 P1
**预估耗时**：4 小时
**依赖**：P1-04（需要 checkpoint 保存中间状态）

### 目标
将单层 ReAct 循环升级为 Plan-and-Execute 架构：
```
START → Router → [单作品/多作品] → Planner → Executor(Loop) → Critic → END
```

### 执行步骤

#### 6.1 新增 `backend/app/agents/nodes/router_node.py`

路由器节点负责识别用户意图，输出分类标签：
- `deep_analysis`：单作品深度分析
- `comparison`：多作品对比分析
- `general_chat`：普通闲聊/简单查询（fallback 到旧的 ReAct）

使用 LLM 做分类，prompt 模板包含意图分类的定义和示例。

#### 6.2 新增 `backend/app/agents/nodes/planner_node.py`

规划器节点将用户需求拆解为子任务列表。输出格式（写入 state）：
```python
{"plan": [
    {"step_id": 1, "description": "获取基本信息", "tool": "get_anime_info", "args": {...}},
    {"step_id": 2, "description": "获取制作团队", "tool": "get_anime_staff", "args": {...}},
    ...
]}
```

#### 6.3 新增 `backend/app/agents/nodes/critic_node.py`

审核节点在最终输出前做自我审查：
- 检查是否覆盖了所有计划步骤
- 检查结论是否有数据支撑
- 补充遗漏点

#### 6.4 定义 AgentState（替代 MessagesState）

新建 `backend/app/schemas/agent_state.py`：
```python
from typing import TypedDict, List, Annotated
from langgraph.graph.message import add_messages

class AgentState(TypedDict):
    messages: Annotated[list, add_messages]
    intent: str                        # router 输出
    plan: list[dict]                   # planner 输出
    completed_steps: int               # executor 进度
    critic_feedback: str               # critic 反馈
```

#### 6.5 重写 `backend/app/agents/graph.py`

编译多节点条件图：
- `router_node` 输出 → 条件边分流到不同的 planner 或通用 ReAct
- `planner_node` 输出 → `executor_node`
- `executor_node` 循环执行直到所有步骤完成
- `critic_node` 审核 → 条件边决定是否重新执行某个步骤
- 所有节点共享 `AgentState`

保留原有的 SSE 事件流（`message_chunk`, `tool_start`, `tool_end`），在 `executor` 执行期间继续输出。

### 验收方式
1. 发送请求"深度分析《钢之炼金术师FA》"，Router 应识别为 `deep_analysis`
2. Planner 应生成 4+ 步骤的计划
3. Executor 应逐步执行每个步骤
4. Critic 应输出审核结论
5. 流式输出中间结果（渐进式报告）

---

## 任务 P2-07：Tool 调用重试与降级

**关联评估项**：T2-#9（Tool 重试/降级）
**优先级**：🟡 P1
**预估耗时**：1 小时
**依赖**：无（可独立于其他 P2 任务实现）

### 目标
为所有 Agent Tool 添加自动重试（3 次指数退避）和备选数据源降级。

### 执行步骤

#### 7.1 新增 `backend/app/core/retry.py`

```python
"""通用重试与降级工具"""
from functools import wraps
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
import httpx
from app.core.logging import get_logger

logger = get_logger(__name__)

def with_retry(max_attempts: int = 3):
    """指数退避重试装饰器，仅对 HTTP 5xx 和网络超时重试"""
    return retry(
        stop=stop_after_attempt(max_attempts),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TimeoutException)),
        before_sleep=lambda retry_state: logger.warning(
            f"Retry {retry_state.attempt_number}/{max_attempts} "
            f"after error: {retry_state.outcome.exception()}"
        ),
    )
```

#### 7.2 修改 `backend/app/agents/tools.py`

为每个调用 Bangumi API 的 tool 添加 `@with_retry()` 装饰器。方式：在 `search_subjects_advanced` 和 `fetch_subject_detail` 等 Bangumi client 方法上添加 `@with_retry()`。

**降级链**（在 `search_anime_advanced` tool 中实现）：
```
Bangumi API (3 retries) → 本地 SQLite 关键词搜索 → 返回热门推荐列表
```

#### 7.3 新增依赖
```bash
cd backend && uv add tenacity
```

### 验收方式
1. 通过修改 hosts 文件或环境变量模拟 Bangumi API 不可达
2. 发送 Agent 请求，日志中应出现 "Retry 1/3 after error" 等重试日志
3. 重试 3 次失败后，应自动降级到本地数据源，不中断对话

---

## 任务 P2-08：Celery 异步任务系统

**关联评估项**：T2-#8（Celery 异步）
**优先级**：🟡 P1
**预估耗时**：3 小时
**依赖**：P1-01（需要 Redis 连接）

### 目标
将阻塞式同步改为 Celery 异步任务，实现三个核心定时任务。

### 执行步骤

#### 8.1 实现 `backend/app/worker/celery_app.py`

以下功能从 `# TODO` 占位变为可运行代码：

```python
from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "otakuneko",
    broker=settings.REDIS_URL or "redis://localhost:6379/0",
    backend=settings.REDIS_URL or "redis://localhost:6379/0",
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "sync-bangumi-calendar-weekly": {
            "task": "app.worker.tasks.sync_calendar",
            "schedule": 604800.0,  # 每周
        },
        "sync-user-collections-daily": {
            "task": "app.worker.tasks.sync_user_collections",
            "schedule": 86400.0,  # 每天
        },
        "rebuild-anime-index-daily": {
            "task": "app.worker.tasks.rebuild_anime_index",
            "schedule": 43200.0,  # 每 12 小时
        },
        "precompute-user-profiles-hourly": {
            "task": "app.worker.tasks.precompute_profiles",
            "schedule": 3600.0,  # 每小时
        },
    },
)
```

#### 8.2 新增 `backend/app/worker/tasks.py`

定义四个 Celery 任务函数：
- `sync_calendar()` — 调用 `bangumi_data_sync.py` 的同步逻辑
- `sync_user_collections()` — 批量增量同步所有用户的 Bangumi 收藏
- `rebuild_anime_index()` — 调用 `vector_service.py` 的增量索引构建
- `precompute_profiles()` — 为活跃用户预计算画像并缓存

每个任务函数都是 celery_app 的 `@celery_app.task` 装饰的函数，内部调用已有的 service 层逻辑。

#### 8.3 更新 `docker-compose.yml`

新增 Celery Worker 和 Celery Beat 服务定义：
```yaml
celery_worker:
  build: ./backend
  command: celery -A app.worker.celery_app worker --loglevel=info
  depends_on: [redis, db]
  environment:
    - DEPLOY_MODE=cloud
    - REDIS_URL=redis://redis:6379/0
    ...

celery_beat:
  build: ./backend
  command: celery -A app.worker.celery_app beat --loglevel=info
  depends_on: [redis, db]
  ...
```

### 验收方式
1. `docker-compose up` 后 celery_worker 和 celery_beat 服务正常启动
2. Celery Beat 日志中出现定时任务调度记录
3. 手动触发一个 celery 任务（`docker-compose exec celery_worker celery -A app.worker.celery_app call ...`），确认执行成功

---

## 任务 P2-09：LangFuse 全链路追踪

**关联评估项**：T2-#7（LangFuse Ops）
**优先级**：🟡 P1
**预估耗时**：1.5 小时
**依赖**：P2-06（有复杂链路才有追踪价值，但可提前实现基础集成）

### 执行步骤

#### 9.1 新增依赖
```bash
cd backend && uv add langfuse
```

#### 9.2 修改 `backend/app/core/config.py`

新增：
```python
LANGFUSE_PUBLIC_KEY: Optional[str] = None
LANGFUSE_SECRET_KEY: Optional[str] = None
LANGFUSE_HOST: str = "https://cloud.langfuse.com"
```

#### 9.3 修改 `backend/app/agents/graph.py`

在 `__init__` 中初始化 LangFuse callback handler（如果配置了密钥）：
```python
if settings.LANGFUSE_SECRET_KEY:
    from langfuse.callback import CallbackHandler
    self.langfuse_handler = CallbackHandler(
        secret_key=settings.LANGFUSE_SECRET_KEY,
        public_key=settings.LANGFUSE_PUBLIC_KEY,
        host=settings.LANGFUSE_HOST,
    )
else:
    self.langfuse_handler = None
```

在 `astream_events` 调用时注入 callback：
```python
config = {"configurable": {"thread_id": thread_id}}
if self.langfuse_handler:
    config["callbacks"] = [self.langfuse_handler]
```

### 验收方式
1. 设置 LangFuse 密钥后启动服务
2. 发送 Agent 聊天请求
3. 在 LangFuse Dashboard 中查看 Trace，确认能看到 LLM 调用、tool 调用、token 消耗

---

## 任务 P2-10：Prompt 分层管理

**关联评估项**：T2-#11（Prompt 分层管理）
**优先级**：🟡 P1
**预估耗时**：2 小时
**依赖**：无

### 执行步骤

#### 10.1 新增 `backend/app/agents/prompts/` 目录及文件

```
backend/app/agents/prompts/
├── __init__.py
├── base.py          # 基础角色设定模板
├── few_shots.py     # Few-shot 示例库
└── manager.py       # Prompt 组装与版本管理
```

#### 10.2 `base.py` — 基础 System Prompt 模板

```python
BASE_SYSTEM_PROMPT = """You are OtakuNeko, an expert anime recommendation and analysis assistant.

Your capabilities:
- Search for anime using semantic understanding and structured filters
- Provide detailed analysis of anime (production, staff, cast, audience reception)
- Generate personalized recommendations based on user preferences
- Compare multiple anime across various dimensions

Guidelines:
1. Always use tools to fetch real data; never fabricate anime information
2. When recommending, explain WHY each anime matches the user's request
3. Cite specific data (ratings, staff, reviews) when making claims
4. Be honest when you don't know something
"""
```

#### 10.3 `few_shots.py` — 示例库

按场景分类的 few-shot 示例（推荐、分析、搜索各 3-5 个），格式为：
```python
FEW_SHOT_EXAMPLES = {
    "recommendation": [
        {"user": "...", "assistant": "...", "tool_calls": [...]},
        ...
    ],
    "analysis": [...],
    "search": [...],
}
```

#### 10.4 `manager.py` — 组装逻辑

```python
class PromptManager:
    def __init__(self, user_id: Optional[int] = None):
        self.user_id = user_id
    
    async def build_system_prompt(self, intent: Optional[str] = None) -> str:
        """组装三层 prompt：Base + Dynamic Context + Few-shot"""
        parts = [BASE_SYSTEM_PROMPT]
        
        # 动态注入用户画像
        if self.user_id:
            profile = await self._get_user_profile_context()
            if profile:
                parts.append(profile)
        
        # 按意图注入 few-shot 示例
        if intent and intent in FEW_SHOT_EXAMPLES:
            parts.append(self._format_few_shots(FEW_SHOT_EXAMPLES[intent]))
        
        return "\n\n".join(parts)
```

#### 10.5 修改 `backend/app/api/v1/agent.py`

将原来的简单字符串拼接改为使用 `PromptManager`：
```python
from app.agents.prompts.manager import PromptManager

pm = PromptManager(user_id=current_user.id if current_user else None)
system_prompt = await pm.build_system_prompt()
```

### 验收方式
1. 发送不同类型的 Agent 请求（推荐、分析），检查 LangFuse trace 中的 system prompt 是否包含对应的 few-shot 示例
2. Tool docstring 已全部改为英文（此任务也会涉及部分 tools.py 的修改）

---

## 任务 P2-11：测试体系

**关联评估项**：T2-#10（测试体系）
**优先级**：🟡 P1
**预估耗时**：3 小时
**依赖**：P1-01 ~ P1-05（各模块重构完成后补充）

### 执行步骤

#### 11.1 创建测试目录结构

在 `backend/` 下创建 `tests/` 镜像目录：

```
backend/tests/
├── __init__.py
├── conftest.py                  # 全局 fixtures
├── agents/
│   ├── __init__.py
│   ├── test_graph.py            # graph 编译、节点执行
│   ├── test_tools.py            # tool 输入验证、错误处理
│   └── test_workflow.py         # 完整 ReAct 循环
├── services/
│   ├── __init__.py
│   ├── test_user_profile.py     # 画像算法正确性
│   ├── test_bangumi_service.py  # 数据清洗逻辑
│   └── test_collection_service.py
├── api/
│   ├── __init__.py
│   ├── test_agent.py            # SSE 端点
│   ├── test_auth.py             # JWT 认证
│   └── test_collections.py
├── core/
│   ├── __init__.py
│   ├── test_security.py         # JWT 创建/解码
│   └── test_retry.py            # 重试装饰器
└── test_data/
    ├── sample_subject.json
    └── sample_collection.json
```

#### 11.2 `backend/tests/conftest.py`

```python
import pytest
from unittest.mock import AsyncMock, patch
from langchain_core.messages import AIMessage
from httpx import AsyncClient
from app.main import app

@pytest.fixture
async def async_client():
    async with AsyncClient(app=app, base_url="http://test") as ac:
        yield ac

@pytest.fixture
def mock_llm_with_tool_call():
    """Mock LLM 返回一个 tool_call"""
    async def _mock(messages):
        return AIMessage(
            content="",
            tool_calls=[{"name": "get_anime_info", "args": {"subject_id": 12345}, "id": "call_1"}]
        )
    return _mock

@pytest.fixture
def mock_llm_with_text():
    """Mock LLM 返回纯文本"""
    async def _mock(messages):
        return AIMessage(content="Here is my recommendation...")
    return _mock
```

#### 11.3 优先实现的核心测试

| 测试文件 | 测试内容 | 测试函数建议命名 |
|----------|---------|-----------------|
| `test_security.py` | JWT 创建/解码正确性 | `test_create_and_decode_token_preserves_user_id` / `test_decode_invalid_token_returns_none` |
| `test_user_profile.py` | 画像算法正确性 | `test_empty_collections_returns_empty_profile` / `test_frequency_and_score_weighted_tags_order_correctly` |
| `test_tools.py` | Tool 错误安全返回 | `test_get_anime_info_handles_api_error_gracefully` / `test_search_anime_advanced_empty_result_returns_empty_list` |
| `test_graph.py` | Graph 编译不报错 | `test_compile_graph_with_all_tools_succeeds` |
| `test_agent.py` | SSE 端点 401 | `test_chat_endpoint_rejects_missing_api_key` |

#### 11.4 新增依赖
```bash
cd backend && uv add --dev pytest pytest-asyncio pytest-cov httpx
```

### 验收方式
```bash
cd backend && uv run pytest tests/ -v --cov=app --cov-report=term
```
预期：30+ 测试通过，覆盖率 > 60%

---

# Phase 3：进阶级（2.5 Tier，2 周）

> **目标**：用户画像完整集成、增量收藏同步、混合检索、评测体系。

---

## 任务 P3-12：用户画像 — 四象限集成 + 缓存

**关联评估项**：Phase 3 画像优化
**优先级**：🟢 P2
**依赖**：P2-08（Celery 定时预计算）

### 执行步骤

1. 修改 `backend/app/services/user_profile_service.py` — 将 `_extract_four_quadrants` 的结果集成到 `generate_user_profile` 的返回值中
2. 缓存层：profile 计算结果写入 Redis（key: `user_profile:{user_id}`，TTL: 3600）
3. 新增 `backend/app/models/user_profile.py` — 画像持久化表（`user_id`, `profile_json`, `computed_at`）
4. 新增 `backend/app/api/v1/user_profile.py` — 画像 REST API 端点（GET `/api/v1/user-profile/me`）

---

## 任务 P3-13：增量收藏同步 — 状态机 + 断点恢复

**关联评估项**：Phase 3 收藏同步
**优先级**：🟢 P2
**依赖**：P2-08（Celery）

### 执行步骤

1. 新增 `backend/app/models/sync_state.py` — 同步状态表
2. 修改 `backend/app/services/bangumi_service.py` — 增量同步逻辑（基于 `last_sync_at`）
3. Celery 任务中实现状态机：`pending → fetching → upserting → done`
4. 断点恢复：从上次位置继续

---

## 任务 P3-14：混合检索 + Re-Rank

**关联评估项**：T3-#15（混合检索）
**优先级**：🟢 P2
**依赖**：P1-05（RAG 基础）

### 执行步骤

1. 修改 `backend/app/services/vector_service.py` — 新增双通道召回函数
2. 新增 `backend/app/services/rerank_service.py` — Cross-Encoder 重排序
3. 在 `semantic_search_anime` tool 中集成混合检索逻辑

---

## 任务 P3-15：评测体系 — 50 用例 + LLM-as-Judge

**关联评估项**：T3-#16（评测体系）
**优先级**：🟢 P2
**依赖**：P2-06（Plan+Execute）

### 执行步骤

1. 新增 `backend/tests/eval/` — 评测脚本目录
2. 构建 50 条标准测试用例（`test_cases.json`），覆盖搜索、推荐、分析三大场景
3. LLM-as-Judge 评分函数：事实准确度 / 完整性 / 推理质量 / 格式规范性
4. Prompt A/B 对比流水线

---

# Phase 4：卓越级（Tier 3，2 周+）

> **目标**：CI/CD、K8s 部署、LoRA 微调、安全沙箱。

---

## 任务 P4-16：CI/CD Pipeline

**依赖**：P2-11（测试体系）

### 执行步骤
创建 `.github/workflows/ci.yml`，内容参考 `business-driven-improvement-plan.md` 场景九 9.1 的完整 YAML。

---

## 任务 P4-17：K8s 部署

**依赖**：P4-16（CI/CD 构建镜像）

### 执行步骤
创建 `helm/otakuneko/` 目录，含 `Chart.yaml`、`values.yaml`、templates（Deployment、Service、ConfigMap、HPA）。

---

## 任务 P4-18：LoRA 微调

**依赖**：P1-05（RAG 基础，需要嵌入知识作为训练数据）

### 执行步骤
创建 `scripts/finetune/` 目录，含数据集构建、LoRA 训练、模型对比评测脚本。

---

## 任务 P4-19：Agent 安全沙箱

**依赖**：P4-17（K8s 部署）

### 执行步骤
新增 `backend/app/services/sandbox_service.py`，在 Docker-in-Docker 容器中执行不受信任的代码。

---

# 附录：依赖关系全图

```
Phase 1 (必须全部完成)
  ├── P1-01 安全修复 ──┬── P1-03 Graph 复用 ──→ P1-04 Agent Memory
  │                    │                              │
  ├── P1-02 清理调试    │                              ▼
  │                    └── P1-05 RAG 基础 ───────→ Phase 2
  │
Phase 2 (按优先级推进)
  ├── P2-06 Plan+Execute ← P1-04
  ├── P2-07 Tool 重试/降级 (独立)
  ├── P2-08 Celery 异步 ← P1-01
  ├── P2-09 LangFuse ← P2-06
  ├── P2-10 Prompt 管理 (独立)
  └── P2-11 测试体系 ← P1-01~05
                          │
Phase 3 (并行推进)          ▼
  ├── P3-12 画像优化 ← P2-08
  ├── P3-13 增量同步 ← P2-08
  ├── P3-14 混合检索 ← P1-05
  └── P3-15 评测体系 ← P2-06
                          │
Phase 4 (长线项目)          ▼
  ├── P4-16 CI/CD ← P2-11
  ├── P4-17 K8s ← P4-16
  ├── P4-18 LoRA ← P1-05
  └── P4-19 沙箱 ← P4-17
```

---

> **开始执行**：Agent 应从 Phase 1 的 P1-01 和 P1-02 开始（可并行），然后顺序执行 P1-03 → P1-04 → P1-05。
> **每次完成一个任务**，运行 `cd backend && uv run pyright app/` 验证无 type 错误，然后更新本文件对应任务的完成状态。
