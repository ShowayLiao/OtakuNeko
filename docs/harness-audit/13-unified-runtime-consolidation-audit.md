# Unified Runtime Consolidation 当前审计

> 审计日期：2026-08-01
>
> 状态：基于当前源码的持续审计；BATCH-19 / TASK-POST-AUDIT-006 已增加 canary，但不代表目标已经实现。
>
> 目标架构：[agent-runtime-target-architecture.md](../architecture/agent-runtime-target-architecture.md)

## 1. 判定结论

前置的 POST-AUDIT-001～005 已建立 Decision、Dispatcher、Budget、Cancellation、Memory、Checkpoint 和 Acceptance 基础，但主聊天仍然是兼容架构：

```text
默认路径：
API
  → AgentRuntime.stream()
    → RunCoordinator
      → LangGraphAdapter
        → ChatWorkflow: think → tools → think → speak

显式 canary：
API
  → AgentRuntime.stream_decision()
    → ModelGateway → DecisionParser → Dispatcher
    → InvocationResult → terminal Event
```

严格按照目标架构判定，当前仍是 **Level 2 partial / Runtime-governed compatibility architecture**，尚未达到“AgentRuntime 唯一控制内部 Decision Loop”；canary 默认关闭，且 canonical durable Event/Invocation pipeline 尚未接入该路径。

## 2. 当前事实证据

| 目标不变量 | 当前事实 | 判定 |
|---|---|---|
| Runtime 是唯一 Run 控制者 | 默认 `AgentRuntime.stream()` 创建 `RunCoordinator`，但 `ChatWorkflow` 仍控制模型/Tool 循环；canary `stream_decision()` 已由 Runtime 控制 | Partial / canary |
| LLM 只返回 Decision | canary 经过 `ModelGateway.infer()` 和 `DecisionParser`；默认主 Graph 仍直接调用 LangChain `ainvoke()` | Partial / default path fail |
| 所有执行经过 Dispatcher | Graph ToolNode 使用 proposal wrapper，主 API 的 proposal handler 会进入 Dispatcher；旧适配器和 specialist 仍需统一验证 | Partial |
| trusted Context 由 Runtime 注入 | `ExecutionContext`、allowlist 和 run scope 已存在；没有独立 ContextManager 统一组装所有模型上下文 | Partial |
| Result/Event 只有一条规范路径 | `RunEvent`、`RunStore`、`EventStore`、Dispatcher events 和 SSE adapter 并存，Invocation ID 归一化仍需收口 | Partial |
| 断线、重启、多 worker 可恢复 | SSE replay 和 SQLite checkpoint 存在；共享多 worker adapter 与取消传播未完成 | Fail |

关键源码路径：

- `backend/app/api/v1/agent.py` 默认保留 `FeatureFlagRoutingAdapter(enabled=False)` 与 `LangGraphAdapter` 兼容路径；`HARNESS_PRIMARY_DECISION_LOOP_ENABLED=true` 时进入 `AgentRuntime.stream_decision()` canary。
- `backend/app/agents/graph.py` 编译 `think -> tools -> think -> speak`，并在 `think` 中直接执行 LangChain model `ainvoke()`。
- `backend/app/harness/runtime.py::stream_decision()` 已包含目标形态的结构化循环，并由主聊天 API 的显式 canary 调用；默认仍未切换。
- `backend/app/harness/dispatcher.py` 已提供 Capability、Policy、Approval、幂等、Budget、Timeout 和 Cancellation 边界。

## 3. Gap 注册表

| ID | 严重度 | Gap | 影响 | 首个后续任务 |
|---|---|---|---|---|
| G-UNIFIED-01 | High | 默认主聊天仍由 LangGraph 持有内部循环；Runtime-owned loop 目前仅 canary | Runtime 默认路径仍无法唯一决定继续、重试和终止 | TASK-POST-AUDIT-007 / 010 |
| G-UNIFIED-02 | High | 默认主聊天模型调用仍绕过 ModelGateway | usage/cost/error/Decision schema 默认路径不能统一归因 | TASK-POST-AUDIT-010 |
| G-UNIFIED-03 | High | `stream_decision()` 已接入 canary，但尚未成为默认且 durable 的生产主入口 | 目标循环仍受 persistence/parity gate 约束 | TASK-POST-AUDIT-007 |
| G-UNIFIED-04 | Medium | 没有统一 ContextManager | Memory、Tool schema、trusted scope 和当前 State 组装分散 | TASK-POST-AUDIT-008 |
| G-UNIFIED-05 | High | Invocation/Event/Result 仍有多套投影 | 断线恢复、审计和幂等关联可能出现 ID 分叉 | TASK-POST-AUDIT-007 |
| G-UNIFIED-06 | High | Legacy Graph、specialist 和 MCP 兼容入口尚未完成退役 | 仍需证明没有旁路 Dispatcher 的启用路径 | TASK-POST-AUDIT-010 |
| G-UNIFIED-07 | High | shared checkpoint/cancellation 尚未完成 | 多 worker、重启和未知副作用状态无法完整证明 | TASK-POST-AUDIT-009 |
| G-UNIFIED-08 | Medium | 目标架构缺少真实主 API Decision Loop Eval | Acceptance 主要验证 Runtime/adapter，不足以证明生产入口迁移 | TASK-POST-AUDIT-010 |

## 4. 后续迁移顺序

1. **TASK-POST-AUDIT-006**：已在 BATCH-19 建立 Runtime-owned Decision Loop canary，保留明确的 legacy rollback flag；默认切换仍待后续持久化门禁。
2. **TASK-POST-AUDIT-007**：统一 Invocation、Result、Event、Trace 和 SSE projection 的 canonical ID 与持久化顺序。
3. **TASK-POST-AUDIT-008**：建立 ContextManager，统一 trusted context、Memory provenance、Tool schema 和模型可见数据。
4. **TASK-POST-AUDIT-009**：实现 shared checkpoint、durable cancellation、lease/recovery 和多 worker 部署验证。
5. **TASK-POST-AUDIT-010**：关闭 legacy bypass，补真实主 API Acceptance/Eval，并重新判定 Harness maturity。

每个任务都必须先写失败契约测试；未完成的任务不得在架构文档或执行记录中写成已实现。
