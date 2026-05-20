# Memory → LangGraph Checkpoint 融合重构计划

> 状态：待确认 / 日期：2026-05-20

## 1. 目标

- `JsonStore` JSON 文件管理 → LangGraph `AsyncSqliteSaver` checkpoint 持久化（短记忆）
- `LongTermMemory` 自定义 JSON → LangGraph 原生 `Store`（全局跨线程长记忆）
- 完整 CRUD：读历史、删会话、列 checkpoints（全部通过 LangGraph 原生 API）
- 引入 `trim_messages` / `filter_messages` 等标准工具，零手搓上下文压缩
- 消除手动 SQL/JDBC 读 checkpoint 表 — 全部使用 `graph.get_state()` / `graph.get_state_history()`

## 2. 现状问题

| 问题 | 严重度 |
|------|--------|
| `InMemorySaver` 重启丢失 | 🔴 |
| 路径依赖 CWD（跨平台不可靠） | 🔴 |
| `add_fact()` 去重时 O(N) embedding | 🔴 |
| `extract_and_store_facts` 异常静默 | 🔴 |
| 匿名用户对话不保存 | 🔴 |
| 硬编码 `gpt-3.5-turbo` | 🟡 |
| 全模块零日志 | 🟡 |
| `hash(api_key)` 字典键不可靠 | 🟡 |
| 自定义 `LongTermMemory` 管理事实 — LangGraph 原生 `Store` 已提供 `put/search/delete` | 🟡 |

## 3. 保留 / 替换

| 保留 | 替换/删除 |
|------|-----------|
| LangGraph 原生 `Store` 接管长期记忆（`store.put/search/delete`） | `JsonStore` 整个 `stores/` 目录 |
| `MemoryManager.extract_and_store_facts()` → 改写为写入 `Store` | `ShortTermMemory` 整个 `short_term.py` |
| BM25 / Vector / Hybrid Retriever → 可选保留作为 Store 检索补充 | `LongTermMemory` 自定义 CRUD（`add_fact/delete_fact/list_facts`）— Store 原生提供 |
|  | `MemoryManager.save_turn()` |

## 4. 新架构分层

```
API (agent.py)          POST /chat   GET/DELETE /chat/history
                            │   ↑ graph.get_state(config)
Agent (graph.py)        AsyncSqliteSaver (checkpoints.db) → 自动持久化短记忆
Store (langgraph.store) InMemoryStore / PostgresStore → 全局跨线程长记忆
Memory (manager.py)     load_context() 从 checkpoint + Store 读取
```

## 5. 新增依赖

```toml
# pyproject.toml
"langgraph-checkpoint-sqlite>=2.0.0",
"pytest>=8.0",
"pytest-asyncio>=0.24",
"pytest-mock>=3.14",
```

---

## 6. 上下文压缩：LangChain 标准工具全景

> **原则：优先用标准库，绝不手搓。** 以下全部来自 `langchain_core.messages`，当前项目已依赖 `langchain-core>=1.2.11`。

### 工具一：`trim_messages` — 按 token 数裁剪

```python
from langchain_core.messages import trim_messages
```

| 参数 | 说明 |
|------|------|
| `max_tokens` | 裁剪后的最大 token 数 |
| `strategy="last"` | 保留最新消息（默认）；`"first"` 保留最早 |
| `token_counter=llm` | 直接传 LLM 实例，自动用模型自带 tokenizer |
| `include_system=True` | 始终保留 SystemMessage |
| `start_on="human"` | 确保输出以 HumanMessage 开头 |
| `end_on=("human","tool")` | 确保输出以 Human/Tool 结尾 |
| `allow_partial=True` | 允许拆分单条消息内容 |

**在 graph 中的位置**：`_call_model` 节点调用 LLM 前，对 `state["messages"]` 执行。

```python
# graph.py — _call_model 添加一行
messages = trim_messages(
    state["messages"], max_tokens=8000, strategy="last",
    token_counter=self.llm, include_system=True,
    start_on="human", end_on=("human", "tool"),
)
response = await self.llm_with_tools.ainvoke(messages)
```

### 工具二：`filter_messages` — 按类型/名称/ID 过滤

```python
from langchain_core.messages import filter_messages

# 只保留 human + ai 消息，移除所有 tool 消息
filtered = filter_messages(messages, include_types=["human", "ai"])

# 排除特定 name 的工具输出
filtered = filter_messages(messages, exclude_names=["bash_exec"])
```

作为 LCEL Runnable：`filter_messages(...) | llm` 直接链式调用。

### 工具三：`RemoveMessage` — 从 State 中永久删除

```python
from langchain_core.messages import RemoveMessage

# 在 graph 节点中返回，LangGraph add_messages reducer 自动处理删除
return {"messages": [RemoveMessage(id=msg.id) for msg in old_tool_messages]}
```

### 工具四（LangGraph Store）：`store.asearch()` — 语义搜索长期记忆

```python
# LangGraph 原生 Store API，无需手写 BM25/Vector 混合检索
# 底层自动使用 embedding + vector search
facts = await store.asearch(
    ("memories", user_id), 
    query="用户偏好",
    limit=5
)
```

> **注意**：`store.asearch()` 依赖编译时传入的 `store` 配置 embedding 模型。本地开发可用 `InMemoryStore`，生产用 `PostgresStore` + pgvector。

---

## 7. 分步执行

> 每步代码改完立刻跑对应 pytest，通过才进下一步。

### 4.0 前置：测试基础设施

1. `pyproject.toml` 追加 `pytest` / `pytest-asyncio` / `pytest-mock`
2. 创建 `tests/conftest.py`（event_loop fixture + `temp_db_path` fixture）
3. 验证：`uv sync && uv run pytest --collect-only`

### Phase A: Checkpoint 持久化基石

| Step | 动作 |
|------|------|
| A1 | `pyproject.toml` 加 `langgraph-checkpoint-sqlite` |
| A2 | `graph.py`：`InMemorySaver` → `AsyncSqliteSaver.from_conn_string(db_path)` |
| A3 | **同步引入** `CodingAgentState`（`current_dir` / `plan` / `last_terminal_output` / `completed_steps: Annotated[List[str], operator.add]`）+ Planner / Executor / Verifier 三节点图 |
| A3b | ⚠️ **Reducer 陷阱**：`completed_steps` 必须用 `Annotated[List[str], operator.add]`，否则 LangGraph 默认覆盖而非追加 |
| A4 | 验证：6 条测试 — 跨连接持久化、累积、删除、列表、空线程返回 None、自动建库 |

**测试文件**：`tests/agents/test_graph_checkpoint.py`（6 tests）

### Phase B: ShortTermMemory 下线 + API 改用原生 State History

| Step | 动作 |
|------|------|
| B1 | `manager.py`：`load_context()` 从 checkpoint 读；删除 `save_turn()` |
| B2 | `agent.py`：`GET /chat/history` 改用 `graph.aget_state(config)`（LangGraph 原生 API，无需手动读 SQL） |
| B3 | 删除 `short_term.py` + `stores/__init__.py` + `stores/json_store.py` |
| B4 | 验证：4 条 — 从 checkpoint 加载消息、不存在的线程返回空、长记忆注入、无 checkpointer 降级 |

**测试文件**：`tests/memory/test_manager.py`（4 tests）

### Phase C: API 补全 + 长期记忆迁入 Store

| Step | 动作 |
|------|------|
| C1 | `graph.py`：`_compile_graph` 接收 `store` 参数，`graph.compile(checkpointer=cp, store=store)` |
| C2 | `MemoryManager.extract_and_store_facts()`：改写为 `await store.aput(namespace, key, value)`（LangGraph 原生 Store API） |
| C3 | `MemoryManager.load_context()`：调用 `store.asearch(namespace, query)` 替代自定义 BM25/Vector 混合检索 |
| C4 | `agent.py`：加 `DELETE /chat/history/{thread_id}`（使用 `graph.aget_state_history()` 列出 + `checkpointer.adelete_thread()` 删除） |
| C5 | 删除 `long_term.py` 自定义 CRUD（`add_fact`/`delete_fact`/`list_facts`）— 全部由 Store 原生提供 |
| C6 | 验证 API 端点（4 tests） |
| C7 | 验证 Store 集成（6 tests）：put/search/delete/list |

**测试文件**：
- `tests/api/v1/test_agent_memory.py`（4 tests）
- `tests/memory/test_store_integration.py`（6 tests）— mock `store.aput`/`store.asearch`
- `tests/memory/retrievers/` — 保留（BM25/Vector/Hybrid 作为可选检索插件，不绑死 Store）

### Phase D: 质量加固 + 上下文压缩

| Step | 动作 |
|------|------|
| D1 | `graph.py` `_call_model`：消息传给 LLM 前过 `trim_messages`（标准工具，一行代码） |
| D2 | `graph.py` Verifier 节点：读取 `last_terminal_output`，执行 `filter_messages` 裁剪旧 ToolMessage |
| D3 | `manager.py` `load_context()`：注入 `completed_steps` 摘要 + `terminal_context`（切片后） |
| D4 | 全模块补日志（`get_logger(__name__)`） |
| D5 | `manager.py`：`fact_model` 参数替代硬编码 |
| D6 | `agent.py`：`hash(api_key)` → 直接 `(api_key, base_url)` |
| D7 | 验证：Store 语义搜索（2 tests）+ 日志输出（2 tests） |

**测试文件**：
- `tests/memory/test_store_search.py`（2 tests）— mock `store.asearch` 语义搜索
- `tests/memory/test_memory_logging.py`（2 tests）

---

## 8. 文件变更总表

### 新增

```
tests/
├── conftest.py
├── agents/test_graph_checkpoint.py
├── memory/
│   ├── test_manager.py
│   ├── test_store_integration.py
│   ├── test_store_search.py
│   ├── test_memory_logging.py
│   └── retrievers/               # 可选保留
│       ├── test_bm25_retriever.py
│       ├── test_vector_retriever.py
│       └── test_hybrid_retriever.py
└── api/v1/test_agent_memory.py
```

### 修改

| 文件 | 变更 |
|------|------|
| `pyproject.toml` | + `langgraph-checkpoint-sqlite` / `pytest` / `pytest-asyncio` / `pytest-mock` |
| `agents/graph.py` | `AsyncSqliteSaver` + `CodingAgentState`（含 `operator.add` reducer）+ 多节点图 + `trim_messages` + `store` 参数 |
| `memory/manager.py` | `load_context` 从 checkpoint + Store 读；删 `save_turn`；加 `fact_model`；加日志 |
| `memory/__init__.py` | 移除 `ShortTermMemory` / `LongTermMemory` 导出；导出 `MemoryManager`（Store 适配版） |
| `api/v1/agent.py` | `/chat/history` 用 `graph.aget_state()`；+ `DELETE`；修复 `hash`；初始化 `Store` 实例 |

### 删除

- `memory/short_term.py`
- `memory/long_term.py` — 自定义 CRUD 被 Store 替代
- `memory/stores/__init__.py`
- `memory/stores/json_store.py`

---

## 9. 四阶段路线图对照

| 阶段 | 本计划覆盖 |
|------|-----------|
| **一** State & Loop | Phase A 同步引入 `CodingAgentState` + 多节点图 |
| **二** Tools & MCP | 后续独立计划（原子工具集 + bash/patch/grep） |
| **三** Context Compaction | Phase D：`trim_messages` + `filter_messages` + 步骤摘要（全标准工具） |
| **四** Permission & Sandbox | 后续独立计划（`interrupt()` + 高危命令拦截） |

---

## 10. 一键验证

```bash
cd backend && uv sync

# Phase A
uv run pytest tests/agents/test_graph_checkpoint.py -v

# Phase B
uv run pytest tests/memory/test_manager.py -v

# Phase C
uv run pytest tests/memory/test_store_integration.py tests/api/v1/test_agent_memory.py -v

# Phase C (optional retrievers)
uv run pytest tests/memory/retrievers/ -v

# Phase D
uv run pytest tests/memory/test_store_search.py tests/memory/test_memory_logging.py -v

# 全量回归
uv run pytest tests/ -v
```

## 11. 确认清单

1. ✅ `ShortTermMemory` + `JsonStore` 完全下线？
2. ✅ Phase A 同步引入 `CodingAgentState` + 多节点图？
3. ✅ Phase D 用 `trim_messages` / `filter_messages` 标准工具做上下文压缩？
4. ✅ 原子工具集 + 安全关卡放后续独立计划？
5. ✅ `data/checkpoints.db` 路径 OK？
