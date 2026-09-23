# Post-BATCH-13 后端 Harness 当前审计

> 状态：源码审计快照，不代表本文件已对应任何正在执行的 Batch。
> 审计基线：分支 `feature-harness`，HEAD `65d48429144c97699862494807e31fb9f1a591e2`。
> 审计日期：2026-08-01 Asia/Shanghai。
> 本文件用于替代旧审计中与 BATCH-01～13 实现不一致的当前状态描述；旧文件保留为历史基线。

## 1. 审计目标和判定方法

本次审计按以下理想链路判断后端是否真正形成统一 Harness：

```text
RunRequest
  → Runtime 唯一控制 Run
  → ContextCompiler
  → ModelGateway
  → 结构化 AgentDecision
  → DecisionParser / Policy / Authorization
  → InvocationDispatcher
  → Capability / Tool / Workflow / MCP
  → InvocationResult
  → Event / State / Trace
  → 继续 Loop 或 RunResult
```

判定规则：

1. 类、契约或测试名称存在不等于真实主路径已使用。
2. 以 API、Scheduler、MCP 和直接 HTTP 写入口的实际调用链为准。
3. 只把能由当前源码、测试或部署配置证明的能力标记为“已实现”。
4. 未确认的部署、网络和生产 Provider 行为标记为“未验证”，不伪造为通过。

## 2. 当前事实摘要

### 2.1 交互聊天主路径

```text
POST /chat
  → AgentTask
  → AgentRuntime.stream()
  → RunCoordinator
  → FeatureFlagRoutingAdapter / LangGraphAdapter
  → ChatWorkflow
  → LangGraph think → ToolNode → think → speak
  → SSE
```

`AgentRuntime.stream()` 默认创建 `RunCoordinator`，并接入预算、取消、Run/Event persistence 和 Trace。[`backend/app/harness/runtime.py:207-378`](../../backend/app/harness/runtime.py#L207)

但 `RunCoordinator` 当前包装的是完整的 `adapter.stream()`；它主要观察 chunk、累计预算和持久化事件，不负责把模型 Decision 转成受 Policy 约束的 Invocation。[`backend/app/harness/coordinator.py:56-158`](../../backend/app/harness/coordinator.py#L56)

`ChatWorkflow` 仍直接创建 LangGraph `ToolNode`、绑定 `ALL_TOOLS`，并直接调用 LangChain model 的 `ainvoke()`。[`backend/app/agents/graph.py:102-185`](../../backend/app/agents/graph.py#L102)

### 2.2 非流式和 Scheduler 路径

`AgentRuntime.execute()` 直接调用 `self.adapter.run(state)`，没有复用 `RunCoordinator`。[`backend/app/harness/runtime.py:115-205`](../../backend/app/harness/runtime.py#L115)

Proactive Scheduler 通过 `selected_runtime.execute(agent_task)` 执行任务，因此与交互式 `stream()` 形成第二套 Run 生命周期。[`backend/app/harness/scheduler/execution.py:72-124`](../../backend/app/harness/scheduler/execution.py#L72)

### 2.3 已存在但未成为主路径的控制组件

以下组件已经存在：

- `AgentDecision`、`InvocationRequest`、`InvocationResult` 等版本化契约；
- `CapabilityRegistry`；
- `PolicyEngine`；
- `CapabilityAdapter`；
- `ModelGateway`；
- `ResultNormalizer`；
- MCP Exposure 和 MCP Policy。

但是源码中没有一个主路径 `DecisionParser + Dispatcher` 把这些组件串成每次模型调用的必经链路。`AgentDecision` 目前主要是契约，不是交互聊天实际的模型输出边界。[`backend/app/harness/contracts.py:37-91`](../../backend/app/harness/contracts.py#L37)

### 2.4 持久化、SSE 和恢复

当前已有：

- `RunStore`；
- `EventStore`；
- `GET /runs/{run_id}`；
- `GET /runs/{run_id}/events`；
- `Last-Event-ID` / `after` 查询；
- Run/Invocation/Event 的用户范围检查。

但当前没有独立的 durable cancel API。前端停止操作主要是 abort 当前 HTTP 请求，取消信号是请求内的 `CancellationToken`。[`backend/app/api/v1/agent.py:293-319`](../../backend/app/api/v1/agent.py#L293)

Checkpoint 默认使用本地 SQLite 路径，compose 没有证明后端容器使用共享持久化卷。[`docker-compose.yml:77-78`](../../docker-compose.yml#L77)

## 3. 成熟度判定

| 能力 | 当前状态 | 判定 |
|---|---|---|
| Run/Decision/Invocation/Event 契约 | 契约存在，主路径使用不完整 | Partial |
| Runtime 唯一控制 Run | stream 有 Coordinator，execute/Scheduler 另有路径 | Fail |
| LLM 只产生结构化 Decision | 主 Graph 仍产生 LangChain tool call 并由 ToolNode 执行 | Fail |
| Registry/Schema/Policy 统一 | Capability/MCP/Legacy Tool 并存，主聊天未统一 | Fail |
| 身份可信注入 | CapabilityAdapter 和 MCP 边界较好，主 Legacy Tool 未统一 | Partial |
| Invocation/Result 统一 | persistence 有 Invocation，工具执行结果仍有 legacy chunk | Partial |
| 预算/超时/取消 | Coordinator stream 有；主模型 usage 不完整，取消不 durable | Partial |
| Run/Event 持久化 | 已实现并有 replay 基础 | Partial |
| 重启恢复/多 Worker | SQLite checkpoint 和部署责任未证明 | Fail |
| ModelGateway | synthesis 和 provider adapter 存在，主推理未统一 | Partial |
| Memory trust/provenance | 已有较完整实现，但 namespace/预算存在缺口 | Partial |
| Trace/Eval | 已有实现和测试，主路径 gate 仍需加强 | Partial |

**结论：严格 Level 2 未通过；处于 Level 2 partial；不属于 Level 3。**

## 4. 当前 Gap 注册表

| ID | 严重度 | Gap | 当前证据 | 影响 |
|---|---|---|---|---|
| G-POST-01 | P1 / High | Runtime 与 Graph 共同拥有 Agent Loop | `RunCoordinator` 包装 adapter；Graph 自己执行 `think/tools/speak` | 无法保证唯一控制者和统一终止状态 |
| G-POST-02 | P1 / High | Decision/Policy/Dispatcher 未接入主聊天 | `ToolNode(ALL_TOOLS)` 直接执行；无主路径 DecisionParser/Dispatcher | 模型工具调用可能绕过统一授权和 Invocation |
| G-POST-03 | P1 / High | 主模型调用未统一进入 ModelGateway | Graph 直接 `ainvoke()`；Gateway 主要 synthesis | usage/cost/timeout/provider error 不完整 |
| G-POST-04 | P1 / High | stream、execute、Scheduler 有多个执行控制面 | `runtime.stream()` 与 `runtime.execute()` 分离 | Scheduler 与交互聊天状态、预算、恢复语义不一致 |
| G-POST-05 | P1 / High | durable cancel/recovery/shared checkpoint 不完整 | 无 cancel API；本地 token；SQLite checkpoint 无共享部署证据 | 断线、重启、多 Worker 可能产生未知状态或重复执行 |
| G-POST-06 | P1 / Medium | Result、SSE、replay 的安全视图不统一 | Graph 发送原始工具输出，EventStore 保存安全摘要 | 前端 replay 不等价，外部数据边界不统一 |
| G-POST-07 | P1 / Medium | Schedule HTTP 写入口绕过幂等层 | `schedules.py` 直接调用 `ScheduleService` | 重试或重复提交可能造成重复写入/状态竞争 |
| G-POST-08 | P1 / Medium | Memory namespace 与 Run namespace 不一致 | Graph 使用 `run_id`，Memory 固定 `checkpoint_ns=""` | 当前 Run 可能读不到或提取不到对应上下文 |
| G-POST-09 | P1 / Medium | Memory extraction 不在主 Run budget 内 | Chat 结束后单独执行事实提取模型调用 | 预算、取消、Trace 和失败语义不完整 |
| G-POST-10 | P1 / Medium | Provider endpoint 的 DNS/egress 边界未充分证明 | 代码做 URL/IP 文本检查，未证明解析后私网阻断 | 可能存在 SSRF/重定向/私网访问风险，需部署验证 |
| G-POST-11 | P1 / Medium | Alembic、`create_all`、部署启动责任未统一 | 应用初始化和 migration 同时存在 | fresh DB、升级和回滚可能出现 schema 漂移 |
| G-POST-12 | P2 | 审计文档与当前源码事实漂移 | 旧摘要仍描述 qB 未认证和 Run/Event 不存在 | 后续 Codex 可能按错误 Gap 重复修改或误判完成 |

## 5. 已关闭或需要重分类的旧 Gap

| 旧 Gap | 当前状态 | 说明 |
|---|---|---|
| G-P0-01 qB 未认证写入 | 已关闭/需新证据复核 | 当前 qB route 使用 `check_qb_access`、allowlist、IdempotencyStore；旧审计结论不能直接沿用。 |
| G-P1-03 无 Run/Event/SSE replay | 部分关闭 | Run/Event、GET projection、Last-Event-ID 已存在；取消、恢复和完整 replay 仍未完成。 |
| G-P1-04 qB 无幂等/补偿 | 部分关闭/主要已关闭 | qB 已有幂等和补偿；Schedule HTTP 写入口仍需单独处理。 |
| G-P1-10 Memory 无 provenance | 主要关闭 | provenance/trust 已实现；namespace 和 extraction budget 仍是新 Gap。 |
| G-P1-06/P1-09 observability/Eval | 部分关闭 | Trace/Eval 基础和 BATCH-13 gate 已有；主 LLM Decision/Dispatcher 集成测试仍缺。 |

## 6. 目标不变量

后续重构完成后必须满足：

1. `AgentRuntime` 是唯一 Run 控制者；Graph、Scheduler、MCP adapter 不拥有第二套 Run 状态机。
2. LLM 只能返回 `AgentDecision`，不能直接获得 Python Tool 或 Domain Service 执行权限。
3. 每个工具调用都生成 `InvocationRequest` 和 `InvocationResult`。
4. 所有 side effect 都在 Policy、授权、审批、幂等、超时、取消和审计边界内执行。
5. `user_id`、tenant、principal、db session 和资源范围只能由可信 Runtime/Domain 注入。
6. SSE 是 Event Store 的 projection，不是 Run 状态的唯一来源。
7. Tool/MCP/RSS/网页/Memory 输出默认标记为不可信数据，并经过 ResultNormalizer。
8. 主模型 usage、latency、cost 和 provider error 都进入 RunBudget/Trace/Eval。
9. Run、Invocation、Event、Trace、Eval 使用同一组稳定 ID 和 schema version。
10. 所有迁移阶段保留兼容路径，但不能让旧路径绕过安全边界。

## 7. 改进计划入口

详细任务位于：[`docs/harness-tasks/POST-AUDIT-UNIFIED-RUNTIME/README.md`](../harness-tasks/POST-AUDIT-UNIFIED-RUNTIME/README.md)

建议顺序：

```text
TASK-POST-AUDIT-001 主路径 Decision / Dispatcher
        ↓
TASK-POST-AUDIT-002 Runtime 唯一控制 / Cancel / Recovery
        ↓
TASK-POST-AUDIT-003 Capability / Tool / Side Effect 收口
        ↓
TASK-POST-AUDIT-004 Model / Memory / Deployment 收口
        ↓
TASK-POST-AUDIT-005 主路径 Acceptance / Review / Hardening
```

没有活动 Batch 时，不创建 `BATCH-14-execution.md`；开始实际执行后，按 `docs/harness-execution/TEMPLATE.md` 创建对应记录。
