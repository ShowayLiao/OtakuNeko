# TASK-POST-AUDIT-007：Canonical Invocation / Result / Event Pipeline

## 目标

把 TASK-POST-AUDIT-006 的 Runtime-owned Decision Loop 接入唯一的持久化事实流：

```text
AgentRuntime
  → Decision / Dispatcher
  → InvocationResult
  → canonical RunEvent + durable Invocation
  → SSE / history / replay projection
```

SSE 只能订阅和投影 canonical Run Event，不能在 API 层重新创造 Run、Invocation、Result 或终态。

## 依赖

- TASK-POST-AUDIT-006 已通过 Review，且 canary 路径可由 `HARNESS_PRIMARY_DECISION_LOOP_ENABLED=true` 启动。
- 复用现有 `RunStore`、`EventStore`、`RunEvent`、`AgentInvocation` 和 `AgentRun` 契约；除非源码证明字段不足，不新增数据库迁移。

## 允许修改

- `backend/app/harness/runtime.py`
- `backend/app/harness/coordinator.py`
- `backend/app/harness/persistence/`
- `backend/app/api/v1/agent.py`
- `backend/tests/acceptance/`
- `backend/tests/harness/`
- `backend/tests/evaluation/`
- 适用的前端 SSE projection 测试文件
- 本任务对应的 execution record

## 禁止修改

- 不删除旧事件名或在没有版本兼容说明的情况下改变 SSE payload。
- 不让 API、前端或 adapter 直接写 `AgentRun`/`AgentRunEvent`。
- 不重复持久化同一 Invocation、terminal Result 或 Event。
- 不把完整 prompt、provider raw payload、Secret、token 或完整 tool output 写入 Event。
- 不修改无关 Domain Service、依赖、生产迁移或部署环境。

## TDD 契约

实现前先增加失败测试，至少覆盖：

1. 一个 Run 的 `run.started → model/decision → invocation.started → invocation.completed → run.succeeded/failed` 只产生一条 canonical 序列。
2. 重复消费、重试和断线重放不会新增 Event 或 Invocation；相同 ID/sequence 的重复写必须幂等，相冲突 payload 必须失败关闭。
3. `RunResult.run_id`、`InvocationResult.invocation_id`、`RunEvent.invocation_id` 和 SSE `id` 可互相追溯。
4. EventStore 写入失败时 Run 不能伪造成功；Runtime 进入明确的持久化失败终态，并保留补偿/人工核查信息。
5. SSE 只从 `EventStore.list_after()` 投影；`Last-Event-ID`、越界 cursor、owner/thread scope 和 terminal replay 有测试。
6. redaction 对 model output、arguments、tool output、provider error 和 exception payload 生效。

## 实现要求

- Runtime 是唯一生成 canonical Run/Event 生命周期事实的组件。
- API 只负责认证、owner scope、订阅和 SSE 格式化。
- 事件序列分配、invocation 创建/结束、terminal transition 与幂等键必须在受控 persistence boundary 内完成。
- 将临时 stream event 与 durable event 的映射写成版本化代码契约，不能依赖事件名称猜测状态。
- 完成 canary 的 durable replay parity 后，才允许把 `HARNESS_PRIMARY_DECISION_LOOP_ENABLED` 默认值切换为 `true`。

## 验收

- 真实主 API fake provider/tool 测试证明一次调用只经过 Runtime → Dispatcher，并能从 EventStore 完整重放。
- 后端测试、Ruff、前端协议测试、typecheck、build、Eval 和 `git diff --check` 均有真实退出码。
- Review verdict 为 `pass`，无 blocker/critical/high 或未处理 medium finding。

## 回滚

保留已写入的 canonical Run/Event 数据，使用 canary flag 恢复 LangGraph 兼容投影；不得删除历史事件或绕过 owner scope。回滚后必须再次运行 duplicate-write、replay 和 terminal parity 测试。
