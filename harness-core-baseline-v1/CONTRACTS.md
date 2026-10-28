# Harness Core — Protocol & Contract Baseline v1

> **Status:** 初版规范（2026-10-28）。供 P0/P1 实现与 Contract Tests 使用。  
> 本文定义**语义与不变量**，字段/示例是建议的最小契约，不是现成可导入的 Python 实现。规范变更需更新版本、Fixture、测试与 ADR。

## 0. 全局约定

- **三种权威**：Runtime 拥有 Run 状态；Domain Service 拥有业务事实和资源授权；Memory Service 拥有长期知识。模型、浏览器、工具返回都不是权限权威。
- **三层通信**：外部 API/Transport command、Core 内部 Ports/contracts、前端安全 Event projection 分开定义。不要将 FastAPI Request、ORM、vendor SDK 对象写进 Core Contract。
- **ID**：`session_id`、`run_id`、`step_id`、`model_call_id`、`invocation_id`、`approval_id`、`event_id` 均为不透明、稳定标识。`thread_id` 只作为旧系统/客户端的映射别名；新 Core 默认使用 `session_id`。
- **版本**：对外/持久化对象必须有 `schema_version`；`CapabilityDefinition` 有独立 `capability_version`；Checkpoint/Context 算法有策略版本。未知不兼容主版本必须拒绝，不可静默回退。
- **编码**：所有持久化/跨进程对象 JSON-safe、UTC ISO-8601 时间、显式枚举与有界载荷；类型适配写在 Transport/Store/Provider Adapter。
- **Null semantics**：未知 usage/cost/remote outcome 用 `null`/`unknown`；不得虚构为 `0` 或成功。
- **隐私**：原始 chain-of-thought、API key、完整未经处理的 provider 请求/响应、非必要用户历史不得进入 RuntimeEvent、SSE、Trace 或 Eval artifacts。
- **信任标签**：`trusted_instruction`（仅由受信配置生成）/`authorized_data`/`untrusted_data`。授权访问的数据仍是数据，不等于可执行指令。

## 1. Execution Protocol

### 1.1 核心实体与权责

| Contract | 最少字段 | Owner / 要点 |
|---|---|---|
| `SessionRef` | `session_id`, `owner_ref`, `created_at`, `schema_version` | Conversation/Session service 负责会话归属及历史；Core 只引用。`thread_id` 在 Transport Adapter 映射。 |
| `RunRequest` | `schema_version`, `session_id`, `input`, `agent_profile_ref`, `client_request_id`, `run_options` | 外部输入，仅允许提供请求内容/可选偏好；Runtime 创建权威 ID；不得包含可信 identity/approval/status。 |
| `ExecutionContext` | `schema_version`, `principal_id`, `tenant_id`, `roles/scopes`, `run_id`, `trace_id`, `session_id`, `capability_allowlist`, `policy_version`, `deadline` | **受信** Identity/Policy/Runtime 共同创建，逻辑不可变；不得由模型、记忆、前端覆盖。匿名首版禁用。 |
| `RunState` | `run_id`, `state_version`, `status`, `current_step_id`, `budget_snapshot`, `pending_*_refs`, `last_durable_sequence`, `timestamps`, `terminal_error` | Runtime 是唯一状态转换者；Store 使用 CAS/原子提交。 |
| `StepRecord` | `step_id`, `run_id`, `parent_step_id?`, `kind`, `status`, `started_at`, `ended_at?`, `correlation_ref?` | 一次 model/context/tool/approval 控制操作；可关联多个事件。 |
| `RunResult` | `run_id`, `status`, `final_output_ref?`, `safe_error_code?`, `usage_summary?`, `finished_at` | 终态摘要；不代替 Transcript/Event。 |
| `RunBudget` | `max_model_calls`, `max_tool_calls`, `max_steps`, `deadline`, `token_limits`, `used/reserved` | Runtime 原子/串行计量，恢复时不重置；缺失 provider usage 明确保留未知。 |

**P1 状态**：`queued`, `running`, `succeeded`, `failed`, `cancelled`, `timed_out`。  
**预先保留、P2 实现转移**：`waiting_approval`, `waiting_reconciliation`, `interrupted`, `recovering`。  
`waiting_reconciliation` 表示外部副作用结果不确定，不能盲目重试；不能与普通模型失败合并。

```text
queued -> running | cancelled | failed
running -> succeeded | failed | cancelled | timed_out
running -> waiting_approval | waiting_reconciliation | interrupted      (P2)
waiting_approval -> running | cancelled | failed | timed_out          (P2)
waiting_reconciliation -> recovering | failed | cancelled           (P2, 需对账证明)
interrupted -> recovering | failed                                    (P2)
recovering -> running | waiting_approval | waiting_reconciliation | failed  (P2)
terminal [succeeded/failed/cancelled/timed_out] -> no transition
```

取消表示 Runtime 已确认不会启动新步骤，且对已启动的外部动作采取能力允许的取消/对账处理；**不能把网络断连当成取消**。外部动作一旦有不确定结果，先记录事实并停在可对账状态，不能假定取消已经回滚副作用。`cancel_requested` 是控制命令/标志，不是已完成取消。

`RuntimeCommand` 为受信命令联合类型：`create_run`, `request_cancel`, `submit_approval`, `request_resume`。携带认证 actor、幂等命令 ID、期望 `state_version`；Transport 不得直接修改 RunStore。

### 1.2 Loop & Decision

唯一 P1 Loop 策略：准备 Context → 调用模型 → 验证结构化 Decision → 工具执行/结束 → 记录 observation → 重复。Runtime 拥有状态和边界动作，Loop 不直接调用状态 Store。

- 模型决定的 `ModelDecision` 仅有两种受支持的**语义**：`invoke`（携带一个或多个 tool proposal）与 `final`（携带最终答复，`disposition=answered|refused`）。
- 非终态文本增量由 `ModelStreamEvent` 表达，不另设会偷偷终止 Run 的 `respond` 状态。
- 模型无效/未知 Decision → 安全验证错误或有界模型纠正尝试；不得自动调用猜测的工具。
- `LoopStepOutcome`（内部）仅可提出 `request_model`、`request_invocation`、`return_final`、`abort` 等结果；由 Runtime 作权威提交。`await_approval` / `reconcile` 在 P2 启用。
- Phase 1 最多支持显式有界的单批 read tool proposals；若实现并行，必须声明顺序、部分失败和取消语义。不得提前投递尚未校验完整的流式参数。

### 1.3 Model Gateway 合同

```text
ModelRequest:
  schema_version, model_call_id, run_id, trace_id
  context_snapshot_ref / typed_messages, tool_definitions
  model_policy, required_provider_features, output_reserve, deadline
  response_schema?, stream?
ModelResponse:
  model_call_id, provider_id, model_id, normalized_decision
  finish_reason, usage? (nullable), latency?, safe_error?
ModelStreamEvent:
  model_call_id, kind[text_delta | tool_proposal_delta | completed | failed]
  ordered_offset?, safe_payload
ProviderCapabilities:
  supports_tools, supports_stream, supports_structured_output
  supports_parallel_tool_calls, max_context_tokens?, usage_availability
```

`ModelGateway` **不得**执行工具、签发权限或推进 Run 状态。请求不支持的必需模型特性时，必须明确报错或执行**可信且已声明**的降级；不得假装厂商功能完全一致。Adapter 内处理 vendor SDK、认证、模型参数、速率限制/错误归一；重试层与 Runtime 的预算必须避免重复计数或双重重试。

### 1.4 Capability & Tool Invocation

| Contract | 必要语义 |
|---|---|
| `CapabilityDefinition` | `capability_id`, `capability_version`, `action_id`, `description`, `input/output_schema`, `effect_class=read|write|external_side_effect`, `risk_class`, `permission_requirements`, `approval_policy_ref?`, `timeout`, `retry_class`, `idempotency_requirement`, `concurrency_class`, `input/output_bounds` |
| `ToolInvocation` | `invocation_id`, `run_id`, `step_id`, `model_call_id`, `capability_id/version/action_id`, **canonical** arguments + `arguments_digest`, trusted actor/scope reference, stable `idempotency_key`, attempt/deadline, approval ref? |
| `ToolResult` | `invocation_id`, `status=succeeded|failed|rejected|timed_out|cancelled|unknown_outcome`, bounded typed result, safe error category/code, retryability, attempt/latency, output digest, provider correlation? |

**Tool pipeline**（不可跳过）：

```text
ModelDecision.invoke
  -> Registry resolve pinned capability version
  -> schema/size validation + reject authority-field pollution
  -> Policy authorize(ExecutionContext, action, resource/args)
  -> Approval barrier if required (P2)
  -> persist InvocationIntent before external dispatch
  -> ToolExecutionPort.invoke(..., restricted trusted context)
  -> normalize ToolResult + persist outcome
  -> feed observation to Context/Loop
```

Registry 负责**发现和工具定义投影**，不是授权机关。业务 Domain Service 必须独立检验资源所有权。Tool output 一律作为不可信 observation。ToolAdapter 类型（Python/HTTP/MCP/Sandbox）不改变 Loop。工具的“只读/并发安全”可在调用时依据参数判断，但不能由模型输入自行提升权限。

- 读取型工具：只有在声明为幂等、失败类型确定且预算允许时重试。
- 写/外部副作用：需要稳定 `idempotency_key`、durable intent、结果查询或显式对账策略。一次尝试结果未知时标记 `unknown_outcome`；不得产生新 key 重做。
- P1 Fake Tool 不接真实写服务。**在 P2 持久化/审批/对账通过前禁止真实外部写能力。**

### 1.5 Policy / Approval

- `PolicyDecision = allow | deny | require_approval`，由可信 Policy Port 返回；默认拒绝未知 capability/身份/权限。
- `ApprovalRequest`：`approval_id`, `run_id`, `invocation_id`, actor/tenant, action + version, **canonical arguments digest**, resource digest, effect/risk, policy version, created/expires, redacted presentation。
- `ApprovalDecision`：approval ID、digest、authenticated approver、decision `approved|rejected|expired|revoked`、time、reason/version。不得接受修改后的参数作为“同一审批”。
- Approve 后仍需复验当前主体、资源权限、参数 digest、有效期和策略版本；批准不能自动绕过 Domain Resource ACL。
- **授权校验每次执行必需；人工审批按风险策略触发，非所有写动作一律必须弹窗。**

### 1.6 Run Journal / Checkpoint / Event

`RunJournalPort`（建议）原子处理：RunState CAS + durable event append + invocation intent/result 的需要共同提交的事实。具体 SQL/数据库实现归 Adapter；P1 可 InMemory，P2 需具备跨进程可恢复的事务边界。`CheckpointPort` 保存由这些事实关联的恢复快照，可落后，但不能让其覆盖更可信的已提交 invocation 事实。

```text
Checkpoint:
  schema_version, run_id, state_version, last_durable_sequence
  serialized_control_state, remaining_budget, strategy_id/version
  pending_invocation_ref?, pending_approval_ref?
  capability_hashes, policy_version, lease_epoch?, checksum, timestamp
```

Checkpoint **不能**包含 provider credentials、完整原始推理、ORM/HTTP 对象；恢复时重新认证/授权、验证版本、owner、checksum 和 pending side-effect 记录。持久化事实与外部业务效果不能共享事务时，以 stable key 查询已执行结果；不能宣称 exactly-once。

`RuntimeEvent`：

```text
EventEnvelope:
  event_id, run_id, sequence? (per-run durable monotonic)
  occurred_at, schema_version, event_type, payload_type
  step_id?, model_call_id?, invocation_id?, causation_id?, correlation_id?
  durability = durable_fact | ephemeral_delta
  safe_typed_payload
```

- Durable 事件：`run.started|completed|failed|cancelled|timed_out|paused|resumed`, `tool.intent|completed|failed|unknown_outcome`, `approval.requested|resolved`, `model.started|completed|failed`（依据持久化策略保存必要事实）。
- Ephemeral：`message.delta`, `progress.delta` 等高频数据；不承诺断线逐 token 重放。
- 事件从已提交的 Journal 事实产生；单 Run durable sequence 单调、append/replay 有确定游标。消费者以 `event_id` 去重、识别 sequence gap 后 replay；SSE/前端是安全投影，不是状态真相。
- **任何 event/trace/log 不能直接转发 vendor `reasoning_content` 或原始 provider chunk。**

## 2. Context Protocol

### 2.1 输入/输出契约

```text
ContextBuildRequest:
  schema_version, run_id, model_call_id
  session_ref, current_input_refs, history_refs, tool_result_refs
  agent_instruction_refs, allowed_capability_refs, memory_query_hint?
  trusted_execution_context_ref, model_context_limit, reserved_output_tokens
  context_policy_version
ContextSnapshot:
  schema_version, snapshot_id/hash, run_id, model_call_id
  ordered_typed_message_blocks, projected_tool_definitions
  source_refs + per-block trust/provenance
  token_estimates (per block + total), reserved_output_tokens
  included_refs, excluded_refs, truncation/compaction_actions, warnings
```

- `ContextEngine.build()` 是 **每次模型调用**的确定边界，不能由 Loop 任意拼接不带标签的字符串。
- 数据从 Conversation Store / Run observations / capability definitions / `MemoryReader` 获取；只有受信配置能产生 system/developer instruction。模型可见“你已授权”描述**不**具有权限效力。
- 先获取并按授权过滤，再挑选排序、估算预算、压缩/裁剪、形成不可变 Snapshot；尽可能稳定可缓存前缀。
- Context token 估算与模型真实计数可能不同。无法安全容纳时拒绝调用或采取显式压缩，不隐式丢掉当前任务的关键约束；为输出留容量。
- 压缩只改变模型可见投影，**绝不改写/删除原始 Transcript**；保存摘要版本、压缩动作和原始来源引用，以便评估与重建。
- `authorized_data` 只说明能读取；用户输入、历史、Memory、Web、MCP、ToolResult 必须以**数据**处理，不能成为高优先级指令或授权。

### 2.2 P1 / P2 分工

P1：简单固定顺序 Builder、token 预估/限制、工具结果上限、Fake MemoryReader、完整来源标签；ContextSnapshot 进入 ModelGateway 并被引用/审计。  
P2：可替换历史选择、关键词/记忆按需检索、分级裁剪、Compaction 摘要、缓存优化、隐私保留策略与跨租户检索测试。

## 3. Memory Protocol

### 3.1 Core 的唯一依赖：MemoryReader Port

```python
class MemoryReader(Protocol):
    async def query(
        self,
        request: MemoryQuery,
        context: ExecutionContext,
    ) -> MemoryQueryResult: ...
```

`MemoryQuery`（业务无关）：`schema_version`, `domain?`, `kinds?`, `subjects?`, `tags?`, `keywords?`, `as_of?`, `limit`, `token_budget?`。**不接受模型指定任意 owner/tenant、SQL 文本或未经校验的任意过滤表达式。**

`MemoryQueryResult`：有界 `records`, `source_refs`, `query_strategy`, `truncated`, `warnings`, `retrieval_policy_version`。作用域先由受信 `ExecutionContext` 注入并过滤；Memory records 仍是 untrusted data。

### 3.2 独立 Memory Service 的契约

```text
MemoryRecord:
  schema_version, memory_id, owner_id, tenant_id?, scope, domain, kind
  subject/tags, content, source_refs, source_kind (explicit|inferred|external)
  confidence?, observed_at, updated_at, valid_until?
  status (candidate|active|superseded|expired|deleted)
  version, supersedes_ref?, retention_policy_ref?
```

Memory Service 单独拥有：`extract_candidates` → `validate` → `consolidate(new/merge/supersede/reject/expire)` → `store`，以及 `query`、用户 `correct`、`delete/forget`、retention、Profile projection。它可以由任务事件触发独立 Worker，不阻塞 Run 完成；必须允许用户选择禁用自动学习、查看/纠正/删除。推断偏好不能冒充用户明确陈述；敏感属性不能在未经适当授权时自动推断并保存。

**Query-first 默认策略：** PostgreSQL/其他现有关系 DB + owner/tenant/scope/status/时间/标签过滤 → 关键词/全文/BM25 → 去重/相关性排序 → token 上限。向量索引是可选的内部检索策略，**不是合同依赖，也不是 P1/P2 的交付前提**。

**Source-of-truth 规则：** 用户收藏/评分/日历 = Domain Service 权威事实；Memory = 过往偏好、反馈、知识线索；User Profile = 可重建派生视图。旧 Memory 可被新 Adapter 读取，但不能让 Core 写原表或绕过授权。

## 4. 最小 Port 清单及替换要求

| Port | 最小方法/语义 | P1 implementation | P2 implementation |
|---|---|---|---|
| `ModelGateway` | `infer/stream(request) -> normalized result/events` | 2 个 Scripted Fake Provider | 至少 1 个真实 Provider Adapter；同一合同测试 |
| `ContextEngine` | `build(request, trusted_ctx) -> snapshot` | Deterministic Builder | Bounded retrieval + compaction |
| `MemoryReader` | `query(request, trusted_ctx) -> result` | Fake/No-op | Scope-aware SQL/keyword adapter |
| `CapabilityRegistry` | `get/list_visible(version, ctx)` | Static definitions | 可扩展来源，仍由 Policy 授权 |
| `PolicyPort` | `authorize(invocation, trusted_ctx) -> decision` | Deny-by-default; read-only allowlist | Approval、细粒度 scope、撤销/复验 |
| `ToolExecutionPort` | `invoke(authorized_invocation, trusted_ctx) -> result` | Fake read-only | Domain HTTP/local/MCP adapters 逐个实现 |
| `RunJournalPort` | CAS state + durable event + invocation facts | InMemory | Transactional store + replay |
| `CheckpointPort` | `save/load(versioned snapshot)` | InMemory/No-op（不可宣称恢复） | Durable with version/fencing/recovery tests |
| `EventProjectionPort` | `project(durable facts / safe deltas)` | Capture Fake | SSE + safe Trace/Metrics |

## 5. 必测的跨协议不变量

1. Forged principal/tenant/role/tool args **never** change `ExecutionContext` or expand allowed actions.
2. Disallowed capability cannot be projected to model **or** dispatched even with a forged proposal.
3. Same `invocation_id + idempotency_key` cannot cause a second side effect; different canonical args cannot reuse that key.
4. Approved action can execute only with matching action/version/args/resource digest and current authorization.
5. External effect with uncertain status becomes `unknown_outcome` / `waiting_reconciliation`, not blind retry.
6. Run terminal states cannot be rewritten; cancellation/timeout cannot reset budget or create further invocations.
7. Original Transcript is independent of compaction; `ContextSnapshot` is per model call and source-traceable.
8. MemoryReader queries are owner/tenant scoped before retrieval; Memory content never grants permission; deleting a source is reflected in derived Profile/indexes per retention policy.
9. Durable event replay preserves per-run order, dedup and safe payload; raw reasoning/credentials never leak across any output sink.
10. Replacing Fake A with Fake B does not change Loop implementation; Clean Core install has no OtakuNeko/ORM/vendor imports.

## 6. Contract change process

**Before coding:** write/update JSON-safe fixtures, a unit/port conformance test, and consumer expectations.  
**Additive changes:** new optional field + backward-compatible fixture.  
**Semantic/breaking changes:** new major version + migration/refusal policy + ADR.  
**No guessing:** if a legacy field differs, map it in an Adapter rather than silently weakening the new Contract.

See [`ARCHITECTURE.md`](ARCHITECTURE.md) and [`docs/adr/ADR-0001.md`](docs/adr/ADR-0001.md) for ownership, constraints and first-release decisions.
