# Think-Speak 双节点架构改造

> 将思考与最终输出从「标签解析」模式迁移到「双节点物理分离」模式
> 日期：2026-06-02

---

## 1. 动机

当前 [graph.py](../../backend/app/agents/graph.py) 通过流式解析 LLM 输出中的 `<think>...</think>` XML 标签来区分推理过程与最终回复。该方案存在三个结构性问题：

| 问题 | 影响 |
|------|------|
| **System Prompt 未指令标签格式** | 仅 DeepSeek-R1 等原生输出 `<think>` 的模型碰巧可用，GPT/Claude/Qwen 等完全不工作 |
| **8 字符滚动 buffer 边界漏洞** | `<thi` + `nk>` 跨两个 chunk 到达时漏检 |
| **标签与讨论内容冲突** | 用户问 "解释 `<think>` 标签是什么" 时解析器误判 |
| **标签浪费 token** | 每次对话多余消耗标记 token |

**核心决策**：利用 LangGraph 节点物理边界，将推理(`think`)与回复(`speak`)拆为两个独立节点。`astream_events` v2 的 `metadata.langgraph_node` 原生支持流式分流，零解析成本。

---

## 2. 架构变更

### 2.1 图拓扑变更

```
变更前 (单节点 + 标签解析):              变更后 (双节点):
                                      
START                                   START
 │                                       │
 ▼                                       ▼
agent ──[tools_condition]──→ tools      think ──[_think_condition]──→ tools
 │                    ↑       │          │  ▲              │speak      │  ▲
 │                    └───────┘          │  └──────────────┘           │  │
 ▼                                       ▼                             │  │
 END                                    speak ─────────────────────────┘  │
                                         │                                 │
                                         ▼                                 │
                                        END ◄──────────────────────────────┘
```

### 2.2 节点职责

| 节点 | LLM 配置 | System Prompt 定位 | 输出流向 SSE |
|------|---------|-------------------|-------------|
| `think` | `llm.bind_tools(tools)` | 内部推理引擎：分析意图 → 搜索数据 → 整合信息，可用工具 | `thinking_start` → `thinking_chunk` → `thinking_end` |
| `speak` | `llm`（无工具绑定） | 面向用户的助手：基于 think 的推理结果，用自然语言回复，**不可调用工具** | `message_start` → `message_chunk` → `message_end` |
| `tools` | —（ToolNode，不变） | — | `tool_call_start` → `tool_call_end` |

### 2.3 条件路由

`tools_condition`（LangGraph 预置）返回 `"tools"` 或 `END`，不适用。替换为自定义 `_think_condition`：

```python
def _think_condition(self, state: CodingAgentState) -> str:
    last_message = state["messages"][-1]
    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "tools"
    return "speak"
```

---

## 3. 实现步骤

### Step 1：State 扩展 — 增加 `reasoning_trace`

**文件**：`backend/app/agents/graph.py`

在 `CodingAgentState` 中增加一个字段，存储 think 节点的完整推理文本（非流式捕获，用于调试/日志）：

```python
class CodingAgentState(TypedDict):
    messages: Annotated[List[BaseMessage], add_messages]
    reasoning_trace: str          # ← 新增
    current_dir: str
    plan: str
    completed_steps: Annotated[List[str], operator.add]
    last_terminal_output: str
```

> 变更半径：仅 State TypedDict 定义，下游 `_call_model`/`stream_chat` 中 `astream_events` 初始 dict 加一行 `"reasoning_trace": ""`。

### Step 2：拆分 `_call_model` → `_think_node` + `_speak_node`

**文件**：`backend/app/agents/graph.py`

**`_think_node`**（替代原 `_call_model`）：
- 在消息列表前**临时插入**一条 think 专用 system prompt（不写入 state）
- 使用 `self.llm_with_tools`（绑定工具）调用
- 返回 `{"messages": [response], "reasoning_trace": response.content}`

```python
async def _think_node(self, state: CodingAgentState):
    messages = list(state["messages"])
    messages = filter_messages(messages, include_types=["human", "ai", "system", "tool"])
    messages = self._trim_and_clean(messages)

    # 注入 think 专用 system prompt（不持久化到 state）
    think_sys = {"role": "system", "content": THINK_SYSTEM_PROMPT}
    messages.insert(0, think_sys)

    response = await self.llm_with_tools.ainvoke(messages)
    return {
        "messages": [response],
        "reasoning_trace": response.content if hasattr(response, "content") else "",
    }
```

**`_speak_node`**（新增）：
- 在消息列表前**临时插入**一条 speak 专用 system prompt（合并用户配置的 persona/tone/rules）
- 使用 `self.llm`（**不**绑定工具）调用
- 返回 `{"messages": [response]}`

```python
async def _speak_node(self, state: CodingAgentState):
    messages = list(state["messages"])
    messages = filter_messages(messages, include_types=["human", "ai", "system", "tool"])
    messages = self._trim_and_clean(messages)

    # 注入 speak 专用 system prompt（合并用户 persona）
    speak_sys = {"role": "system", "content": self._speak_prompt or SPEAK_SYSTEM_PROMPT}
    messages.insert(0, speak_sys)

    response = await self.llm.ainvoke(messages)
    return {"messages": [response]}
```

**提取公共方法 `_trim_and_clean`**：
- 将原来 `_call_model` 中的 `filter_messages` + `trim_messages` + `_strip_orphaned_tool_calls` 三段逻辑抽成独立方法，两个节点复用。

### Step 3：修改 `_compile_graph` — 注册新拓扑

**文件**：`backend/app/agents/graph.py`

```python
def _compile_graph(self):
    workflow = StateGraph(CodingAgentState)
    workflow.add_node("think", self._think_node)
    workflow.add_node("speak", self._speak_node)
    workflow.add_node("tools", ToolNode(self._get_tools()))

    workflow.add_edge(START, "think")
    workflow.add_conditional_edges("think", self._think_condition, {
        "tools": "tools",
        "speak": "speak",
    })
    workflow.add_edge("tools", "think")
    workflow.add_edge("speak", END)

    return workflow.compile(checkpointer=self.checkpointer, store=self._store)
```

### Step 4：重写 `stream_chat` — 移除标签解析，改为节点分流

**文件**：`backend/app/agents/graph.py`

**删除**：
- `_StreamPhase` 类
- `_detect_think_boundary` 函数
- `phase` / `_inside_think` / `_boundary_buffer` 变量及所有相关分支逻辑
- 不再需要 `Tuple` import

**替换为**：基于 `metadata.langgraph_node` 的简洁分流逻辑

```python
async for event in self.app.astream_events(
    {"messages": enriched_messages, "current_dir": "", "plan": "",
     "completed_steps": [], "last_terminal_output": "", "reasoning_trace": ""},
    config=config, version="v2"
):
    kind = event["event"]
    node_name = event.get("metadata", {}).get("langgraph_node")

    if kind == "on_chat_model_stream":
        chunk = event["data"]["chunk"]

        # 工具调用 delta（think 节点内）
        if hasattr(chunk, "tool_call_chunks") and chunk.tool_call_chunks:
            for tc in chunk.tool_call_chunks:
                if tc.get("name"):
                    yield _emit("tool_call_delta", id=tc.get("id"),
                                name=tc.get("name"), delta=tc.get("args", ""))
            continue

        if not (hasattr(chunk, "content") and isinstance(chunk.content, str) and chunk.content):
            continue

        delta = chunk.content

        if node_name == "think":
            if not _thinking_active:
                _thinking_active = True
                yield _emit("thinking_start")
            yield _emit("thinking_chunk", content=delta)

        elif node_name == "speak":
            if _thinking_active:
                _thinking_active = False
                yield _emit("thinking_end")
            if not _message_started:
                _message_started = True
                yield _emit("message_start")
            yield _emit("message_chunk", content=delta)

    elif kind == "on_chat_model_end":
        if node_name == "think" and _thinking_active:
            yield _emit("thinking_end")
            _thinking_active = False
        elif node_name == "speak" and _message_started:
            yield _emit("message_end")
            _message_started = False

    elif kind == "on_tool_start":
        if _thinking_active:
            yield _emit("thinking_end")
            _thinking_active = False
        # ... tool_start/tool_end 逻辑与原代码一致，不变
```

> **关键差异**：`on_tool_start` 不再需要重置 `_boundary_buffer`、`_inside_think` 等标签状态。仅需关闭正在进行的 thinking 流。

### Step 5：注入 System Prompt

**文件**：`backend/app/agents/graph.py`

新增模块级常量 + `ChatWorkflow` 实例属性：

```python
THINK_SYSTEM_PROMPT = """你是一个内部推理引擎。请逐步分析用户的问题：
1. 理解用户意图
2. 确定需要什么信息
3. 调用工具搜索/获取数据
4. 对获取的数据进行分析和筛选

注意：你只需要分析和推理，不需要给出最终回复。不要对用户说话。"""

SPEAK_SYSTEM_PROMPT = """你是一个友好的二次元助手。基于前面的分析结果，
用自然、亲切的语言回答用户的问题。不要再调用工具。"""
```

在 `stream_chat` 中，将用户配置的 `prompt_config`（persona/tone/rules）**合并到 `self._speak_prompt`**（而非原 system prompt），think 节点始终使用固定的 `THINK_SYSTEM_PROMPT`。这确保了：
- 用户的角色设定只影响最终呈现给用户的回复
- 推理过程不受 persona 干扰，保持客观

### Step 6：`agent.py` 适配 — 传递 prompt_config 到 workflow

**文件**：`backend/app/api/v1/agent.py`

原来 prompt_config 构建的 system_message 直接放入 `formatted_messages`。变更后：
- 不再将 prompt_config 作为 system message 塞入消息列表
- 改为传递给 `ChatWorkflow` 或 `stream_chat`（如新增参数 `speak_prompt: Optional[str] = None`）

```python
# agent.py stream_generator 中
speak_prompt = None
if request.prompt_config:
    speak_prompt = (
        f"[角色设定]\n{request.prompt_config.persona}\n\n"
        f"[语气风格]\n{request.prompt_config.tone}\n\n"
        f"[行为准则]\n{request.prompt_config.rules}"
    )

async for chunk_data in workflow.stream_chat(
    model=request.model,
    messages=formatted_messages,
    temperature=request.temperature,
    thread_id=thread_id,
    speak_prompt=speak_prompt,       # ← 新增
):
```

### Step 7：`schemas/agent.py` — 新增 `reasoning_trace` 事件类型

**文件**：`backend/app/schemas/agent.py`

在 `StreamEventType` 枚举中新增一条事件类型，用于在 think 阶段结束时将完整推理文本推送给前端：

```python
class StreamEventType(StrEnum):
    # ... 现有类型不变 ...
    REASONING_TRACE = "reasoning_trace"    # ← 新增：think 完成时推送完整推理
```

### Step 8：`reasoning_trace` SSE 推送 + API 持久化读取

**文件**：`backend/app/agents/graph.py` + `backend/app/api/v1/agent.py`

#### 8a — 流式结束时推送完整推理

在 `stream_chat` 的 `on_chat_model_end` 中（节点为 think 时），推送一次 `reasoning_trace` 事件：

```python
elif kind == "on_chat_model_end":
    if node_name == "think":
        if _thinking_active:
            yield _emit("thinking_end")
            _thinking_active = False
        # 推送完整推理文本，供前端 "查看推理过程" 面板展示
        yield _emit("reasoning_trace", content=state_snapshot.get("reasoning_trace", ""))
    elif node_name == "speak" and _message_started:
        yield _emit("message_end")
        _message_started = False
```

> 注意：`astream_events` v2 的 `on_chat_model_end` 事件中不包含 state。需要在 `on_chain_end` 事件（带 `langgraph_node` metadata）中获取 state，或通过在 `_think_node` 内部 emit。推荐方案：在 `_think_node` 返回值后，`stream_chat` 监听 `on_chain_end` 事件，从 event 的 output 中提取 `reasoning_trace`。

实际上更简洁的做法——直接在 `stream_chat` 的事件循环中维护一个 `_latest_reasoning` 变量，在 `on_chat_model_stream` 的 think 分支中累积：

```python
_last_reasoning: str = ""

if node_name == "think":
    if not _thinking_active:
        _thinking_active = True
        _last_reasoning = ""
        yield _emit("thinking_start")
    _last_reasoning += delta
    yield _emit("thinking_chunk", content=delta)
```

然后在 `on_chat_model_end`（think 节点）时推送：

```python
elif kind == "on_chat_model_end":
    if node_name == "think":
        if _thinking_active:
            yield _emit("thinking_end")
            _thinking_active = False
        if _last_reasoning:
            yield _emit("reasoning_trace", content=_last_reasoning)
```

#### 8b — API 端点暴露历史推理

新增 API，供前端在加载历史对话时获取推理过程：

**文件**：`backend/app/api/v1/agent.py`

```python
@router.get("/chat/reasoning/{thread_id}")
async def get_chat_reasoning(
    thread_id: str,
    x_api_key: Optional[str] = Header(None, alias="X-Api-Key"),
    x_base_url: Optional[str] = Header(None, alias="X-Provider-Endpoint"),
    user: UserRead = Depends(get_current_user),
):
    """获取指定对话线程的最新推理过程（reasoning_trace）"""
    api_key = x_api_key or os.getenv("OPENAI_API_KEY") or ""
    base_url = x_base_url or "https://api.openai.com/v1"

    workflow = ChatWorkflow(api_key=api_key, base_url=base_url)
    await workflow._ensure_checkpointer()
    config = {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}}
    cp = await workflow.checkpointer.aget_tuple(config)

    if not cp:
        raise HTTPException(status_code=404, detail="Thread not found")

    channel_values = cp.checkpoint.get("channel_values", {})
    reasoning = channel_values.get("reasoning_trace", "")

    return {"thread_id": thread_id, "reasoning_trace": reasoning}
```

### Step 9：LangGraph `interrupt()` 思考中断

**文件**：`backend/app/agents/graph.py`

在 think → speak 之间插入 LangGraph 原生 `interrupt()`，允许人工审核推理结果后再继续生成回复。

#### 9a — 图拓扑变更

```
think ──[无工具调用]──→ interrupt_check → speak
                              │
                              └── 暂停，等待前端 approve/continue
```

#### 9b — 实现

```python
from langgraph.types import interrupt

async def _interrupt_check(self, state: CodingAgentState):
    """在 think → speak 之间插入人工审核断点"""
    last_msg = state["messages"][-1]
    reasoning = state.get("reasoning_trace", "")

    # interrupt() 会暂停图执行，返回前端传入的 decision
    decision = interrupt({
        "question": "请审核推理结果",
        "reasoning": reasoning[:500],  # 截断展示
        "tool_calls": [
            {"name": tc["name"], "args": tc.get("args", {})}
            for tc in getattr(last_msg, "tool_calls", []) or []
        ] if hasattr(last_msg, "tool_calls") else [],
    })

    if decision == "reject":
        return {"messages": [{"role": "system",
                "content": "用户拒绝了此推理，请重新思考"}]}
    # decision == "approve" → 继续执行 speak 节点
    return {}
```

#### 9c — `_compile_graph` 更新

```python
def _compile_graph(self, enable_interrupt: bool = False):
    workflow = StateGraph(CodingAgentState)
    workflow.add_node("think", self._think_node)
    workflow.add_node("speak", self._speak_node)
    workflow.add_node("tools", ToolNode(self._get_tools()))

    workflow.add_edge(START, "think")
    workflow.add_conditional_edges("think", self._think_condition, {
        "tools": "tools",
        "speak": "speak",
    })
    workflow.add_edge("tools", "think")

    if enable_interrupt:
        workflow.add_node("interrupt_check", self._interrupt_check)
        # 重新路由 think → interrupt_check → speak
        # 注意：_think_condition 中返回 "speak" 改为返回 "interrupt_check"
        ...

    workflow.add_edge("speak", END)
    return workflow.compile(
        checkpointer=self.checkpointer,
        store=self._store,
        interrupt_before=["interrupt_check"] if enable_interrupt else None,
    )
```

> **实际推荐**：使用 `interrupt_before=["speak"]` 更简洁，无需新增 `interrupt_check` 节点。LangGraph 在 `speak` 执行前自动暂停，前端调用 `Command(resume=...)` 恢复。

#### 9d — 前端交互

在 `agent.py` 中新增恢复端点：

```python
@router.post("/chat/resume")
async def resume_chat(
    request: ChatRequest,
    decision: str = "approve",  # "approve" | "reject"
    ...
):
    workflow = ChatWorkflow(...)
    await workflow._ensure_checkpointer()
    config = {"configurable": {"thread_id": request.thread_id}}

    # 恢复被 interrupt 暂停的图
    async for chunk_data in workflow.app.astream(
        Command(resume={"decision": decision}),
        config=config,
        stream_mode="messages",
    ):
        ...
```

---

## 4. 文件变更清单

| 文件 | 操作 | 变更内容 |
|------|------|---------|
| `backend/app/agents/graph.py` | **重写** | 拆分 `_call_model` → `_think_node` + `_speak_node`；重写 `_compile_graph`（含 interrupt_before）；重写 `stream_chat` 事件分流（含 reasoning_trace 推送）；移除 `_StreamPhase` / `_detect_think_boundary` / 标签解析；State 加 `reasoning_trace`；新增 `_interrupt_check` |
| `backend/app/api/v1/agent.py` | **扩展** | prompt_config 改为 `speak_prompt` 参数；新增 `GET /chat/reasoning/{id}`；新增 `POST /chat/resume` |
| `backend/app/schemas/agent.py` | **微调** | `StreamEventType` 新增 `REASONING_TRACE` |
| `backend/app/agents/README.md` | **更新** | 同步文档描述新拓扑、事件流、中断机制 |

---

## 5. 测试策略

> 遵循**后端镜像原则**：测试文件放置于 `tests/agents/` 下，与被测源文件路径镜像。

### 5.1 测试文件

| 测试文件 | 被测对象 | 核心验证点 |
|---------|---------|-----------|
| `tests/agents/test_graph_dual_node.py` | `_compile_graph` 拓扑 | think→speak 路由、tools→think 回环 |
| `tests/agents/test_graph_dual_node.py` | `_think_condition` | 有 tool_calls 返回 "tools"，无则返回 "speak" |
| `tests/agents/test_graph_dual_node.py` | `stream_chat` 事件流 | `langgraph_node="think"` → `thinking_*` 事件；`langgraph_node="speak"` → `message_*` 事件 |
| `tests/agents/test_graph_dual_node.py` | `_speak_node` 无工具调用 | 验证 speak 节点 uses `llm` not `llm_with_tools`，不会产生 tool_call |

### 5.2 关键测试用例

```python
# ──── 路由逻辑 ────

# test_think_condition_routes_to_speak_when_no_tool_calls
# Arrange: state with last ai message having no tool_calls
# Act: _think_condition(state)
# Assert: returns "speak"

# test_think_condition_routes_to_tools_when_tool_calls_present
# Arrange: state with last ai message having tool_calls
# Act: _think_condition(state)
# Assert: returns "tools"

# ──── 流式事件 ────

# test_stream_chat_emits_thinking_events_for_think_node
# Arrange: mock LLM that outputs "推理内容" on think node
# Act: collect events from stream_chat()
# Assert: thinking_start → thinking_chunk("推理内容") → thinking_end in order

# test_stream_chat_emits_message_events_for_speak_node
# Arrange: mock LLM that outputs "最终回复" on speak node
# Act: collect events from stream_chat()
# Assert: message_start → message_chunk("最终回复") → message_end in order

# test_speak_node_does_not_bind_tools
# Arrange: mock state with messages, _speak_node uses self.llm (no bind_tools)
# Act: response = await _speak_node(state)
# Assert: response["messages"][0] has no tool_calls

# test_stream_chat_emits_reasoning_trace_after_think_end
# Arrange: mock LLM that outputs "分析: 用户想要搜索2023年动画" on think node
# Act: collect events from stream_chat()
# Assert: after thinking_end, exactly one reasoning_trace event with content containing "分析:"

# ──── reasoning_trace API ────

# test_get_reasoning_returns_trace_for_existing_thread
# Arrange: thread with saved reasoning_trace="分析内容"
# Act: GET /chat/reasoning/{thread_id}
# Assert: 200, {"thread_id": "...", "reasoning_trace": "分析内容"}

# test_get_reasoning_returns_404_for_nonexistent_thread
# Act: GET /chat/reasoning/ghost-thread
# Assert: 404

# test_get_reasoning_returns_empty_string_when_no_trace
# Arrange: thread checkpoint without reasoning_trace field (old data)
# Act: GET /chat/reasoning/{thread_id}
# Assert: 200, {"reasoning_trace": ""}

# ──── interrupt 思考中断 ────

# test_interrupt_pauses_before_speak_when_enabled
# Arrange: compiled graph with interrupt_before=["speak"]
# Act: stream until interrupt event
# Assert: execution halts with Interrupt event, send Command(resume=...) to continue

# test_resume_with_approve_proceeds_to_speak
# Arrange: interrupted at think→speak boundary
# Act: Command(resume={"decision": "approve"})
# Assert: speak node executes, message events emitted

# test_resume_with_reject_re_enters_think
# Arrange: interrupted at think→speak boundary
# Act: Command(resume={"decision": "reject"})
# Assert: think node re-executes with rejection feedback message
```

### 5.3 运行命令

```bash
cd backend
uv run pytest tests/agents/test_graph_dual_node.py -v
```

---

## 6. 兼容性分析

### 6.1 前端（最小改动）
- SSE 事件类型 `thinking_start/chunk/end`、`message_start/chunk/end`、`tool_call_start/end`、`progress`、`error` **全部不变**
- **新增** `reasoning_trace` 事件类型 — 前端需新增对该事件的监听，将内容填充到 "查看推理过程" 展开面板
- `POST /chat/resume` 端点 — 仅在启用 interrupt 模式时需要前端配合发送 resume 请求

### 6.2 持久化（零改动）
- `CodingAgentState` 仅新增 `reasoning_trace` 字段（有默认值 `""`），向后兼容旧 checkpoint
- `AsyncSqliteSaver` 不变

### 6.3 现有 API（微调向后兼容）
- `/chat` POST 请求体不变（`prompt_config` 仍为可选）
- `prompt_config` 行为变化：原来作为 system message 注入；现在作为 `speak_prompt` 传给 speak 节点。对用户来说效果一致
- `/chat/history`、`/chat/threads`、`DELETE /chat/history/{id}` 不变

---

## 7. 风险与缓解

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| speak 节点额外 LLM 调用增加延迟 | 用户感知回复变慢 | speak 节点仅做 "翻译成自然语言"，可考虑用更便宜/更快的模型（方案内已预留 `speak_model` 参数扩展点） |
| think→speak 推理链断裂（speak 忽略 think 的推理） | 回复质量下降 | speak 的 system prompt 明示 "基于前面的分析结果回答"；think 的输出作为 messages 的一部分传给 speak |
| 旧 checkpoint 中无 `reasoning_trace` 字段 | 加载旧对话时 KeyError | TypedDict 定义中设置默认值为 `""`；`_think_node` 每次覆盖 |
| think 节点无限循环（一直调用工具不停止） | 对话卡死 | `max_tool_calls` 计数器限制（后续扩展点 #2）；LLM 自带 stop 条件 |
| interrupt 断点导致对话挂起忘记恢复 | 用户离开后 checkpoint 长期占用 | `interrupt` 有超时机制（LangGraph 内置）；可在前端加 "继续/放弃" 按钮超时自动 approve |
| `reasoning_trace` 包含敏感信息暴露给前端 | 推理中可能引用用户数据 | think 的 system prompt 中声明 "不要在推理中包含用户敏感数据"；前端面板默认折叠 |

---

## 8. 后续扩展点

1. **`speak_model` 参数**：允许 speak 节点使用不同于 think 的模型（如 think 用 deepseek-r1，speak 用 gpt-4o-mini），显著降低延迟与成本
2. **`max_tool_calls` 硬限制**：在 `_think_condition` 中计数工具调用次数，超过阈值强制路由到 speak，防止无限循环
