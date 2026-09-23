# UNIFIED-RUNTIME-CONSOLIDATION 任务规划

> 目标：将主聊天从“Runtime 外层治理 + LangGraph 内部循环”迁移为“AgentRuntime 唯一控制 Decision Loop”。
>
> 当前状态：TASK-POST-AUDIT-006～013 已按依赖顺序在 BATCH-19～26 完成；TASK-POST-AUDIT-007～010 的统一 Runtime closure 已在 BATCH-22～26 完成。启用的主路径已切换为 Runtime-owned primary path；LangGraph 兼容回滚、未迁移 specialist 和 SQLite 单 worker 边界仍明确保留。每个已执行 Batch 都有对应的 `BATCH-XX-execution.md`。

## 1. 目标架构

```text
AgentRuntime
  → ContextManager
  → ModelGateway
  → DecisionParser
  → Policy / Authorization
  → Dispatcher
  → InvocationResult
  → Event / State persistence
  → continue or terminal RunResult
```

LangGraph 可以保留为兼容 adapter，但不能继续拥有第二套 Run 控制面、Tool 执行权或 terminal state 决策权。

## 2. 依赖顺序

| 任务 | 目标 | 依赖 | 状态 |
|---|---|---|---|
| TASK-POST-AUDIT-006 | 主聊天 Runtime-owned Decision Loop | POST-AUDIT-001～005 | BATCH-19 canary completed |
| TASK-POST-AUDIT-007 | Canonical Invocation / Result / Event pipeline | 006 | BATCH-22 completed |
| TASK-POST-AUDIT-008 | ContextManager 与 Memory/Provider trust boundary | 006、007 | BATCH-23 completed |
| TASK-POST-AUDIT-009 | Shared checkpoint、durable cancellation 与 worker recovery | 007、008 | BATCH-24 completed |
| TASK-POST-AUDIT-010 | Legacy bypass 退役、真实主 API Eval 与最终 hardening | 006～009 | BATCH-26 completed |

一次只实施一个任务；前置任务未通过测试和 Review 时，不得修改后续任务的实现范围。

## Target Architecture Closure 补充任务

TASK-POST-AUDIT-006 已完成 Runtime-owned Decision Loop canary；根据 [14-target-architecture-gap-audit.md](../../harness-audit/14-target-architecture-gap-audit.md)，BATCH-20～26 已补齐模型取消、结果契约、Provider 安全边界、canonical persistence、ContextManager、shared recovery 和 legacy retirement。

| 任务 | 目标 | 依赖 | 执行 Batch |
|---|---|---|---|
| TASK-POST-AUDIT-011 | ModelGateway cancellation、timeout 与 provider error hardening | 006 | BATCH-20 completed |
| TASK-POST-AUDIT-012 | ResultNormalizer、schema、safe output 与 authority contract | 006、011 | BATCH-21 completed |
| TASK-POST-AUDIT-013 | Provider SSRF、egress allowlist 与 endpoint authorization | 011 | BATCH-25 completed |

这些 Batch 已完成真实 Preflight、Implementation、Verification 和 Review；对应 execution record 是当前批次状态的依据。

目标架构的完整依赖顺序和主 API Eval 门禁见 [TARGET-ARCHITECTURE-CLOSURE-EXECUTION-PLAN.md](../../harness-execution/TARGET-ARCHITECTURE-CLOSURE-EXECUTION-PLAN.md)。

## 3. 全局不变量

- AgentRuntime 是一次 Run 的唯一控制者。
- LLM 只能输出结构化、版本化 Decision，不能直接获得 Python Tool 或 Domain Service 权限。
- DecisionParser、Policy 和 Dispatcher 是模型输出到执行的唯一边界。
- user、tenant、principal、scope、db session、approval 和 resource ownership 由可信 Runtime/Domain 注入。
- 所有写操作必须处理授权、审批、超时、取消、重试、幂等、审计、补偿或 unknown outcome。
- SSE/WebSocket 只能投影 durable Run Event，不是 Run 状态源。
- 不删除兼容路径，除非 parity test、rollback path 和任务范围明确允许。
- 不通过关闭 redaction、删除失败测试或伪造 provider/tool 结果制造通过。

## 4. 共同验收门槛

- 失败契约测试先于实现代码。
- 主 API 或 Runtime 真实入口经过 `ModelGateway → DecisionParser → Dispatcher`。
- 每次模型调用、Invocation、Event 和 terminal Result 使用同一 Run 关联和稳定 ID。
- 取消、超时、Budget、provider error、tool error、client disconnect 和 recovery 有确定性状态。
- side effect 默认 fail closed，并验证幂等 key conflict 与 unknown outcome。
- `git diff --check`、后端测试、Ruff、前端协议测试和适用 Eval 有真实退出码。
- Review 完整未提交 diff；无 blocker/critical/high 或未处理 medium finding。
