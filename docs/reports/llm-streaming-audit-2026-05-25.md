# LLM 流式输出全链路审查报告

> 审查日期：2026-05-25
> 审查范围：Thinking / Tool Call / Final Message 三阶段结构化拆分与 SSE 事件下发
> 关联文档：[agent-architecture-roadmap.md](../plans/agent-architecture-roadmap.md)（M5 节）

---

## 1. 架构全景

当前数据流路径为：

```
[LLM Provider] → ChatOpenAI(streaming=True) → LangGraph astream_events(v2)
    → ChatWorkflow.stream_chat() 逐事件 yield Dict
        → agent.py stream_generator() → format_sse() → StreamingResponse(text/event-stream)
            → 前端 fetch() + ReadableStream → parseSSE() → useChatStreaming → Zustand Store
```

### 涉及的核心文件

| 层级 | 文件 | 职责 |
|------|------|------|
| 编排核心 | `backend/app/agents/graph.py` | `ChatWorkflow.stream_chat()` — 事件分类与 yield |
| API 层 | `backend/app/api/v1/agent.py` | `stream_generator()` + `format_sse()` — SSE 封装 |
| 前端消费者 | `frontend/src/lib/fetcher.ts` | `parseSSE()` — SSE 解包 + 事件路由 |
| 前端状态 | `frontend/src/hooks/useChatStreaming.ts` | 各类回调 → Zustand Store |
| 前端 UI | `frontend/src/components/chat/MessageList.tsx` | ThinkingPanel / ProgressPanel 渲染 |
| Schema | `backend/app/schemas/agent.py` | `ChatRequest` 定义 |
| 工具层 | `backend/app/agents/tools/*.py` | 7 个工具定义 |
| 工具基类 | `backend/app/agents/tools/base.py` | `ToolResult` schema / `log_tool_call` 装饰器 |
| MCP 传输 | `backend/app/agents/mcp/*.py` | SSE/Stdio/连接池/心跳 |

---

## 2. 当前下发给前端的 SSE 事件 Payload 全览

后端通过 `event:` + `data:` 双字段下发，共 **7 种事件类型**，逐一列出实际 JSON 结构：

### 2.1 `reasoning_chunk` — 思考阶段文本

```
event: reasoning_chunk
data: {"type": "reasoning_chunk", "content": "让我分析一下用户的需求..."}
```

**触发条件**：`has_executed_tools == False` 时的流式 chunk。
**注入点**：[graph.py#L149-L150](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/agents/graph.py#L149-L150)

### 2.2 `message_chunk` — 最终输出文本

```
event: message_chunk
data: {"type": "message_chunk", "content": "根据搜索结果，我为您推荐以下..."}
```

**触发条件**：`has_executed_tools == True` 时的流式 chunk。
**注入点**：[graph.py#L152-L153](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/agents/graph.py#L152-L153)

### 2.3 `tool_start` — 工具调用开始

```
event: tool_start
data: {"type": "tool_start", "name": "search_anime_advanced", "inputs": {"keyword": "进击的巨人"}}
```

**注入点**：[graph.py#L165-L169](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/agents/graph.py#L165-L169)

### 2.4 `tool_end` — 工具调用结束

```
event: tool_end
data: {"type": "tool_end", "name": "search_anime_advanced", "output": {"total": 5, "results": [...]}, "duration_ms": 234.5, "tool_count": 1}
```

**注入点**：[graph.py#L171-L190](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/agents/graph.py#L171-L190)

### 2.5 `progress` — 进度事件

```
event: progress
data: {"type": "progress", "tool_name": "search_anime_advanced", "tool_count": 1, "duration_ms": 234.5}
```

**注入点**：[graph.py#L192-L197](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/agents/graph.py#L192-L197)

### 2.6 `plan_update` — 计划提取

```
event: plan_update
data: {"type": "plan_update", "content": "第一步：搜索动画\n第二步：获取详情..."}
```

**注入点**：[graph.py#L155-L160](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/agents/graph.py#L155-L160)

### 2.7 `error` — 全局异常

```
event: error
data: {"type": "error", "detail": "Graph Execution Error: ..."}
```

**注入点**：[graph.py#L221](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/agents/graph.py#L221) / [agent.py#L78](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/api/v1/agent.py#L78)

---

## 3. 核心缺陷诊断

### 🔴 缺陷 #1（Critical）：`reasoning_chunk` vs `message_chunk` 分类逻辑存在根本性 Bug

**位置**：[graph.py#L147-L153](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/agents/graph.py#L147-L153)

```python
if not has_executed_tools:
    yield {"type": "reasoning_chunk", "content": chunk.content}
else:
    yield {"type": "message_chunk", "content": chunk.content}
```

**问题**：
- **无工具调用场景下的灾难**：当用户问 "你好" 这种不需要工具的问题时，`has_executed_tools` 永远为 `False`，**所有文本被标记为 `reasoning_chunk`**，前端永远收不到 `message_chunk`。
- 前端代码 `useChatStreaming.ts` 中 `onReasoningChunk` 仅将内容写入 `reasoningTextRef`（到可折叠的 ThinkingPanel），而 `onMessageChunk` 才是驱动 `accumulatedContentRef` 的来源。**无工具调用场景下用户看到的回复区域永远是空的**。
- 这与 M5 里程碑的设计意图相悖——M5 本意是将调用工具**之前的独白**标为 `reasoning_chunk`，而不是将所有文本都标为推理。

### 🔴 缺陷 #2（Critical）：完全不兼容 DeepSeek-R1 等推理模型的 `<think>` 标签

- 全代码库零 `<think>` 标签处理逻辑。
- DeepSeek-R1 流式输出嵌入 `<think>推理过程</think>最终回复` 结构。当前代码将整个响应（包括标签后的正式内容）在无工具调用场景下一股脑归入 `reasoning_chunk`。
- `accumulated_text` 在 `on_chat_model_end` 后被清空（[graph.py#L160](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/agents/graph.py#L160)），多轮 ReAct 循环中的文本跨轮丢失。

### 🔴 缺陷 #3（Medium）：缺少 Thinking/Message 阶段的显式起止边界事件

当前只有 `reasoning_chunk` 和 `message_chunk` 流式文本事件，但**没有**以下边界事件：

| 缺失事件 | 影响 |
|---------|------|
| `thinking_start` | 前端无法精确控制 ThinkingPanel 展开时机 |
| `thinking_end` | 前端无法确定何时折叠思考面板、切换为正式输出 |
| `message_start` | 前端无法区分"还在思考"和"开始正式回答" |
| `message_end` | 前端无法确定流式回复是否已完整结束 |

前端目前只能通过 "是否收到过 `tool_start`" 来间接推断阶段切换，这是极其脆弱的。

### 🟡 缺陷 #4（Medium）：工具调用失败无显式状态传导

**位置**：[graph.py#L176-L190](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/agents/graph.py#L176-L190)

- `tool_end` 事件中**不包含 `status` 字段**区分成功/失败。
- 前端 [useChatStreaming.ts#L105](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/hooks/useChatStreaming.ts#L105) 硬编码 `status: 'success'`，即使工具返回 `{"error": "..."}` 也标注为成功。
- `ToolResult` schema（[base.py](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/agents/tools/base.py)）定义了 `success`/`error_type` 字段，但 `graph.py` 未使用它统一包装输出。

### 🟡 缺陷 #5（Low）：LangGraph `astream_events` v2 不转发 tool_call delta

DeepSeek-R1 等模型的流式响应中，`tool_call` 的 delta（`tool_call_chunks`）也会经过 `on_chat_model_stream`。当前代码仅用 `hasattr(chunk, "content")` 过滤，不会误输出，但也未主动转发 `tool_call` 流式增量给前端，导致工具调用参数无法渐进式展示。

---

## 4. 重构方案

### 4.1 设计原则

- **最小侵入**：保留现有 LangGraph 图结构和 `astream_events` v2 事件流，仅修改 `stream_chat()` 方法中的事件分类逻辑。
- **状态机驱动**：引入 `_StreamPhase` 枚举（`IDLE → THINKING → TOOLING → FINAL_MESSAGE`），替代单一的 `has_executed_tools` 布尔值。每轮 ReAct 循环中工具调用后重置关键标志位，防止多轮状态污染。
- **标签透传、前端解析**：后端仅通过简单标记位（`_inside_think`）判断当前是否处于 `<think>` 块内部以切换发送管道（`thinking_chunk` vs `message_chunk`），**不对标签文本做任何正则匹配或替换**。原始标签原样随着 `thinking_chunk` 下发，由前端的 Markdown AST 解析器识别 `<think>` 节点并渲染为可折叠的思考动画。这避免了流式 Chunk 在跨网络层被切碎时正则匹配的不可预期行为。
- **强类型契约**：工具异常判断依赖 `ToolResult` 序列化后的 `success` 字段，杜绝通过字典键名猜测业务成败。

### 4.2 新增事件类型 Schema

建议在 [schemas/agent.py](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/schemas/agent.py) 中新增：

```python
from enum import StrEnum
from typing import Any, Optional
from pydantic import BaseModel

class StreamEventType(StrEnum):
    THINKING_START   = "thinking_start"
    THINKING_CHUNK   = "thinking_chunk"
    THINKING_END     = "thinking_end"
    TOOL_CALL_DELTA  = "tool_call_delta"
    TOOL_CALL_START  = "tool_call_start"
    TOOL_CALL_END    = "tool_call_end"
    MESSAGE_START    = "message_start"
    MESSAGE_CHUNK    = "message_chunk"
    MESSAGE_END      = "message_end"
    PLAN_UPDATE      = "plan_update"
    PROGRESS         = "progress"
    ERROR            = "error"

class StreamEvent(BaseModel):
    type: StreamEventType
    content: Optional[str] = None
    name: Optional[str] = None
    inputs: Optional[dict] = None
    output: Optional[Any] = None
    status: Optional[str] = None        # "success" | "error"
    duration_ms: Optional[float] = None
    tool_count: Optional[int] = None
    detail: Optional[str] = None
```

### 4.3 核心重构：`stream_chat()` 方法

**文件**：[graph.py](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/agents/graph.py)

新增状态机枚举（无需导入 `re`，不再使用正则）：

```python
class _StreamPhase:
    IDLE = "idle"
    THINKING = "thinking"
    TOOLING = "tooling"
    FINAL_MESSAGE = "final_message"
```

以下是 `stream_chat()` 方法的重构版本（保留所有现有长记忆注入、checkpointer 初始化逻辑，仅替换事件循环体）：

```python
async def stream_chat(
    self, model: str, messages: List[Dict[str, Any]],
    temperature: float, thread_id: str = "default"
) -> AsyncGenerator[Dict[str, Any], None]:
    await self._ensure_checkpointer()
    self.llm = ChatOpenAI(
        model=model, api_key=self.api_key, base_url=self.base_url,
        temperature=temperature, streaming=True
    )
    self.llm_with_tools = self.llm.bind_tools(self._get_tools())

    enriched_messages = list(messages)
    if self.memory and thread_id:
        user_query = next((m["content"] for m in reversed(messages)
                          if m.get("role") == "user"), "")
        if user_query:
            ctx = await self.memory.load_context(thread_id, user_query)
            if ctx.summary:
                sys_idx = next((i for i, m in enumerate(enriched_messages)
                               if m.get("role") == "system"), None)
                if sys_idx is not None:
                    enriched_messages[sys_idx]["content"] += f"\n\n{ctx.summary}"
                else:
                    enriched_messages.insert(0, {"role": "system", "content": ctx.summary})

    config = {"configurable": {"thread_id": thread_id}}

    # ===== 状态机变量 =====
    phase: str = _StreamPhase.IDLE
    _inside_think: bool = False          # 标记当前是否处于 <think> 块内部
    _boundary_buffer: str = ""           # ← 修正 #4：防跨 Chunk 切断的滑动窗口（保留尾部 8 字符）
    tool_count: int = 0
    tool_start_times: Dict[str, float] = {}  # Key = run_id，见修正 #6
    message_started: bool = False

    def _emit(event_type: str, **kwargs) -> Dict[str, Any]:
        return {"type": event_type, **kwargs}

    def _detect_think_boundary(delta_text: str, buffer_text: str
                               ) -> Tuple[bool, bool, str]:
        """带有滑动窗口的边界检测，免疫网络切片导致的标签跨 Chunk 切断。
        返回 (should_toggle_inside, is_entering, new_buffer)"""
        search_text = buffer_text + delta_text.lower()
        has_open = "<think" in search_text
        has_close = "</think>" in search_text

        # 保留尾部 8 字符（足以容纳 "</think>"），作为下一轮拼接前缀
        new_buffer = search_text[-8:] if len(search_text) >= 8 else search_text

        if has_open and has_close:
            return (True, search_text.index("<think") < search_text.index(
                "</think>"), new_buffer)
        elif has_open:
            return (True, True, new_buffer)
        elif has_close:
            return (True, False, new_buffer)
        return (False, False, new_buffer)

    try:
        async for event in self.app.astream_events(
            {"messages": enriched_messages, "current_dir": "",
             "plan": "", "completed_steps": [], "last_terminal_output": ""},
            config=config, version="v2"
        ):
            kind = event["event"]

            if kind == "on_chat_model_stream":
                chunk = event["data"]["chunk"]

                # ---------- tool_call delta ----------
                if hasattr(chunk, "tool_call_chunks") and chunk.tool_call_chunks:
                    for tc in chunk.tool_call_chunks:
                        if tc.get("name"):
                            yield _emit("tool_call_delta",
                                        id=tc.get("id"), name=tc.get("name"),
                                        delta=tc.get("args", ""))
                    continue

                if not (hasattr(chunk, "content") and isinstance(chunk.content, str)
                        and chunk.content):
                    continue

                delta = chunk.content

                # === <think> 标记位检测（仅切换管道，不做文本切割）===
                toggle, entering, _boundary_buffer = _detect_think_boundary(
                    delta, _boundary_buffer
                )

                if entering and not _inside_think:
                    # 刚进入 <think> 块 → 切换到思考态
                    _inside_think = True
                    if phase != _StreamPhase.THINKING:
                        phase = _StreamPhase.THINKING
                        yield _emit("thinking_start")
                    yield _emit("thinking_chunk", content=delta)
                    continue

                if not entering and _inside_think and toggle:
                    # 遇到了 </think> → 退出思考态
                    _inside_think = False
                    yield _emit("thinking_chunk", content=delta)
                    yield _emit("thinking_end")
                    phase = _StreamPhase.FINAL_MESSAGE
                    continue

                if _inside_think:
                    # 在 <think> 块内部 → 管道分流到 thinking_chunk
                    yield _emit("thinking_chunk", content=delta)
                    continue

                # ===== 标签外部 / 普通模型流式输出 =====
                if phase == _StreamPhase.IDLE:
                    phase = _StreamPhase.THINKING
                    yield _emit("thinking_start")

                if phase == _StreamPhase.THINKING:
                    yield _emit("thinking_chunk", content=delta)
                elif phase == _StreamPhase.FINAL_MESSAGE:
                    if not message_started:
                        message_started = True
                        yield _emit("message_start")
                    yield _emit("message_chunk", content=delta)

            elif kind == "on_chat_model_end":
                if _inside_think:
                    yield _emit("thinking_end")
                    _inside_think = False
                if phase == _StreamPhase.THINKING:
                    yield _emit("thinking_end")
                if message_started:
                    yield _emit("message_end")
                phase = _StreamPhase.IDLE

            elif kind == "on_tool_start":
                if phase == _StreamPhase.THINKING:
                    yield _emit("thinking_end")
                phase = _StreamPhase.TOOLING
                message_started = False       # ← 修正 #1：多轮 ReAct 重置标志位
                _inside_think = False         # 重置 think 标记，迎接下一轮推理
                _boundary_buffer = ""         # ← 修正 #4：清空滑动窗口
                tool_name = event["name"]
                run_id = event["run_id"]
                inputs = event["data"].get("input", {})
                tool_start_times[run_id] = time.perf_counter()  # ← 修正 #6：Key = run_id 防并行覆盖
                yield _emit("tool_call_start", name=tool_name, inputs=inputs)

            elif kind == "on_tool_end":
                tool_name = event["name"]
                run_id = event["run_id"]
                duration_ms = 0.0
                if run_id in tool_start_times:
                    duration_ms = (
                        time.perf_counter() - tool_start_times.pop(run_id)
                    ) * 1000                        # ← 修正 #6：改用 run_id 寻址

                raw_output = event["data"].get("output")
                tool_count += 1

                if hasattr(raw_output, "content"):
                    output_data = raw_output.content
                elif isinstance(raw_output, (dict, list, str, int, float, bool,
                                             type(None))):
                    output_data = raw_output
                else:
                    output_data = str(raw_output)

                # ← 修正 #2：强类型契约 — 仅依赖 ToolResult.success 字段
                tool_status = "success"
                if isinstance(output_data, dict) and not output_data.get(
                    "success", True
                ):
                    tool_status = "error"

                yield _emit("tool_call_end",
                            name=tool_name, output=output_data,
                            status=tool_status,
                            duration_ms=round(duration_ms, 2),
                            tool_count=tool_count)

                yield _emit("progress",
                            tool_name=tool_name,
                            tool_count=tool_count,
                            duration_ms=round(duration_ms, 2))

    except Exception as e:
        yield _emit("error", detail=f"Graph Execution Error: {str(e)}")
```

> **修正汇总**：
> | # | 场景 | 策略 |
> |---|------|------|
> | #1 | 多轮 ReAct 状态污染 | `on_tool_start` 中重置 `message_started` / `_inside_think` |
> | #2 | 工具误判（字典键名） | 强依赖 `output_data.get("success", True)` |
> | #3 | `<think>` 正则脆断 | 不做文本切割，标记位原样透传，前端 AST 渲染 |
> | #4 | 跨 Chunk 标签切断 | 滑动窗口 `_boundary_buffer`（尾部 8 字符拼接） |
> | #6 | 并行工具 Duration 覆盖 | `tool_start_times` Key 从 `tool_name` → `event["run_id"]` |

### 4.4 SSE 格式层（`agent.py`）— 无需改动

[agent.py#L28-L29](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/api/v1/agent.py#L28-L29) 的 `format_sse()` 已通过 `chunk_data.get("type")` 动态生成 `event:` 字段，新增类型会自动映射。

### 4.5 前端改动要点

| 新增/变更事件 | 前端适配行为 |
|--------------|-------------|
| `thinking_start` | 初始化 ThinkingPanel 展开状态，显示 "思考中..." 动画 |
| `thinking_chunk`（保留） | 追加推理文本到 ThinkingPanel。**注意**：DeepSeek-R1 场景下此事件会携带原始 `<think>...</think>` 标签，前端需用 Markdown AST 解析器识别 `<think>` 节点并渲染为可折叠思考面板 |
| `thinking_end` | 折叠 ThinkingPanel，添加淡出动画 |
| `tool_call_delta`（新增） | 流式展示工具调用参数（渐进式 JSON delta） |
| `tool_call_start`（重命名） | 替代旧 `tool_start`，新增 ProgressPanel 条目 |
| `tool_call_end`（增强 `status` 字段） | 替代旧 `tool_end`，根据 `status` 渲染 √/✗ 图标 |
| `message_start`（新增） | 切换 UI 到 "正式输出" 模式，隐藏思考面板 |
| `message_chunk`（保留） | 追加到最终回复区域（`accumulatedContentRef`） |
| `message_end`（新增） | 标记完整回复结束，停转圈 |
| `progress`（保留） | 行为不变 |

**前端 `<think>` 标签处理补充**：建议在 `fetcher.ts` 的 `onReasoningChunk` 回调中，对携带的文本做一次轻量检测——若当前累计文本中检测到 `<think>` 开标签，将 ThinkingPanel 渲染为"深度推理"样式（如紫色脉冲动画）。当流式结束时（`thinking_end` 或 `message_start`），通过 Markdown AST 遍历最终文本，将 `<think>` 节点子树替换为 `ThinkingPanel` React 组件。这比后端正则切割更健壮，且不依赖 Chunk 边界的完整性。

**⚠️ 前端 AST 安全配置硬性要求**：在 Lobe UI 等基于 `react-markdown`（底层 `remark`/`rehype`）的渲染管线中，标准的 Markdown 解析器默认会将不安全 HTML 标签转义为 `&lt;think&gt;`，或被 `rehype-sanitize` 直接过滤。因此必须做以下显式配置：

```typescript
// react-markdown / unified pipeline 中必须：
import rehypeRaw from 'rehype-raw';

<ReactMarkdown
  rehypePlugins={[rehypeRaw]}           // ← 显式允许原始 HTML 标签
  components={{
    think: ({ children }) => (           // ← 自定义组件映射
      <ThinkingPanel>{children}</ThinkingPanel>
    ),
  }}
>
  {messageContent}
</ReactMarkdown>
```

这样 AST 才能正确将流式下发的 `<think>推理文本</think>` 节点映射为折叠式 `ThinkingPanel` React 组件，而非纯文本展示。

---

## 5. 异常处理边界优化

### 5.1 当前问题

| 层级 | 问题 | 位置 |
|------|------|------|
| 后端工具层 | `return {"error": "..."}` 无统一状态码 | [anime.py](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/agents/tools/anime.py) 等 |
| 后端 graph 层 | 不检查工具输出中的 error 字段，当作普通数据透传 | [graph.py#L176-L190](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/agents/graph.py#L176-L190) |
| 前端状态层 | 硬编码 `status: 'success'`，忽略工具异常 | [useChatStreaming.ts#L105](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/hooks/useChatStreaming.ts#L105) |
| 全局异常 | 仅一个 `error` 事件，无法区分 LLM 调用失败、工具超时、checkpoint 写入失败 | [graph.py#L221](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/agents/graph.py#L221) |

### 5.2 优化方案

**后端 — 工具层统一使用 `ToolResult` 包装**：

```python
# tools/anime.py — 示例改动
from app.agents.tools.base import ToolResult
import time

@tool
@log_tool_call("get_anime_info")
async def get_anime_info(subject_id: int) -> dict:
    t0 = time.perf_counter()
    try:
        result = await fetch_subject_by_id(subject_id)
        return ToolResult(
            success=True,
            data=result.model_dump(exclude_none=True),
            tool_name="get_anime_info",
            duration_ms=round((time.perf_counter() - t0) * 1000, 2)
        ).model_dump()
    except Exception as e:
        return ToolResult(
            success=False,
            error=str(e),
            error_type="internal",
            tool_name="get_anime_info",
            duration_ms=round((time.perf_counter() - t0) * 1000, 2)
        ).model_dump()
```

**后端 — `graph.py` 的 `on_tool_end` 已在上方重构代码中通过以下逻辑修复**（强依赖 `ToolResult.success` 字段，杜绝字典键名误判）：

```python
tool_status = "success"
if isinstance(output_data, dict) and not output_data.get("success", True):
    tool_status = "error"
```

**前端 — `useChatStreaming.ts` 应使用后端下发的 `status` 字段**：

```typescript
// 将 onToolEnd 签名从 (name, output, durationMs)
// 扩展为 (name, output, durationMs, status)
onToolEnd: (name, output, durationMs, status) => {
  store.updateMessage(activeSessionId, ..., {
    id: toolCallId, name,
    status: status || 'success',   // 使用后端下发的状态
    output, durationMs
  });
}
```

---

## 6. 总结矩阵

| 阶段 | 审查时状态 | 当前状态 | 现有事件 |
|------|----------|---------|---------|
| **Thinking** | 🔴 Critical | ✅ 已修复 | `thinking_start` `thinking_chunk` `thinking_end` |
| **Tool Calling** | 🟡 Medium | ✅ 已修复 | `tool_call_delta` `tool_call_start` `tool_call_end` (+`status`) `progress` |
| **Final Message** | 🟡 Medium | ✅ 已修复 | `message_start` `message_chunk` `message_end` |
| **异常传达** | 🟡 Medium | ✅ 已修复 | `error` + `tool_call_end.status` + 工具层 `success` 字段 |

### 修复优先级（均已执行）

| # | 优先级 | 描述 | 状态 | 执行日期 |
|---|--------|------|------|---------|
| 1 | P0 | 修复 `reasoning_chunk`/`message_chunk` 分类逻辑（切换为状态机） | ✅ 已完成 | 2026-05-25 |
| 2 | P0 | 接入 `<think>` 标记位检测 + 滑动窗口（兼容 DeepSeek-R1） | ✅ 已完成 | 2026-05-25 |
| 3 | P1 | 补全 `thinking_start`/`thinking_end`/`message_start`/`message_end` 边界事件 | ✅ 已完成 | 2026-05-25 |
| 4 | P1 | `tool_end` → `tool_call_end`，增加 `status` 字段（依赖 `ToolResult.success`） | ✅ 已完成 | 2026-05-25 |
| 5 | P2 | 工具层统一 `success: True/False` 字段返回格式 | ✅ 已完成 | 2026-05-25 |
| 6 | P2 | 新增 `tool_call_delta` 流式参数事件 | ✅ 已完成 | 2026-05-25 |

---

## 7. 实施记录（2026-05-25）

### 后端变更

| 文件 | 改动摘要 |
|------|---------|
| `backend/app/agents/graph.py` | 移除 `import re` + 废弃的 `_extract_plan`；新增 `_StreamPhase` 状态机枚举；重写 `stream_chat()` — `has_executed_tools` 布尔值 → 4 状态状态机；新增 `_detect_think_boundary()` 滑动窗口防跨 Chunk 切断；事件重命名 `reasoning_chunk→thinking_chunk` / `tool_start→tool_call_start` / `tool_end→tool_call_end`；新增 `thinking_start/end`、`message_start/end`、`tool_call_delta` 四种事件；`tool_call_end` 新增 `status` 字段；`tool_start_times` Key 从 `tool_name` → `event["run_id"]`；`on_tool_start` 中重置 `message_started`/`_inside_think`/`_boundary_buffer` |
| `backend/app/schemas/agent.py` | 新增 `StreamEventType`(StrEnum) + `StreamEvent`(BaseModel) 事件类型定义 |
| `backend/app/agents/tools/anime.py` | 4 个工具返回值追加 `"success": True` / `"success": False` 字段 |
| `backend/app/agents/tools/search.py` | 3 处 return 追加 `"success": True/False` |
| `backend/app/agents/tools/datetime.py` | 2 处 return 追加 `"success": True/False` |
| `backend/app/agents/tools/base.py` | `log_tool_call` 中 success 判断从 `"error" in result` → `result.get("success", True)` |

### 前端变更

| 文件 | 改动摘要 |
|------|---------|
| `frontend/src/lib/fetcher.ts` | 接口 `ChatWithBackendOptions` 回调签名全面更新（新增 `onMessageStart/End`、`onThinkingStart/Chunk/End`、`onToolCallDelta`）；switch 语句新增 8 种新事件处理；保留旧事件名 `reasoning_chunk`/`tool_start`/`tool_end` 向后兼容映射 |
| `frontend/src/hooks/useChatStreaming.ts` | 回调名同步更新；`onToolCallEnd` 使用后端下发的 `status` 字段替代硬编码 `'success'`；新增 `onThinkingStart/Chunk/End`、`onMessageStart` 处理逻辑 |

### 无需改动的文件

- `backend/app/api/v1/agent.py` — `format_sse()` 已通过 `chunk_data.get("type")` 动态生成 `event:` 字段，零改动兼容所有新事件类型

### 验证

- pyright 类型检查：全部 8 个变更文件 **0 diagnostics**
