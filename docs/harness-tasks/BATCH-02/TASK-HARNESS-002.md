# TASK-HARNESS-002

## 目标

定义版本化的 `RunRequest`、`ExecutionContext`、`AgentDecision`、`InvocationRequest`、`InvocationResult`、`RunEvent`、`RunResult` 和错误分类，并用 adapter 包装现有 LangGraph/raw Tool 事件。

## 背景

对应 `G-P1-01`、`G-P1-02`、`G-P1-06`、`G-P1-11`。当前已有 `AgentTask`、`AgentState`、`AgentResult`、`CapabilityResult`，但 Graph Tool 输出仍是 raw payload，Runtime/Graph/Trace/SSE 没有共同的 Run/Invocation/sequence（`backend/app/harness/task.py`; `backend/app/harness/state.py`; `backend/app/harness/result.py:8-85`; `backend/app/agents/graph.py:445-477`）。参考文档 Batch 1 要求这些契约并用 Adapter 兼容现有 LangGraph/Tool（参考文档:1928-1938）。

## 允许修改

- 新建 `backend/app/harness/contracts.py`
- `backend/app/harness/task.py`
- `backend/app/harness/state.py`
- `backend/app/harness/result.py`
- `backend/app/agents/langgraph_adapter.py`
- `backend/tests/harness/test_contracts.py`
- `backend/tests/harness/test_result_contract.py`
- `backend/tests/agents/test_langgraph_adapter.py`

## 禁止修改

- `backend/app/api/v1/agent.py` 的外部请求/SSE 结构
- `backend/app/agents/graph.py` 的节点、模型、ToolNode 行为
- 数据库/迁移、前端、全部 Tool 注册和 Domain Service
- 将 raw reasoning/Chain-of-Thought 写入新契约

## 实施要求

1. 在 `contracts.py` 定义 Pydantic v2 模型：

```python
class ExecutionContext(BaseModel):
    principal_id: int | None
    run_id: str
    trace_id: str
    capability_allowlist: frozenset[str] = frozenset()

class InvocationRequest(BaseModel):
    invocation_id: str
    run_id: str
    capability: str
    capability_version: str
    arguments: dict[str, Any]
    idempotency_key: str | None = None

class InvocationResult(BaseModel):
    invocation_id: str
    status: Literal["succeeded", "failed", "denied", "cancelled"]
    output: dict[str, Any] = {}
    error_code: str | None = None
    retryable: bool = False

class RunEvent(BaseModel):
    run_id: str
    sequence: int
    event_type: str
    invocation_id: str | None = None
    payload: dict[str, Any] = {}
```

`RunRequest` 至少包含 `run_id/user_id/goal/messages/model`；`RunResult` 至少包含 `run_id/status/content/error_code`。所有默认 dict 使用 `Field(default_factory=dict)`，不使用可变默认值。

2. 错误分类固定为 `invalid_request、unauthorized、policy_denied、timeout、cancelled、budget_exceeded、provider_error、tool_error、transient、permanent`；raw exception 只能进入内部 cause，不进入 public payload。
3. 在 `LangGraphAdapter` 增加纯 adapter 函数，把当前 `tool_call_start/tool_call_end/error/message_*` 转成 `RunEvent`；不改变既有 chunk，旧调用方继续获得原事件。
4. `AgentResult.from_raw` 保持兼容旧 dict，但新增 `InvocationResult` 的显式转换路径；`content` 不进入 `prompt_payload()`。
5. `ExecutionContext.principal_id` 只能由 API/scheduler 注入；契约不得把 `user_id` 作为模型可写的公开 Tool 参数。

## 兼容要求

- 现有 `AgentTask` 和 `AgentResult` 保留，契约先作为包装层。
- 现有 SSE event name 和 payload 不变；新增内部 RunEvent 不要求前端立即消费。
- 旧 Tool dict 能通过 `from_raw` 得到稳定的 `InvocationResult`。
- Schema 必须可 JSON 序列化，且不包含 api key、authorization、raw prompt 或 CoT。

## 测试

- 单元测试：模型校验、错误枚举、不可变 `principal_id` 语义、默认字段、JSON 序列化和 raw result 兼容。
- 集成测试：fake LangGraph event stream 逐事件转译并保持 sequence/Invocation ID 稳定；Graph error event 得到 `failed` 语义。
- 回归测试：`cd backend && uv run pytest tests/harness tests/agents/test_langgraph_adapter.py tests/agents/test_chat_schema.py -q`。
- 手工验证：用现有 `/chat` fake provider 跑一次只读回答，确认旧 SSE 仍可消费且未输出新 raw secret 字段。

## 验收标准

- [ ] 七类契约和错误分类存在，并有 JSON schema/单元测试。
- [ ] raw Tool、Graph error、agent result 都能通过 adapter 得到结构化结果。
- [ ] `principal_id` 不来自模型 arguments；raw exception/CoT/secret 不出现在 public payload。
- [ ] 旧 AgentRuntime/Graph 测试全部通过，未修改 API/DB/frontend。

## 回滚

移除新 contract adapter 的调用点即可恢复旧 chunk；保留纯 Pydantic 类型和测试，不删除旧 `AgentResult`/`AgentTask`。回滚不得把新 public payload 改成 raw exception。

## 输出

- 修改文件列表：列出 contract、adapter 和测试。
- 测试结果：报告 schema、raw compatibility、Graph error 转译结果。
- 未解决问题：列出仍由 BATCH-03/05 决定的 Registry/Runtime 接入点。
- 风险说明：说明本任务只定义并适配契约，不改变实际 Loop owner。
