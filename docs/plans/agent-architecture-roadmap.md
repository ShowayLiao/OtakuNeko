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

| 依赖 | 当前版本 | 说明 |
|------|---------|------|
| `langgraph` | `>=1.0.10` | 两个计划共享 |
| `langgraph-checkpoint-sqlite` | `>=2.0.0` | Memory Plan 引入 |
| `langchain-core` | `>=1.2.11` | `trim_messages` / `filter_messages` 来源 |
| `mcp` | `>=1.0.0` | Tool Plan Step 2 引入 |

---

## 8. 交付检查清单

- [ ] M1: `AsyncSqliteSaver` 可跨连接持久化（6 tests pass）
- [ ] M1: `CodingAgentState` 五字段（含 `operator.add` reducer）Graph 编译通过
- [ ] M2a: `ShortTermMemory` + `JsonStore` + `LongTermMemory` 已删除；history CRUD 通过 `graph.aget_state()`
- [ ] M2b: `tools.py` 已拆分；`ToolRegistry.get_runtime_tools()` 本地+MCP 统一返回
- [ ] M3: `trim_messages` 在 `_call_model` 中生效；`graph.compile(store=store)` 长记忆迁入 Store
- [ ] M3: 动态 `ToolNode` wrapper 可正常执行 MCP 工具（mock MCP server 测试通过）
- [ ] M3: `MCPToolAdapter` schema 转换正确
- [ ] M4: `graph.get_state()` / `graph.get_state_history()` API 端点正常
- [ ] 全量回归: `uv run pytest tests/ -v` 全部通过
