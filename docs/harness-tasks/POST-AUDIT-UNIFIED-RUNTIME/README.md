# POST-AUDIT-UNIFIED-RUNTIME 任务规划

> 状态：planned；不是正在执行的 Batch。
> 来源：[`docs/harness-audit/12-post-batch13-current-audit.md`](../../harness-audit/12-post-batch13-current-audit.md)。
> 目标：把当前已经存在的 Harness 组件收口到主 LLM 执行链路，使 `AgentRuntime` 成为唯一 Run 控制者。
> 兼容原则：先建立 adapter/contract seam，再逐步迁移 Legacy LangGraph Tool；不通过删除测试、关闭 redaction 或移除失败路径制造通过结果。

## 1. 目标架构

```text
API / Scheduler
    ↓ trusted RunRequest + ExecutionContext
AgentRuntime / RunCoordinator
    ↓ ContextCompiler
ModelGateway
    ↓ AgentDecision
DecisionParser / PolicyEngine
    ↓ InvocationRequest
Dispatcher + CapabilityRegistry
    ↓
Capability / Tool / Workflow / MCP adapter
    ↓ InvocationResult
ResultNormalizer + EventWriter + Trace
    ↓
继续 Run Loop 或生成 RunResult
```

LangGraph 可以保留，但只能成为模型和状态适配器：

```text
LangGraph = propose / resume / stream adapter
Runtime   = policy / dispatch / state / budget / terminal owner
```

## 2. 任务依赖

```text
001 Primary Decision / Dispatcher
  ↓
002 Runtime Ownership / Cancellation / Recovery
  ↓
003 Capability / Tool / Side-Effect Convergence
  ↓
004 Model / Memory / Deployment Convergence
  ↓
005 Primary-Path Acceptance / Review / Hardening
```

任务之间可以在同一个 Codex 会话内连续执行，但每个任务仍必须：

1. 先完成 preflight 和基线验证。
2. 只修改任务列出的范围。
3. 先补失败测试，再实现最小改动。
4. 验证后审查完整 diff。
5. Review 有 Finding 时暂停实施，进入 remediation，再重新验证。

## 3. 全局允许和禁止范围

### 允许范围

- `backend/app/harness/`
- `backend/app/agents/` 中的 Runtime adapter、Graph adapter、Tool adapter
- `backend/app/capabilities/`
- `backend/app/mcp_server/` 的协议 adapter 和 policy wiring
- `backend/app/api/v1/agent.py` 的 Run/cancel/replay wiring
- 与任务直接对应的 `backend/app/memory/`、`backend/app/trace/`、`backend/app/evaluation/`
- 对应后端测试、Eval fixture、CI gate、部署配置和文档

### 禁止范围

- 未经任务明确要求改变 Domain Service 业务规则。
- 未经独立迁移任务批准修改生产数据库数据。
- 删除 `ALL_TOOLS`、旧 Graph、旧 Memory 或兼容 API，除非 parity test 已通过且任务明确允许。
- 让模型参数携带 `user_id`、tenant、principal、db、token、文件句柄或任意客户端。
- 将完整 prompt、CoT、Secret、Token、raw provider payload 或完整用户数据写入日志、Trace、Eval fixture。
- 以 feature flag 形式保留可绕过 Policy/Authorization 的生产写路径。
- 创建虚假的 `BATCH-XX-execution.md` 或填写未实际运行的测试结果。

## 4. 任务清单

| 任务 | 目标 | 严重度 | 依赖 | 主要输出 |
|---|---|---:|---|---|
| [TASK-POST-AUDIT-001](TASK-POST-AUDIT-001.md) | 主聊天接入 Decision / Dispatcher | P1 | 当前 contracts、Registry、Policy | 主路径结构化 Decision 和 Invocation |
| [TASK-POST-AUDIT-002](TASK-POST-AUDIT-002.md) | Runtime 唯一控制、取消、恢复 | P1 | 001 | stream/execute/scheduler 统一 Run 生命周期 |
| [TASK-POST-AUDIT-003](TASK-POST-AUDIT-003.md) | Capability/Tool/MCP/写操作收口 | P1 | 001、002 | 所有 side effect 经过统一边界 |
| [TASK-POST-AUDIT-004](TASK-POST-AUDIT-004.md) | Model、Memory、部署和运行时一致性 | P1 | 001、002 | usage/budget/namespace/checkpoint/migration 收口 |
| [TASK-POST-AUDIT-005](TASK-POST-AUDIT-005.md) | 主路径 Acceptance、Review、Hardening | P1 | 001～004 | 真实主路径测试和最终 review gate |

## 5. 跨任务契约

### AgentDecision

```text
schema_version: v1
decision_id: immutable
run_id: immutable
action: invoke | respond | finish
capability: canonical name, required for invoke
capability_version: required for invoke
arguments: public schema only
```

模型不得提供：

```text
user_id / principal_id / tenant_id / db / token / approval_state
```

### InvocationRequest

```text
invocation_id
run_id
capability
capability_version
principal_id: server-derived, not model-owned
input_hash
idempotency_key: required for side effects
deadline / retry policy / approval reference
```

### InvocationResult

```text
status: succeeded | failed | denied | cancelled | timeout
safe output envelope
error_code
retryable
usage / latency / provider metadata
artifact references, never unbounded raw payload
```

## 6. 全局验收门槛

只有同时满足以下条件，才能把整体计划标记为完成：

- 主聊天 fake provider/tool 测试真实经过 `AgentRuntime → DecisionParser → Policy → Dispatcher`。
- 任意 Policy deny、身份伪造、非法 schema、缺少幂等 Key 的写操作都不会触发 Domain Service。
- stream、execute、scheduler 只产生一个权威 terminal Run 状态。
- cancel、timeout、provider error、tool error、budget exceeded 都有结构化状态和事件。
- SSE 断线只重放已持久化事件，不重复执行已完成 Invocation。
- Worker 重启、checkpoint lease 和 shared store 有可重复测试或明确的单 Worker 限制。
- 主模型 usage/cost/latency 进入 RunBudget 和 Trace；unknown usage 不伪装为 0。
- Memory 使用同一 Run namespace，事实提取有明确预算和 Trace 归属。
- 完整后端测试、ruff、相关 Eval、前端协议回归和 `git diff --check` 有真实退出码。
- Review verdict 为 `pass`，无 blocker/critical/high Finding，无未处理 medium Finding。

## 7. 回滚策略

回滚必须是代码和状态双重可执行的：

1. 保留只读 Legacy adapter 作为兼容路径，但不可绕过写操作 Policy。
2. 新 Dispatcher 可以按 capability allowlist 逐步启用；默认 deny 未迁移的 side effect。
3. 已写入的 Run/Event/Invocation schema 不删除，通过兼容读取映射旧版本。
4. 外部副作用发生不确定时，返回 `attention_required`，不得自动重复执行。
5. 迁移、checkpoint 和 production deployment 的回滚由独立发布流程批准，不在普通代码任务中执行。
