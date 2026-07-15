# Agent 架构演进总纲

> 里程碑路线图 / 共享接口契约 / 子计划索引
> 日期：2026-05-20

---

## 1. 子计划索引

| 计划 | 文档 | 职责域 | 核心产出 |
|------|------|--------|---------|
| **Memory Plan** | [memory-checkpoint-fusion.md](./memory-checkpoint-fusion.md) | 状态持久化 + 上下文压缩 | `AsyncSqliteSaver` / `CodingAgentState` / `trim_messages` 管道 / LangGraph 原生 `Store` 长记忆 |
| **Tool Plan** | [tool-registry-mcp-integration.md](./tool-registry-mcp-integration.md) | 工具注册/路由 + MCP | `ToolRegistry` + 动态 `ToolNode` / `MCPTransport` 抽象 / `MCPToolAdapter` |

> 两计划职责正交，零冲突，共享 `graph.py` 和 `agent.py`。本总纲定义执行顺序和共享接口契约。
> 
> **LangGraph 原生升级声明**：本架构放弃所有自定义长记忆存储（`LongTermMemory`/`JsonStore`）和手动工具路由（`_execute_tool`），全面使用 LangGraph 原生 `Store`、动态 `ToolNode`、`graph.get_state()` 等内置能力。

---

## 2. 里程碑路线图

```
┌─────────────────────────────────────────────────────────────┐
│ M1 — 持久化基石 + 状态扩展                                    │
│   Memory Phase A: AsyncSqliteSaver + CodingAgentState        │
│   ⏱ 优先度：最高（所有上层能力依赖 checkpoint 持久化）        │
│   产出：graph.py checkpointer 替换 + State 五字段             │
└──────────────────────────┬──────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                                 ▼
┌─────────────────────────┐    ┌─────────────────────────────┐
│ M2a — 记忆管道           │    │ M2b — 工具体系重构           │
│ Memory B + C             │    │ Tool Step 1                 │
│ ShortTermMemory 下线     │    │ ToolRegistry + tools/ 拆分  │
│ CRUD API + Store 迁入    │    │ ToolResult schema + 日志     │
│ 可并行执行               │    │ 可并行执行                   │
└──────────┬──────────────┘    └──────────┬──────────────────┘
           │                              │
           └──────────┬───────────────────┘
                      ▼
┌─────────────────────────────────────────────────────────────┐
│ M3 — 上下文压缩管道 + MCP 预留 + Store 迁入                   │
│   Memory Phase D: trim_messages → _call_model               │
│   Memory Phase D: filter_messages → Verifier 节点            │
│   Memory Phase D: 日志 + fact_model 参数 + hash 修复           │
│   Memory Phase C: LongTermMemory → Store 迁移                │
│   Tool Step 2: MCPTransport 抽象 + MCPToolAdapter            │
│   耦合点：MCP 工具输出写入 CodingAgentState.last_terminal_output │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│ M4 — 生产就绪                                               │
│   Tool Step 3: StdioTransport + SSETransport 真实接入         │
│   Tool Step 3: 连接池 / 断线重连 / 心跳 / 审计日志            │
│   四阶段安全关卡: interrupt() + 高危命令拦截（后续独立计划）    │
│   四阶段原子工具集: Glob/Grep/patch_file/Bash（后续独立计划） │
└─────────────────────────────────────────────────────────────┘
```

### 执行顺序决策

| 约束 | 决定 |
|------|------|
| Memory Plan Phase A 是否必须在一切之前？ | **是**。`AsyncSqliteSaver` 是所有中断/恢复/time-travel 的基石 |
| M2a 和 M2b 能否并行？ | **能**。不同人/不同时间可并行推进，唯一共享 `graph.py` 按接口契约各自修改 |
| Tool Plan Step 2 能不能不等 Memory Phase D？ | MCP 抽象层 (transport/adapter) **可以**先写；但 MCP 工具输出注入 `CodingAgentState` 需等到 State 定义就绪 |

---

## 3. 共享接口契约

### 3.1 `ChatWorkflow` 最终签名

```python
# agents/graph.py — 合并后完整签名
class ChatWorkflow:
    def __init__(
        self,
        api_key: str,
        base_url: str,
        # ── Memory Plan ──
        db_path: str = "data/checkpoints.db",
        store = None,                              # LangGraph Store（InMemoryStore / PostgresStore）
        # ── Tool Plan ──
        registry: Optional["ToolRegistry"] = None,
    ):
```

> 各计划在自己的 Phase/Step 中只添加自己需要的参数。`store` 由外部传入（`agent.py` 全局单例），`ChatWorkflow` 不负责创建 Store。

### 3.2 `CodingAgentState` — 字段归属

```python
# agents/graph.py
from typing import Annotated, List
from langgraph.graph.message import add_messages
import operator

class CodingAgentState(TypedDict):
    # ── 核心（LangGraph 原生）──
    messages: Annotated[List[BaseMessage], add_messages]

    # ── Memory Plan 产出 ──
    current_dir: str                                   # Phase A 引入，bash 执行后更新
    plan: str                                          # Phase A 引入，Planner 产出
    completed_steps: Annotated[List[str], operator.add]  # ⚠️ 必须用 reducer！默认覆盖

    # ── Tool Plan + Memory Plan 共享 ──
    last_terminal_output: str                          # Phase A 定义；Tool Step 2 开始写入
```

> ⚠️ **Reducer 陷阱**：`completed_steps` 不加 `Annotated[List[str], operator.add]` 的话，LangGraph 每次状态更新会**覆盖**整个列表而非追加。需要导入 `import operator`。

### 3.3 `_compile_graph()` 节点归属 — 动态 ToolNode

```python
def _compile_graph(self):
    workflow = StateGraph(CodingAgentState)

    # ── Tool Plan：动态拉取全量工具（本地 + MCP），统一注入 ToolNode ──
    runtime_tools = asyncio.run(self.registry.get_runtime_tools())

    # ── Memory Plan 引入 ──
    workflow.add_node("planner", self._plan_task)
    workflow.add_node("executor", ToolNode(runtime_tools))  # 统一动态 ToolNode
    workflow.add_node("verifier", self._verify_result)

    workflow.add_edge(START, "planner")
    workflow.add_conditional_edges("planner", self._route_from_planner, {
        "execute": "executor",
        "end": END,
    })
    workflow.add_edge("executor", "verifier")
    workflow.add_conditional_edges("verifier", self._should_retry, {
        "retry": "planner",
        "continue": "executor",
        "end": END,
    })

    # ── Tool Plan Step 3 (后续) ──
    # workflow.add_node("safety_check", ...)  # 四阶段安全关卡

    return workflow.compile(checkpointer=self.checkpointer, store=self.store)
    # ⚠️ store 参数在 Phase C 加入，传递 LangGraph Store 实例
```

### 3.4 `agent.py` 全局实例声明

```python
# ── Memory Plan: 长记忆 → LangGraph Store ──
from langgraph.store.memory import InMemoryStore

_store = InMemoryStore()  # 本地开发；生产用 PostgresStore.from_conn_string(DB_URI)

# ── Tool Plan: ToolRegistry 单例 ──
from app.agents.registry import ToolRegistry
from app.agents.tools import register_all

_tool_registry = ToolRegistry()
register_all(_tool_registry)
```

---

## 4. 测试目录融合视图

两个计划的测试共享统一的 `tests/` 镜像结构。各计划创建时自觉避让、不互相覆盖。

```
tests/
├── conftest.py                         # 共享 fixtures (Memory: db_ 前缀; Tool: tool_ 前缀)
│
├── agents/
│   ├── test_graph_checkpoint.py        # Memory A — AsyncSqliteSaver 持久化契约
│   ├── test_registry.py                # Tool Step 1 — ToolRegistry + 动态 ToolNode
│   ├── tools/
│   │   ├── test_anime.py               # Tool Step 1
│   │   ├── test_search.py              # Tool Step 1
│   │   ├── test_datetime.py            # Tool Step 1
│   │   ├── test_profile.py             # Tool Step 1
│   │   └── test_base.py                # Tool Step 1 — ToolResult schema
│   └── mcp/
│       ├── test_transport.py           # Tool Step 2
│       ├── test_adapter.py             # Tool Step 2 — MCPToolAdapter schema 转换
│       └── test_integration.py         # Tool Step 3
│
├── memory/
│   ├── test_manager.py                 # Memory B — load_context 从 checkpoint + Store
│   ├── test_store_integration.py       # Memory C — Store.put/search/delete
│   ├── test_store_search.py            # Memory D — Store.asearch 语义搜索
│   ├── test_memory_logging.py          # Memory D — 日志补全
│   └── retrievers/                     # 可选 — BM25/Vector/Hybrid 检索插件
│       ├── test_bm25_retriever.py
│       ├── test_vector_retriever.py
│       └── test_hybrid_retriever.py
│
└── api/
    └── v1/
        └── test_agent_memory.py        # Memory C — chat history CRUD（graph.get_state）
```

---

## 5. 依赖交叉表

### 5.1 Memory Plan → Tool Plan 提供的接口

| Memory 产出 | Tool Plan 使用者 |
|------------|-----------------|
| `CodingAgentState.last_terminal_output` | MCP bash 工具执行后写入输出 |
| `CodingAgentState.current_dir` | MCP bash 工具 `cwd` 参数 |
| `AsyncSqliteSaver` checkpointer | 安全关卡 interrupt 断点持久化 |
| `trim_messages` 管道 | MCP 工具产生的大量 ToolMessage 被自动裁剪 |
| LangGraph `Store`（`store.put/search`） | MCP 工具执行完毕后，摘要结果可写入 Store 跨会话共享 |

### 5.2 Tool Plan → Memory Plan 提供的接口

| Tool 产出 | Memory Plan 使用者 |
|----------|-------------------|
| `ToolResult` 统一 schema | Verifier 节点读取 `success` / `error_type` 决策路由 |
| 动态 `ToolNode`（本地+MCP 统一执行） | `_compile_graph()` 的 executor 节点 |
| `MCPToolAdapter.to_langchain_tool()` | `get_runtime_tools()` 包装 MCP 工具为标准 BaseTool |

---

## 6. 风险交叉

| 风险 | 影响两个计划 | 缓解 |
|------|------------|------|
| `graph.py` 多节点图 + `bind_tools` schema 合并 导致 LLM 每次调用 token 激增 | 上下文压缩 `trim_messages` 先裁剪再 bind | Memory Phase D 在 Tool Step 2 之前必须完成 |
| `conftest.py` fixture 命名冲突 | 两计划各自写 fixture 可能撞名 | 本总纲约定：Memory 的 fixture 加 `db_` 前缀，Tool 的 fixture 加 `tool_` 前缀 |
| `AgentState` vs `CodingAgentState` 类型漂移 | 旧 code path 仍用 `AgentState` | 新 `CodingAgentState` 是 `AgentState` 的超集，兼容旧 API |

---

## 7. 版本锁

| 依赖 | 版本（计划） | 实际安装 | 说明 |
|------|-------------|---------|------|
| `langgraph` | `>=1.0.10` | — | 两个计划共享 |
| `langgraph-checkpoint-sqlite` | `>=2.0.0` | `3.1.0` | Memory Plan 引入；`AsyncSqliteSaver` 在 `aio` 子模块 |
| `langchain-core` | `>=1.2.11` | — | `trim_messages` / `filter_messages` 来源 |
| `mcp` | `>=1.0.0` | — | Tool Plan Step 2 引入 |

---

## 8. 交付检查清单

- [x] M1: `AsyncSqliteSaver` 可跨连接持久化（6 tests pass）— 2026-05-20
- [x] M1: `CodingAgentState` 五字段（含 `operator.add` reducer）Graph 编译通过 — 2026-05-20
- [x] M2a: `ShortTermMemory` + `JsonStore` + `LongTermMemory` 已删除；history CRUD 通过 `graph.aget_state()` — 2026-05-20
- [x] M2b: `tools.py` 已拆分；`ToolRegistry` 统一注册中心就绪 — 2026-05-20
- [x] `graph.compile(store=store)` 长记忆迁入 Store（提前至 M2a-C 完成） — 2026-05-20
- [x] `DELETE /chat/history/{thread_id}` API 端点正常 — 2026-05-20
- [x] 全量回归: `uv run pytest tests/ -v` 12/12 全部通过 — 2026-05-20
- [x] M3: `trim_messages` 在 `_call_model` 中生效 — 2026-05-20
- [x] M3: `filter_messages` 裁剪旧 ToolMessage（集成至 `_call_model`）— 2026-05-20
- [x] M3: 全局日志补全（manager.py + graph.py）— 2026-05-20
- [x] M3: `fact_model` 参数化替代硬编码 — 2026-05-20
- [x] `MCPTransport` 抽象 + `MCPToolAdapter` schema 转换 — 2026-05-20
- [x] `ToolRegistry.get_runtime_tools()` / `get_all_schemas()` MCP 本地统一 — 2026-05-20
- [x] `load_context()` 注入 `completed_steps` + `terminal_context` — 2026-05-20
- [x] M4: `StdioTransport` + `SSETransport` 真实接入 — 2026-05-20
- [x] M4: `MCPConnectionPool` 连接池 + 断线重连 + 超时熔断 — 2026-05-20
- [x] M4: `MCPHeartbeat` 心跳检测 + 审计日志 — 2026-05-20
- [x] 全量回归: 38/38 passed — 2026-05-20
- [ ] M4: interrupt() 安全关卡 + 高危命令拦截
- [ ] M4: 原子工具集 (Glob/Grep/patch_file/Bash)
- [x] M5: `reasoning_chunk` SSE 推理文本事件 — 2026-05-21

---

## 9. M5 — Reasoning Chunk 思考过程流式推送（2026-05-21）

> 需求来源：[frontend-chat-improvement.md](./frontend-chat-improvement.md) Round 4.1
> 前端已预埋 `reasoning_chunk` SSE 处理链路，后端只需新增事件推送即可启用 ThinkingPanel 推理节点。

### 9.1 背景

前端 ThinkingPanel 支持将 AI 的"思考推理文本"与"工具调用"分别渲染：
- 🔴 致命差距：后端当前将所有 LLM 流式文本统一以 `message_chunk` 事件推送，前端无法区分"推理独白"和"最终回答"
- 需求：模型在调用工具**之前**的思考文本以 `reasoning_chunk` 事件独立推送

### 9.2 SSE 事件契约

```
event: reasoning_chunk
data: {"content": "我需要先搜索与用户描述匹配的动画作品，然后获取详细信息..."}

```

| 字段 | 类型 | 说明 |
|------|------|------|
| `content` | `string` | 模型推理独白的流式文本片段（与 `message_chunk` 相同的打字机模式） |

### 9.3 注入点

**文件**：`app/agents/graph.py` → `ChatWorkflow.stream_chat()`

**逻辑**：ReAct 循环中，在首次工具调用执行之前，LLM 输出的文本为"推理阶段"；首次工具执行完毕后，后续文本为"回答阶段"。

```
Agent 第 1 次迭代
  on_chat_model_stream → reasoning_chunk  ← 新增
  on_chat_model_end    → plan_update
  on_tool_start        → tool_start       ← 首次工具调用
  on_tool_end          → tool_end / progress
  ↓ 设置 has_executed_tools = True

Agent 第 2 次迭代
  on_chat_model_stream → message_chunk    ← 恢复原有
  ...
```

### 9.4 实现（1 行新增 + 2 行修改）

```python
# graph.py → stream_chat() — 新增标志
has_executed_tools = False

# on_chat_model_stream 分支 — 条件分派
if not has_executed_tools:
    yield {"type": "reasoning_chunk", "content": chunk.content}
else:
    yield {"type": "message_chunk", "content": chunk.content}

# on_tool_start 分支 — 首次工具调用后切换
if not has_executed_tools:
    has_executed_tools = True
```

### 9.5 前后端 SSE 事件对照表（终态）

| SSE 事件 | 触发时机 | 前端处理 | 状态 |
|---------|---------|---------|------|
| `reasoning_chunk` | 模型在首次工具调用前的推理文本 | ThinkingPanel 🟣推理节点流式追加 | ✅ 新增 |
| `tool_start` | 工具开始调用 | ToolCall `status: 'running'` | ✅ 已有 |
| `tool_end` | 工具调用结束 | ToolCall `status: 'success'` + 结果渲染 | ✅ 已有 |
| `message_chunk` | 首次工具执行后的 LLM 回答 | ChatItem Markdown 渲染 | ✅ 已有 |
| `plan_update` | 模型完成当前轮推理 | ThinkingPanel plan 摘要 | ✅ 已有 |
| `progress` | 工具执行完成 | ProgressPanel 步骤更新 | ✅ 已有 |
| `error` | 任何错误 | Error fallback | ✅ 已有 |

### 9.6 交付检查清单

- [x] M5: `stream_chat()` 新增 `reasoning_chunk` SSE 事件 — 2026-05-21

---

## 10. Round 5 — 流式渲染断裂根因（2026-05-21）

> 事实：后端的 `reasoning_chunk` / `tool_start` / `tool_end` / `message_chunk` SSE 事件**均正确逐条推送**。
> 断裂点全在前端 `MessageList` + `ThinkingPanel` 的三个布尔状态计算。

### 10.1 后端侧验证结论

| 检查点 | 结果 |
|--------|------|
| `astream_events(version="v2")` 是否逐 token 推送 | ✅ 每次 `on_chat_model_stream` 携带 1 个 token |
| `reasoning_chunk` 是否在首次 tool 前推送 | ✅ `has_executed_tools=False` 期内全部走 reasoning |
| `tool_start` / `tool_end` 是否携带完整信息 | ✅ name/inputs/output/duration_ms 完整 |
| `message_chunk` 是否在首次 tool 后推送 | ✅ `has_executed_tools=True` 后走 message |
| `format_sse()` 格式是否与前端 `parseSSE()` 兼容 | ✅ `event: xxx\ndata: {...}\n\n` |

**结论**：后端无 Bug，无需修改。

### 10.2 前端 Bug 汇总

详见 [frontend-chat-improvement.md §12](./frontend-chat-improvement.md#12-round-5--流式渲染断裂根因分析2026-05-21)

| Bug | 文件 | 一句话 |
|-----|------|--------|
| A | `MessageList.tsx:L56` | `isStreaming` 要求 `!!msg.content` → reasoning 阶段 false |
| B | `ThinkingPanel.tsx:L77` | `isDone` 在纯 reasoning 阶段误报完成 |
| C | `ThinkingPanel.tsx:L72` | `isThinking` 在工具执行阶段因 isStreaming=false 而 false |
| D | `ThinkingPanel.tsx:L44` | auto-collapse 抢占用户手动展开 |
