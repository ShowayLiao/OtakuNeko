# TASK-POST-AUDIT-001：主聊天接入 Decision / Dispatcher

## 目标

让主聊天路径从：

```text
LLM tool call → LangGraph ToolNode → ALL_TOOLS
```

迁移为：

```text
LLM output → AgentDecision → DecisionParser → PolicyEngine
→ Dispatcher → CapabilityAdapter → InvocationResult
```

本任务只建立主路径控制边界和只读 Capability canary，不接入新的写能力。

## 前置事实

- `AgentDecision`、`InvocationRequest`、`InvocationResult` 已存在于 `backend/app/harness/contracts.py`。
- `CapabilityRegistry` 已存在于 `backend/app/capabilities/registry.py`。
- `CapabilityAdapter` 已存在于 `backend/app/harness/capability_adapter.py`。
- `ChatWorkflow` 当前仍在 `backend/app/agents/graph.py` 内直接创建 `ToolNode` 并执行 `ALL_TOOLS`。
- `LangGraphAdapter` 当前是完整 `ChatWorkflow.stream_chat()` 的 pass-through。[`backend/app/agents/langgraph_adapter.py:88-160`](../../../backend/app/agents/langgraph_adapter.py#L88)

## 允许修改的文件

### 创建

- `backend/app/harness/decision_parser.py`
- `backend/app/harness/dispatcher.py`
- `backend/tests/harness/test_decision_parser.py`
- `backend/tests/harness/test_dispatcher.py`
- `backend/tests/acceptance/test_primary_decision_path.py`

### 修改

- `backend/app/harness/contracts.py`
- `backend/app/harness/model_gateway.py`
- `backend/app/harness/coordinator.py`
- `backend/app/harness/runtime.py`
- `backend/app/harness/capability_adapter.py`
- `backend/app/capabilities/registry.py`
- `backend/app/capabilities/langchain_adapter.py`
- `backend/app/agents/langgraph_adapter.py`
- `backend/app/agents/graph.py`
- `backend/app/api/v1/agent.py`，仅限传递可信 `ExecutionContext` 和主路径配置

## 禁止修改

- `backend/app/services/` 的业务规则。
- qBittorrent 写行为和数据库 migration。
- 前端协议和 SSE event 名称，除非发现现有协议无法表达新的结构化事件并在任务记录中明确批准。
- `ALL_TOOLS` 的删除；本任务只把它降级为兼容来源，并通过 allowlist 约束。
- 任何副作用 Capability 的主聊天暴露。

## 实施步骤

### 步骤 1：补充 Decision Parser 失败测试

在 `backend/tests/harness/test_decision_parser.py` 覆盖：

- 合法 `invoke` Decision 能解析为 `AgentDecision`。
- `respond` / `finish` Decision 不生成 Invocation。
- 缺少 capability、version 或非法 action 被拒绝。
- 参数含 `user_id`、`principal_id`、`db`、`token` 被拒绝。
- 未知 schema version 被拒绝。
- Provider 返回错误 JSON、多个冲突 tool call、超大 arguments 被拒绝。
- 错误只返回安全的结构化 `ErrorCode`，不返回 raw provider payload。

执行：

```powershell
uv run --directory backend pytest tests/harness/test_decision_parser.py -q
```

预期：新增测试在实现前失败。

### 步骤 2：实现 provider-neutral DecisionParser

`decision_parser.py` 必须：

1. 接收 provider-neutral model result，不接收业务 Service 或数据库对象。
2. 将 LangChain/OpenAI-compatible tool call 映射为 canonical capability name/version。
3. 强制校验 `AgentDecision`。
4. 只保留 public arguments。
5. 不从模型参数读取身份、租户、审批或资源归属。
6. 对 `respond` 结果使用受限的 user-facing content，不把内部 prompt/CoT 转为回答。

### 步骤 3：补充 Dispatcher 失败测试

在 `backend/tests/harness/test_dispatcher.py` 覆盖：

- canonical action 能通过 Registry 找到 Capability。
- 缺失 Capability 返回 `not_configured`，不执行 Service。
- Policy deny 时不执行 Capability。
- 身份由 `ExecutionContext` 注入，模型参数不能覆盖。
- side effect 在没有幂等 Key、审批或授权时被拒绝。
- Invocation start/end 都使用同一 `invocation_id`。
- Capability 异常转换为 `InvocationResult`，不向模型暴露 raw exception。
- timeout/cancel 时底层 adapter 能收到 cancellation signal。

执行：

```powershell
uv run --directory backend pytest tests/harness/test_dispatcher.py -q
```

### 步骤 4：实现 Dispatcher

`dispatcher.py` 的输入至少包括：

```text
AgentDecision
ExecutionContext
RunBudget
CancellationToken
CapabilityRegistry
PolicyEngine
```

Dispatcher 必须完成：

1. 解析 canonical capability 和 version。
2. 从 Registry 获取 `ActionDescriptor`。
3. 先执行 Policy/authorization，再创建或执行 Invocation。
4. 为 side effect 校验 idempotency/approval。
5. 只向 CapabilityAdapter 传递 public arguments + trusted context。
6. 将结果统一为 `InvocationResult`。
7. 写入可供 `RunCoordinator` 持久化的结构化事件。

### 步骤 5：把主聊天 Graph 改为“提议/继续”适配器

修改 `graph.py` 和 `langgraph_adapter.py` 时必须保持外部聊天协议兼容，但改变内部权责：

- Graph 可以继续负责消息上下文、模型调用和 checkpoint。
- Graph 遇到 tool call 时只能产生 `model_decision` / `tool_requested` 事件。
- Graph 不得直接执行业务 Capability。
- Runtime/Coordinator 调用 Dispatcher 后，将 `InvocationResult` 作为受控 continuation 输入 Graph。
- Tool result 必须经过 ResultNormalizer，再进入下一次模型 Context。
- `ToolNode` 如果暂时保留，只能调用一个不会直接触达 Domain Service 的 proposal adapter。

不得把 provider 原始 tool call 直接视为已经授权的 Invocation。

### 步骤 6：接入 ModelGateway 主推理接口

扩展 `ModelGateway`，使主模型调用至少能返回：

```text
ModelCallResult
  status
  decision / content
  usage
  latency
  provider
  model
  error_code
  retryable
```

主模型的 usage 必须能够被 `RunBudget` 消费；未知 usage 必须标记 unknown，不能转换成零成本。

### 步骤 7：主路径 Acceptance 测试

在 `backend/tests/acceptance/test_primary_decision_path.py` 使用 fake provider、fake read-only Capability 和 fake EventStore，验证：

```text
HTTP/Task
  → Runtime
  → ModelGateway fake
  → AgentDecision
  → Policy
  → Dispatcher
  → Capability
  → InvocationResult
  → final response
```

至少包含：正常只读查询、非法 capability、policy deny、身份伪造、工具失败、二次 Decision 和最终 respond。

## 验收条件

- 主聊天 fake 流程中不再直接从模型 tool call 进入业务 Tool。
- 至少一个 Anime read Capability 通过 canonical Registry/Dispatcher 执行。
- 所有主路径工具调用都有 `AgentDecision`、`InvocationRequest`、`InvocationResult`。
- Policy deny 时 fake Domain Service 调用次数为零。
- 模型永远不能设置 `user_id` 或 `principal_id`。
- `pytest tests/harness tests/acceptance -q` 通过。
- `uv run --directory backend ruff check app tests` 通过。
- 旧只读聊天兼容测试继续通过。

## 回滚

- 保留 Legacy read-only adapter，但只能由明确的兼容开关启用。
- 关闭新 Dispatcher 时仍禁止 side effect 绕过 Policy。
- 不删除现有 Run/Event 数据或旧 event 映射。
- 如果主路径不能安全转换 Decision，则返回结构化 `provider_error`/`invalid_request`，不得退回无 Policy 的工具执行。
