# 目标架构建议（规划，不代表当前实现）

本文件只给出重构目标和边界，不把目标结构写成当前事实，也不要求采用某个具体框架。参考文档明确把目录视为职责示意，不要求机械照搬（参考文档:1398-1468）。

## 目标原则

1. **一个 Run Coordinator**：创建 Run、检查权限/预算、推进状态、处理取消/重试、持久化事件；模型框架只执行被 Coordinator 调度的 Loop。
2. **一个 Capability Registry**：能力有稳定 name/version/input schema/output schema/risk/side-effect/timeout/retry/idempotency/approval metadata；LangChain、MCP、HTTP 都是 adapter。
3. **可信身份不进模型参数**：公开 schema 不出现 `user_id`/tenant/principal；Coordinator 从 JWT/服务身份建立 `ExecutionContext`，Dispatcher 将 context 注入 Domain Service。
4. **事件先于 UI**：SSE 是 Event Store 的投影；客户端可用 Run ID、sequence、Last-Event-ID 查询/补拉，断开不改变 Run 真值。
5. **业务 Service 在 Harness 外部**：Harness 只编排和约束，qBittorrent、收藏、日程、Bangumi Service 负责资源级业务校验和外部 API 细节（参考文档:1460-1468）。

## 建议逻辑组件

```text
Chat/Task API
   ↓ authenticate + create Run
RunCoordinator
   ├─ RunLifecycle / Cancellation / Budget
   ├─ PolicyEngine(principal, capability, risk, approval)
   ├─ ContextCompiler(Memory + user data + trust labels)
   ├─ ModelGateway → ModelCallResult
   ├─ DecisionParser → Decision(tool / final / handoff)
   ├─ InvocationDispatcher
   │    ├─ CapabilityRegistry → Capability adapter → Domain Service
   │    ├─ MCP adapter (optional)
   │    └─ legacy LangGraph adapter (transition)
   ├─ ResultNormalizer → InvocationResult
   └─ EventWriter → Run/Step/Invocation/Event Store → SSE projection

Domain services / integrations remain below dispatcher and do not import LLM framework.
```

## 建议最小契约

### `ExecutionContext`

```text
principal_id: immutable authenticated subject
tenant_id: optional, server-derived
run_id: immutable
trace_id: immutable
capability_allowlist: server policy
deadline / budget: server policy
approval_context: server state, not model text
```

来源必须是 API auth、scheduler lease 或可信服务调用；不能从 `messages`, tool args, `task.metadata.user_id` 直接信任。当前 MCP 的 `MCPContext.user_id` 注入方式可以作为边界参考（`backend/app/mcp_server/context.py`; `backend/app/mcp_server/__init__.py:320-353`）。

### `Decision`

```text
kind: invoke | final | handoff | pause
capability: canonical name + version
arguments: validated public schema
reason: short user-safe explanation, not chain-of-thought
```

当前 Graph 的 LLM tool call 不必立刻删除，可先由 `LangGraphAdapter` 转为此结构；不可把 provider 原始 tool call 当作已授权 Invocation（`backend/app/agents/graph.py:152-178,384-468`）。

### `Invocation` / `InvocationResult`

```text
invocation_id, run_id, step_id, capability, version
principal_id, input_hash, idempotency_key
status: pending | running | succeeded | failed | cancelled | denied
started_at, finished_at, timeout, retry_count
output: versioned safe data envelope
error: category + retryable + user_message
side_effect: none | read | write | external
```

`CapabilityResult` 和 `AgentResult` 可以作为过渡输入，但必须统一字段和错误语义（`backend/app/capabilities/types.py:10-53`; `backend/app/harness/result.py:1-130`）。

### Event

服务端分配单调 `sequence`，至少包含 `run_id`, `event_id`, `type`, `occurred_at`, `step_id/invocation_id`, `payload_ref`, `safe_payload`。SSE 发送已持久化事件并支持 `Last-Event-ID`，不可由前端生成的消息状态反推成功（当前前端行为：`frontend/src/lib/fetcher.ts:277-290`; `frontend/src/hooks/useChatStreaming.ts:532-548`）。

## 安全与副作用目标

- qBittorrent、Schedule writes、Collection writes 只能进入统一 Dispatcher；REST 也调用同一 policy/side-effect gateway，不能绕过（当前 qBittorrent 绕过证据：`backend/app/api/v1/rss.py:16-105`）。
- 默认 `deny`；高风险能力需要 authenticated principal、显式 allowlist、approval token/状态和 idempotency key。
- qBittorrent upsert 建模为可恢复状态机：`read current → plan → delete old → add new → verify → compensate/mark attention`，并记录外部 resource key。不要把 delete+add 包装成看似原子的普通函数（`backend/app/services/qb_service.py:115-151`）。
- 输出给模型和前端的 Tool result 只允许 schema 中的安全字段；日志使用与 Trace 相同的字段级 redaction（当前两处 raw logging：`backend/app/agents/tools/base.py:20-58`; `backend/app/services/qb_service.py:180-198`）。

## 迁移中的 LangGraph 边界

迁移阶段允许 `ChatWorkflow` 继续执行 `think/tools/speak`，但边界改为：

1. Runtime/Coordinator 创建 Run/Context/Budget。
2. LangGraph adapter 接收不可变 Context 和已编译 Context；它只报告 `model_decision`, `tool_requested`, `tool_result`, `final_output`。
3. Coordinator 在 Dispatcher 前检查 policy、预算、幂等和审批；ToolNode 不直接拥有写能力。
4. adapter 把图异常转为 terminal failure，再由 Coordinator 做唯一状态转移。

这保留了现有图和模型 provider 的投资，同时消除 `AgentRuntime`/Graph 双重控制。图本身不需要被视为标准要求或永久架构。

## 迁移后的存储

最低需要：`run_store`, `event_store`, `checkpoint_store`, `invocation_store`，并与现有 `agent_task_run`/`agent_trace` 明确关系。交互 Run 和 Proactive Run 可以共用契约，但不必第一批合表；先通过相同状态机和 Event schema 建立映射。checkpoint 不能依赖未挂载的容器本地 `data/`（当前证据：`docker-compose.yml:73-125`; `backend/app/agents/graph.py:44-78`）。

## 目标验证门槛

- 安全：未登录 qBittorrent 写请求全拒绝；模型提供伪造 `user_id` 不改变 principal；恶意 Tool output 不改变 policy。
- 运行：一个 Run 有唯一 id；每次 Invocation 有状态、预算和 sequence；断开后 Run 可查询/补拉；取消能到达 provider/tool。
- 恢复：backend 重启后可恢复 queued/running lease；重复请求使用相同 idempotency key 不重复写。
- 兼容：前端现有事件至少可由 SSE projection 继续消费；legacy LangGraph 作为 adapter 通过同一 fake model/tool 集成测试。
