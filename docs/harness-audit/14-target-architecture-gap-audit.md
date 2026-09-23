# Target Architecture Gap Audit

> 状态：第 1～8 节保留 BATCH-20 开始前的规划基线；第 9 节记录 BATCH-20～26 完成后的当前 closure 结论。
>
> 审计基线：feature-harness / 65d48429144c97699862494807e31fb9f1a591e2。
>
> 关联目标：docs/architecture/agent-runtime-target-architecture.md。

## 1. 审计目的与结论

本审计回答一个问题：当前仓库距离 agent-runtime-target-architecture.md 的退出条件还差哪些可执行、可验收的工作。

源码事实优先于任务名称、类名和历史执行记录。BATCH-20 开始前的基线结论为：

~~~text
Level 2 partial / Runtime-governed compatibility architecture
~~~

当前已经存在 DecisionParser、Dispatcher、Run/Event Store、checkpoint、CancellationToken、ModelGateway 和 Runtime-owned Decision Loop canary，但默认主聊天仍然保留 LangGraph 内部循环，canary 也没有完成 canonical durable Run/Event/Invocation 管线。因此不能宣称 AgentRuntime 已经是生产主链路的唯一控制者。

本审计不把测试文件存在、feature flag 存在或历史 execution record 的 pass 当作生产路径已接入的证明。每一项退出条件都必须由真实源码入口、失败路径测试、持久化行为和完整 diff Review 共同证明。

## 2. 当前基线事实

### 2.1 主聊天入口

- backend/app/api/v1/agent.py 创建了 AgentRuntime，但通过 _primary_decision_loop_enabled() 选择 canary 或兼容路径。
- HARNESS_PRIMARY_DECISION_LOOP_ENABLED 默认关闭时，/chat 使用 runtime.stream()，而不是 runtime.stream_decision()。
- FeatureFlagRoutingAdapter 当前以 enabled=False 构造，specialist 路由暂时被主聊天 canary fail-closed 地禁用。
- backend/app/agents/graph.py::ChatWorkflow 仍然编译并运行 LangGraph think -> ToolNode -> think -> speak 循环。ToolNode 已改为 proposal-only wrapper，这是安全改进，但不等于 Runtime 已夺取循环控制权。

### 2.2 Runtime-owned canary

- backend/app/harness/runtime.py::AgentRuntime.stream_decision() 已能执行：

~~~text
ModelGateway -> DecisionParser -> Dispatcher -> InvocationResult -> continue/terminal
~~~

- 该方法目前主要保存 checkpoint 并产生内存中的 stream event。
- API 虽然把 RunStore 和 EventStore 注入 Runtime，但 canary 当前没有在 Runtime 内完成 Run 创建、canonical Event 写入、Invocation 持久化和 terminal transition。
- 因此 canary SSE 与 /runs/{id}、/runs/{id}/events 还不能被证明使用同一个事实源。

### 2.3 已发现的安全与可靠性事实

- ModelGateway 的 Provider adapter 仍有捕获 BaseException 的路径，模型调用中的取消可能被转换为普通模型结果；Runtime 的 DecisionParseError 分支还可能把取消映射成 failed。
- Dispatcher 目前把成功 Capability 的原始 dict 作为 output 返回，缺少统一的 input/output schema、大小限制和 safe projection 入口。
- PROVIDER_RESOLVE_DNS 默认关闭，PROVIDER_ALLOWED_HOSTS 默认为空；Provider endpoint 对任意域名的初始 DNS 私网解析不是默认 fail-closed。
- GET /models/check 没有应用业务认证依赖，并直接创建 HTTP Client 请求用户提供的 endpoint。
- RecommendationAgent、scheduler specialist adapter 和部分 legacy agent 仍存在直接 Capability/Agent 执行路径。
- SQLite checkpoint 部署明确是 single-worker；跨 worker 的 durable cancellation、lease 和恢复语义尚未完成。
- 现有 acceptance 主要直接实例化 AgentRuntime 和 fake gateway，没有完整覆盖真实 /chat、RunStore/EventStore、SSE replay 和 canary 配置。

## 3. 目标退出条件逐项对照

| 目标架构退出条件 | 当前状态 | 证据/缺口 | 后续任务 |
|---|---|---|---|
| /chat 只进入 AgentRuntime，不创建第二套模型/工具循环 | Partial | 默认仍走 runtime.stream()，ChatWorkflow 仍拥有 LangGraph 循环 | 007、010 |
| 主模型调用统一经过 ModelGateway | Partial | canary 经过 Gateway，默认 Graph 直接创建 LangChain model | 010，并受 011 的 cancellation/error contract 约束 |
| LLM 只输出版本化 AgentDecision | Partial | DecisionParser 已存在；默认 Graph 仍有 provider/tool-call 兼容投影 | 007、010 |
| DecisionParser/Dispatcher 是唯一执行边界 | Partial | 主聊天 proposal handler 已接入；specialist、scheduler、legacy MCP 仍需盘点和收口 | 010 |
| Runtime 决定 continuation、retry、cancel、timeout、terminal | Partial | canary 有循环；默认 Graph 和 ModelGateway cancellation 语义尚未统一 | 006、011、009、010 |
| Invocation/Result/Event 使用唯一 canonical ID 和顺序 | Target | Dispatcher 内存 events、Coordinator legacy persistence、API SSE 存在多套投影 | 007、012 |
| Result 是 safe、bounded、schema-validated 的 public contract | Partial | InvocationResult 存在，但成功 raw output 尚未经过统一 ResultNormalizer | 012 |
| ContextManager 统一 trusted principal/tenant/scope/Memory/tool schema | Partial | Context 和 Memory 已有局部边界，但没有唯一 ContextManager | 008、012 |
| side effect 具备授权、审批、超时、取消、重试、幂等、审计、补偿 | Partial | schedule/idempotency 基础存在；unknown outcome、跨 worker recovery、所有入口 parity 未完成 | 009、010 |
| Run/Event/Invocation 在 SSE 断线和 worker 重启后可恢复 | Target | canary 尚未 canonical persistence；SQLite 只支持明确 single-worker | 007、009 |
| Provider endpoint 和外部网络默认安全 | Partial | redirect 有校验；初始 DNS 和 /models/check 仍需 fail-closed | 013 |
| 真实主 API fake-provider Eval 通过 | Target | 当前 acceptance 主要直接调用 Runtime，不证明 /chat 路由和持久化 | 010 |
| legacy ToolNode/specialist/MCP bypass 退役 | Target | 仍能找到直接 Capability/Agent execute 路径 | 010 |

## 4. 未闭合 Gap

### G-TARGET-001：默认主链路仍由 LangGraph 控制

- 严重性：High
- 类别：architecture / correctness
- 证据：backend/app/api/v1/agent.py 的 primary loop flag 和 runtime.stream() 分支；backend/app/agents/graph.py::ChatWorkflow 的 compiled ToolNode 与 model ainvoke()。
- 影响：Runtime 无法唯一决定继续、重试、取消和终态；默认生产路径与目标拓扑不一致。
- 必须完成：先完成 canonical persistence、取消和 API parity，再把 Runtime-owned loop 切为默认；保留的 LangGraph 只能是 provider-neutral compatibility adapter，不能保留内部 Run loop。

### G-TARGET-002：canary 未接入 canonical durable pipeline

- 严重性：High
- 类别：persistence / recovery / API
- 证据：stream_decision() 当前只保存 checkpoint 和 yield event；API 的 RunStore、EventStore 注入没有形成同一条 Runtime persistence boundary。
- 影响：SSE 可能显示了事件，但 Run 查询、事件 replay、terminal state 和 Invocation 记录不一致；断线恢复不能证明不会重复执行。
- 必须完成：由 Runtime 原子地写入 Run、Decision、Invocation、Result、Event 和 terminal transition；API 只读取/投影 EventStore。

### G-TARGET-003：模型取消、超时和错误语义未统一

- 严重性：High
- 类别：cancellation / timeout / provider
- 证据：backend/app/harness/model_gateway.py 的 Provider adapter 捕获 BaseException；ModelGateway.infer() 未把 CancellationToken/deadline 作为明确契约；stream_decision() 的 DecisionParseError 分支没有把 cancelled 作为 terminal cancelled 处理。
- 影响：取消可能等待 Provider 返回，或被错误报告为 failed；不能保证一个 Run 只有一个正确的 cancelled/timeout terminal event。
- 必须完成：见 TASK-POST-AUDIT-011。

### G-TARGET-004：ResultNormalizer 和 schema boundary 不完整

- 严重性：Medium
- 类别：contract / security / observability
- 证据：backend/app/harness/dispatcher.py::dispatch() 成功时直接保留 raw output；backend/app/harness/capability_adapter.py 没有统一应用 descriptor output schema、payload 上限和模型/SSE safe projection。
- 影响：不可信 tool/MCP/RSS 内容可能原样进入模型上下文或 SSE；原始输出可能超过契约边界，造成 prompt injection、敏感字段传播和审计不一致。
- 必须完成：见 TASK-POST-AUDIT-012。

### G-TARGET-005：ContextManager 和 authority field 规则未完全统一

- 严重性：Medium
- 类别：authorization / context / memory
- 证据：DecisionParser 拒绝的 authority field 集合比 Contract、CapabilityAdapter 和 MCP 的部分过滤集合更完整；API、Memory、Tool schema 和 Run state 仍由多个组件自行拼接。
- 影响：不同入口可能产生不同的模型可见上下文和身份信任边界；scope、tenant、approval 等字段可能在非主 Parser 入口被当作普通参数。
- 必须完成：由 ContextManager 生成版本化、可审计的 model-safe snapshot；提取全局 runtime-owned field 集合并在所有入口复用。

### G-TARGET-006：shared checkpoint、durable cancellation 和 worker recovery 未完成

- 严重性：High
- 类别：operations / recovery
- 证据：backend/app/harness/cancellation_store.py 是进程内 registry；docker-compose.yml 明确使用 SQLite single-worker checkpoint；缺少 worker lease、claim、fencing 和 unknown side-effect recovery 的完整路径。
- 影响：worker 重启或多 worker 部署时，取消不能到达执行中的 worker；同一 Run 可能被重复 claim；未知副作用可能被错误重试。
- 必须完成：见 TASK-POST-AUDIT-009。

### G-TARGET-007：specialist、scheduler、MCP 和 legacy agent 仍有 bypass

- 严重性：High（对启用的路径）
- 类别：architecture / authorization
- 证据：backend/app/agents/recommendation_agent.py 直接调用 Capability；backend/app/harness/scheduler/execution.py::_SpecialistAdapter 直接调用 agent；MCP/legacy adapter 需要逐入口证明只通过 Dispatcher。
- 影响：不同入口可能绕过 Runtime context、Policy、Approval、Budget、Cancellation、Idempotency 和 canonical Event。
- 必须完成：建立 enabled-entry inventory，逐入口迁移到 Dispatcher；未迁移入口必须 fail-closed，不能只靠“默认未打开”作为长期安全边界。

### G-TARGET-008：Provider endpoint 初始请求未默认 fail-closed

- 严重性：High
- 类别：security / external access
- 证据：backend/app/core/config.py 默认 PROVIDER_RESOLVE_DNS=false、allowlist 为空；/models/check 接收用户 endpoint 并直接请求。
- 影响：可能被用作内网探测、私网 DNS 解析访问或 metadata 访问入口。
- 必须完成：见 TASK-POST-AUDIT-013。

### G-TARGET-009：真实主 API Acceptance/Eval 不足

- 严重性：Medium
- 类别：testing / release gate
- 证据：backend/tests/acceptance/ 当前主要直接调用 Runtime；没有同时验证 /chat、canary flag、RunStore/EventStore、SSE replay、owner scope 和 frontend contract。
- 影响：测试通过不能证明默认生产入口已经迁移；路由层可能仍使用旧 Graph、旧 prompt contract 或非 canonical event。
- 必须完成：TASK-POST-AUDIT-010 增加真实 API fake-provider/tool Eval，且必须验证持久化与 replay。

### G-TARGET-010：已有终态 Run、重复请求和回滚语义还需统一

- 严重性：Medium
- 类别：idempotency / compatibility / rollback
- 证据：RunCoordinator.execute() 有 existing-run terminal guard，而 stream() 路径需要单独证明不会在已终止 Run 上重新启动 adapter；BATCH-14～19 仍集中在未提交工作树中。
- 影响：重复请求、SSE 重连和 worker 重试可能触发重复执行或非法状态迁移；单一脏工作树使按 Batch 回滚困难。
- 必须完成：为 stream/execute/resume 使用同一 Run claim 和 terminal guard；每个真实 Batch 使用独立 execution record，未经授权不提交或重置。

## 5. 任务映射与依赖

~~~text
TASK-POST-AUDIT-006  Runtime-owned Decision Loop canary       [completed canary, not final]
          │
          └── TASK-POST-AUDIT-011  Model cancellation/timeout/error
                         │
                         └── TASK-POST-AUDIT-012  Result/schema/safe output
                                      │
                                      └── TASK-POST-AUDIT-007  Canonical persistence/SSE
                                      │
                                      └── TASK-POST-AUDIT-008  ContextManager/trust
                                                   │
                                                   └── TASK-POST-AUDIT-009  Shared recovery/lease
TASK-POST-AUDIT-013  Provider SSRF/egress hardening  ───────────────┐
                                                                    │
                                                                    └── TASK-POST-AUDIT-010  Legacy retirement/API Eval/cutover
~~~

建议将 011、012、013 分别作为独立可 Review 的任务；007～010 仍然是主迁移链。不能因为 006 canary 已完成就跳过 011/012/007/009 的生产语义门禁。

## 6. 统一完成门禁

只有同时满足以下条件，才可以把目标架构标记为 Implemented：

1. 真实 /chat 默认进入 Runtime-owned Decision Loop，且 Graph 不再拥有内部 ToolNode 循环。
2. ModelGateway 是主模型唯一边界，所有 provider usage、timeout、cancel、error 都能映射到 Runtime terminal contract。
3. Decision、Invocation、Result、Event、Trace 使用稳定、可关联、可 replay 的 Run/Invocation/sequence ID。
4. EventStore 是 SSE、history、replay 的唯一事实源，API 不重新创造生命周期事件。
5. ResultNormalizer 在模型、SSE、Trace、Memory 之前统一执行 schema、大小、redaction 和 provenance 处理。
6. Run 在取消、超时、断线、worker crash、provider timeout 和 unknown outcome 下都有唯一可审计的终态或人工核查状态。
7. 所有启用的 Capability、Tool、MCP、Workflow、Subagent 和 specialist 入口只能经过 Runtime → Dispatcher。
8. Provider endpoint 在非 local 模式下默认 DNS/私网/redirect/port/host fail-closed，并有认证与 egress 边界。
9. 真实 API fake-provider/tool Acceptance、后端测试、Ruff、前端 lint/test/typecheck/build、Eval 和 git diff --check 都有本轮真实退出码。
10. 完整未提交 diff 的 Review verdict 为 pass，没有 blocker、critical、high 或未处理 medium finding；回滚方式明确。

## 7. Deferred 与不在本轮范围

- 生产数据库迁移、生产部署和生产外部副作用不属于文档规划的授权范围。
- SQLite single-worker 可以继续作为 local adapter，但必须明确禁止伪装为多 worker recovery。
- 不在完成 canonical contract 前删除 legacy compatibility adapter；但未迁移且启用的路径必须 fail-closed。
- 不以新增空接口、永久 TODO、关闭 redaction、删除失败测试或伪造 provider/tool 结果来满足门禁。

## 8. 回滚原则

- 在 default cutover 前，保留已经验证过的 compatibility flag；回滚只能回到仍经过 Dispatcher/Policy 约束的路径。
- 不删除已写入的 canonical Run/Event/Invocation 数据，不用 SSE 最后一条消息推断真实状态。
- 发现 unknown side effect 时暂停自动 retry 和新 Run，进入对账、compensation 或人工核查路径。
- 当前工作树存在未提交变更，任何回退动作必须先识别文件归属、保存 patch，并使用显式文件列表；禁止 git reset --hard 或宽范围 git restore。
## 9. BATCH-20—BATCH-26 closure assessment (2026-08-02)

The remaining closure batches have now completed in dependency order, each with an execution record and `Review verdict: pass`. The verified maturity is:

```text
Level 4 — Runtime-owned primary path with fail-closed compatibility boundaries
```

This is a claim about the enabled primary deployment path, not a claim that every historical class has been deleted or that SQLite is a shared multi-worker adapter.

- `/chat` defaults to `AgentRuntime.stream_decision()`; the primary path does not instantiate `ChatWorkflow` or its LangGraph `ToolNode` loop.
- Primary capability invocation, MCP calls, normalization, cancellation, timeout, canonical SSE/replay, and provider endpoint policy are covered by source-backed tests. The main API fake-provider Eval covers ordinary response, tool invocation, denial, trusted approval enforcement, provider failure, tool timeout, cancellation-before-model, unknown outcome, prompt-injection authority rejection, and the default Workflow resume fail-closed path.
- Specialist and scheduled specialist entrypoints fail closed with a Dispatcher-required error until a Dispatcher-backed subagent contract is available. The LangGraph compatibility implementation remains reachable only through explicit rollback or isolated compatibility tests.
- The explicit rollback is `HARNESS_PRIMARY_DECISION_LOOP_ENABLED=false`; it must not disable policy, approval, timeout, cancellation, idempotency, redaction, audit, or canonical persistence.

Evidence: `docs/harness-execution/BATCH-20-execution.md` through `BATCH-26-execution.md`; final BATCH-26 backend `728 passed, 1 skipped, 165 warnings`, Ruff pass, Fast Eval `9/9`, Observability Eval `14/14`, frontend lint `0 errors/99 warnings`, typecheck pass, Vitest `41/41`, build pass, and `git diff --check` pass.

Deferred risks are limited to the declared single-worker SQLite adapter and specialist availability until the subagent migration is implemented. No enabled production entrypoint is permitted to bypass Dispatcher, and no multi-worker recovery claim is made.
