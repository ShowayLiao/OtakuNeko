# TASK-POST-AUDIT-006：主聊天 Runtime-owned Decision Loop

## 目标

为主聊天建立从 LangGraph 内部 `think → tools → think → speak` 循环迁移到 AgentRuntime 控制的结构化 Decision Loop 的可回滚 canary：

```text
AgentRuntime
  → ModelGateway.infer
  → DecisionParser
  → Dispatcher
  → InvocationResult
  → AgentRuntime 决定继续或结束
```

LangGraph 兼容路径可以暂时保留。TASK-006 先以显式 canary 启用新路径；在 TASK-007 完成 canonical durable pipeline 前，旧路径仍是默认兼容路径，不得把 canary 记为完整迁移或让旧路径绕过 Dispatcher。

## 依赖

- POST-AUDIT-001～005 已完成并通过 Review。
- `docs/architecture/agent-runtime-target-architecture.md` 已写入目标拓扑。
- `backend/app/harness/model_gateway.py`、`decision_parser.py`、`dispatcher.py` 和 `runtime.py` 的契约已存在。

## 允许修改

- `backend/app/api/v1/agent.py`
- `backend/app/harness/runtime.py`
- `backend/app/harness/model_gateway.py`
- `backend/app/harness/contracts.py`
- `backend/app/harness/decision_parser.py`
- `backend/tests/acceptance/`
- `backend/tests/harness/`
- 本任务 execution record

## 禁止修改

- 不改变 Domain Service 的业务规则。
- 不删除 LangGraph 兼容路径或既有 SSE event，除非同一任务有 parity test 和 rollback flag。
- 不修改生产数据库数据、运行生产迁移或升级无关依赖。
- 不允许模型参数携带 user、tenant、principal、scope、db、token 或 approval authority。

## TDD 契约测试

实现前必须新增失败测试，至少覆盖：

1. 主 Runtime 入口连续执行 `invoke → respond` 两轮，并且 Tool 只由 Dispatcher 执行。
2. `respond/finish` 不触发 Dispatcher，且只产生一个 terminal RunResult。
3. 非法 Decision、错误 run_id、模型伪造 authority 字段在执行前失败。
4. Dispatcher 返回 denied、timeout、cancelled、budget exceeded 时，Runtime 不再偷偷开始下一轮。
5. provider error 和 client cancellation 产生明确 terminal 状态。
6. canary 启用时不调用 LangGraph ToolNode，且不会在运行中隐式回退；canary 关闭时只能显式选择已标记的兼容路径。
7. 同一 Run 的 Decision、Invocation、Event 和 Result 使用一致的 run_id/trace_id。

## 实现要求

- 增加流式 Decision Loop 或等价的 Runtime-owned execution API，不能只把 `execute_decision()` 留在测试路径。
- ModelGateway 负责 provider-neutral model call、usage、cost、timeout 和 safe provider error。
- DecisionParser 是唯一模型输出到 `AgentDecision` 的转换入口。
- Dispatcher 是唯一 Capability/Tool/MCP/Workflow/Subagent 执行入口。
- Runtime 负责消息上下文推进、Budget/Cancellation/Deadline、terminal state 和事件投影。
- 兼容路径必须有明确的禁用/回滚配置。本任务先以
  `HARNESS_PRIMARY_DECISION_LOOP_ENABLED=true` 作为显式 canary；由于
  canonical durable Event/Invocation pipeline 尚在 TASK-POST-AUDIT-007，默认值
  暂保持 `false`。只有 TASK-POST-AUDIT-007 完成持久化与 SSE projection 验证后，
  才能把默认值切换为 `true`，不得把 canary 误记为完整迁移。

## 验收

- 主聊天 fake provider/tool 测试从 API 或 Runtime 主入口开始，而不是直接实例化 adapter。
- 旧只读回答协议和 SSE 消费协议保持兼容，或有明确版本/迁移说明。
- 运行任务指定的后端测试、Ruff、前端协议回归、Eval 和 `git diff --check`。
- Review verdict 为 `pass`，无 blocker/critical/high 或未处理 medium finding。

## 回滚

通过 `HARNESS_PRIMARY_DECISION_LOOP_ENABLED=false` 恢复旧 LangGraph adapter；不得删除新 Decision/Dispatcher 契约、测试或持久化数据。回滚开关恢复后必须再次运行主路径 parity tests。
