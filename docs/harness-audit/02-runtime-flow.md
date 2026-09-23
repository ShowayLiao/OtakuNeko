# 当前真实运行流程

以下流程以源码为准；README 的架构描述只作为背景，不作为事实来源。

## 正常回答

```text
Browser useChatStreaming
  → POST /api/v1/chat (BYOK/API endpoint/token/thread_id)
  → Next route 原样转发允许的 headers/body
  → FastAPI chat_endpoint
  → resolve optional user + owner-scoped thread
  → stream_generator
      ├─ 立即发 thinking_start
      ├─ 创建 ChatWorkflow，并打开 data/checkpoints.db 的 AsyncSqliteSaver
      ├─ 已认证用户注入 SQL Memory + LLMFactExtractor
      ├─ 读取用户收藏，作为 metadata.collections
      ├─ 创建静态 AgentRegistry/AgentRouter/FeatureFlagRoutingAdapter
      ├─ 创建 OpenAIModelGateway + SqlTraceStore
      ├─ 创建 AgentTask（没有 task_id）
      └─ AgentRuntime.stream
           → FeatureFlagRoutingAdapter.stream
              → fallback LangGraphAdapter.stream
                 → ChatWorkflow.stream_chat
                    → think(LLM + tools) → speak(LLM) → SSE chunks
  → stream 结束后执行 extract_and_store_facts
  → close workflow/checkpoint connection
```

证据：前端请求参数和 AbortSignal（`frontend/src/hooks/useChatStreaming.ts:325-354`; `frontend/src/lib/fetcher.ts:75-135`）；后端组装顺序（`backend/app/api/v1/agent.py:121-219`）；Graph 节点和流事件（`backend/app/agents/graph.py:90-108,290-474`）。

注意：`thinking_start` 在 workflow/model 初始化前发送，因此客户端看到“开始运行”不等于 Run 已经持久化或已被 provider 接受（`backend/app/api/v1/agent.py:121-134`）。

## 单次 Tool Calling

1. `think` 节点给模型绑定静态工具；模型返回 tool call，条件边转到 `tools`（`backend/app/agents/graph.py:152-178,110-114,195-231`）。
2. `ToolNode(self._get_tools())` 执行工具；工具来自 `ALL_TOOLS`，或由 `ToolRegistry.get_runtime_tools()` 附加 MCP 工具（`backend/app/agents/graph.py:44-64,90-108`; `backend/app/agents/registry.py:20-55`）。
3. graph 读取 Tool 输出，把 `raw_output.content` 或原始 dict/list/string 直接放入 `tool_call_end.output`；只根据顶层 `success` 字段判断错误（`backend/app/agents/graph.py:384-468`）。
4. LangGraph 把 tool message 回送 `think`，模型继续决定是否回答；适配层把 Tool 事件转为 SSE（`backend/app/agents/langgraph_adapter.py:1-220`; `backend/app/api/v1/agent.py:220-231`）。

当前静态工具的输出没有经过统一 `InvocationResult`/字段级 redaction；前端也会 `JSON.stringify` 其输入和输出用于展示（`frontend/src/hooks/useChatStreaming.ts:62-70,444-498`）。

## 多次 Tool Calling

```text
think --(tool call)--> tools --(tool result)--> think
  --(another tool call)--> tools --...--> think --(no tool call)--> speak
```

循环上限不是独立的 Run budget，而是 LangGraph `recursion_limit=24`（`backend/app/agents/graph.py:20,242-247`）。`tool_count` 只用于流展示/进度事件，不作为拒绝条件（`backend/app/agents/graph.py:249-288,465-468`）。

## Tool 失败

工具 decorator 会记录参数和异常，并返回包含 `success=False`、原始异常字符串的 dict（`backend/app/agents/tools/base.py:20-58`）。Graph 层又用顶层 `success` 字段标记 `status=error`，但异常本身通常仍作为 `output` 送入客户端/模型（`backend/app/agents/graph.py:445-463`）。

更重要的是，Graph 的最外层 `except Exception` 把执行异常转换成一个 `type=error` chunk 后结束 generator，而不是重新抛给 `AgentRuntime`（`backend/app/agents/graph.py:470-477`）。因此在某些图失败情况下，Runtime 可能只看到正常结束的 adapter stream；是否会把该次 Run 记为 completed 取决于 adapter 是否产生可识别的结果（`backend/app/harness/runtime.py:181-336`; `backend/app/agents/langgraph_adapter.py`）。这需要集成测试确认，审计将其列为 G-P1-11，而不是断言所有失败都被记成成功。

## SSE 断开

当前前端使用 `AbortController` 或 reader timeout；没有 `Last-Event-ID`、Run 查询或序列补拉。reader 结束后直接调用 `onComplete`，事件解析器也只保留内存 buffer（`frontend/src/lib/fetcher.ts:46-73,147-177,277-290`）。后端 SSE 只在发送 chunk 时附 `stream_sequence`，没有服务端 Event Store 或断线恢复 API（`backend/app/api/v1/agent.py:220-231`; `backend/app/trace/sql_store.py:1-220`）。

因此当前真实状态是：

```text
客户端断开/取消
  → fetch signal/reader 终止（前端显示本地 completed 或 error）
  → 后端是否收到取消、下游 LLM/Tool 是否停止：未由端到端测试确认
  → 没有交互 Run 状态可查询，也没有从 sequence 续流
```

局部 Runtime 测试覆盖了 adapter 抛出 `CancelledError` 时的 trace/checkpoint 状态，但聊天主路径没有把该 checkpoint store 传给 Runtime（`backend/tests/trace/test_agent_instrumentation.py:196-218`; `backend/app/api/v1/agent.py:176-219`）。

## 用户取消

前端 `stopGeneration` 会 abort 当前请求并把本地 pending process 改为 `success`、消息状态写为 `completed`（`frontend/src/hooks/useChatStreaming.ts:285-323`）。这只是 UI 状态，不是服务端 Run 的 `cancelled` 状态。服务端 `AgentRuntime.stream` 能捕获 `BaseException` 并把 trace 标记取消/失败，但前提是取消异常穿过 adapter 到达 Runtime（`backend/app/harness/runtime.py:321-336`）；是否在 FastAPI generator 和 provider 下游稳定传播，当前未确认。

## 服务重启

业务数据引擎可使用 SQLite 或 PostgreSQL，启动生命周期调用 `init_db()`/`create_all`；Redis 即使可连通也使用内存 cache（`backend/app/main.py:35-119`; `backend/app/db/database.py:37-48`）。LangGraph checkpoint 固定为 `data/checkpoints.db`，每个 chat request 自己打开并关闭连接（`backend/app/agents/graph.py:44-88`）。Docker compose 只为 PostgreSQL、Redis、qBittorrent 挂载卷，没有为 backend 挂载 `data/`（`docker-compose.yml:15-36,40-70,73-125`）。

所以：本地直接运行时，checkpoint 文件可能跨进程重启保留；Docker 重建/替换 backend 容器时，仓库配置没有证据证明它会保留。交互 Run、SSE 事件、Runtime state 永远没有独立持久化。该结论是配置级事实；真实发布卷挂载仍属未确认。

## 高风险动作审批

- ChatWorkflow 可以在 `interrupt_before=["speak"]` 编译图，并由 `resume_chat` 接受 `decision=approve/reject` 后发 `Command(resume=decision)`（`backend/app/agents/graph.py:90-108`; `backend/app/api/v1/agent.py:333-382`）。
- 这个 interrupt 位于 `speak` 前，不是 qBittorrent、收藏或日程写操作的统一审批点；qBittorrent 走独立 HTTP 路由且没有认证依赖（`backend/app/api/v1/rss.py:28-93`）。
- Proactive task 创建/更新有 `confirm_side_effects` 和 `ProactivePolicy` 检查，但它只适用于 scheduler 任务定义（`backend/app/api/v1/proactive.py:19-84`; `backend/app/harness/scheduler/execution.py:57-80`）。

结论：**聊天主路径的高风险 Tool 审批未实现；Proactive 和 LangGraph interrupt 是两套局部机制。**
