# Target Architecture Closure 执行计划

> 类型：后续任务执行计划，不是 Batch execution record。
>
> 当前状态：planned。
>
> 只有用户明确批准并开始具体 Batch 后，才创建对应的 BATCH-XX-execution.md；不得提前创建虚假的执行记录。

## 1. 目标

把当前 Level 2 partial / Runtime-governed compatibility architecture 推进到目标架构要求的可验收状态：

~~~text
User/API
  -> AgentRuntime (唯一 Run control plane)
  -> ContextManager
  -> ModelGateway
  -> DecisionParser
  -> Policy / Authorization
  -> Dispatcher
  -> Capability / Tool / MCP / Workflow / Subagent
  -> ResultNormalizer
  -> canonical Run / Invocation / Event / Trace
  -> SSE / history / replay projection
~~~

本计划的完成不是“类已经存在”或“单元测试已通过”，而是证明真实启用路径不再拥有第二个 Run loop，并且 Run 在取消、断线、重启和未知外部结果下有明确语义。

## 2. 权威资料与 Preflight

每个实际 Batch 开始前，按以下顺序阅读：

1. AGENTS.md；
2. docs/architecture/standard-agent-harness-reference.md；
3. docs/standard-agent-harness-reference-and-codex-audit-guide.md；
4. docs/harness-audit/14-target-architecture-gap-audit.md；
5. docs/harness-tasks/INDEX.md；
6. 当前任务包 README 和具体任务文件；
7. docs/code-review.md。

运行并记录：

~~~powershell
git status --short
git branch --show-current
git rev-parse HEAD
git log -5 --oneline
git diff --stat
git diff --check
~~~

必须识别：

- 工作树中已有修改的来源；
- 当前是否存在活动 Batch；
- 当前任务允许和禁止的文件；
- 测试、Ruff、前端 lint/typecheck/build、Eval 和启动检查命令；
- 是否存在无法确定幂等、补偿、回滚或 owner scope 的外部副作用。

遇到无法归属的修改、关键测试无法修复、权限越界、Secret 泄漏或未知副作用无法分类时，停止当前 Batch 并报告，不扩大范围。

## 3. 任务与 Batch 顺序

以下是建议的 planned Batch 标识，不代表这些 Batch 已启动：

| 顺序 | Planned Batch | 任务 | 目标 | 前置 |
|---|---|---|---|---|
| 1 | BATCH-20 | TASK-POST-AUDIT-011 | ModelGateway cancellation/timeout/provider error | TASK-006 |
| 2 | BATCH-21 | TASK-POST-AUDIT-012 | ResultNormalizer、schema、safe output、authority contract | TASK-006、011 |
| 3 | BATCH-22 | TASK-POST-AUDIT-007 | canonical Run/Invocation/Result/Event/SSE pipeline | 011、012 |
| 4 | BATCH-23 | TASK-POST-AUDIT-008 | ContextManager、Memory provenance、model-safe context | 007 |
| 5 | BATCH-24 | TASK-POST-AUDIT-009 | shared checkpoint、durable cancellation、lease、recovery | 007、008 |
| 6 | BATCH-25 | TASK-POST-AUDIT-013 | Provider SSRF、egress、endpoint authorization | 011 |
| 7 | BATCH-26 | TASK-POST-AUDIT-010 | legacy retirement、真实 API Eval、默认切换和最终 hardening | 007～009、013 |

一次只实施一个 Batch。前一个 Batch 未通过测试和 Review 时，不得提前修改后一个 Batch 的实现范围。TASK-011、012、013 在工程上可以并行调研，但执行记录和源码实施仍按上述顺序收口，以保持可回滚边界。

## 4. 每个 Batch 的固定循环

### 4.1 Preflight

- 记录 branch、HEAD、status、完整 diff 和文件归属；
- 检查前置任务的 execution record 和 Review verdict；
- 确认当前任务允许修改的文件；
- 运行适用基线测试，保留退出码、通过/失败/跳过数量和警告；
- 不创建 execution record，直到实际开始该 Batch。

### 4.2 TDD

- 先写能证明缺口的失败测试；
- 运行 focused test，记录真实失败原因；
- 实现最小 contract/adapter 变化；
- 再运行 focused test 和受影响的回归测试；
- 不删除旧测试、不关闭 redaction、不伪造 provider/tool 结果。

### 4.3 Verification

后端和 Harness 任务至少运行：

~~~powershell
uv run --directory backend pytest
uv run --directory backend ruff check app tests
pnpm.cmd --dir frontend lint
pnpm.cmd --dir frontend typecheck
pnpm.cmd --dir frontend test
pnpm.cmd --dir frontend build
git diff --check
~~~

适用时增加：

~~~powershell
uv run --directory backend python -m app.evaluation.runner --config evals/config/fast.yaml
uv run --directory backend python -m app.evaluation.runner --config evals/config/observability.yaml
~~~

修改前端协议、部署或启动边界时，必须增加前端 build、启动检查、Alembic/fresh DB 和配置契约验证。命令无法运行时必须记录环境原因，不能把历史 execution record 当成本轮证据。

### 4.4 Review

Review 只读完整未提交 diff，至少检查：

- Runtime 是否仍存在第二个控制循环；
- LLM 是否能直接触达 Tool/Domain Service；
- Decision、Invocation、Result、Event 是否使用同一 Run/ID/schema；
- identity、tenant、scope 是否来自可信上下文；
- side effect 是否有 policy、approval、timeout、cancel、retry、idempotency、compensation；
- SSE 是否只是 Event Store projection；
- 测试是否真实通过主路径；
- 是否存在 Secret、raw prompt、CoT、raw provider payload 或完整用户数据泄漏。

任何 blocker、critical、high 或未处理 medium finding 都必须停止当前 Review，进入 Remediation；修复后重新运行完整适用检查并重新审查完整 diff。

### 4.5 Handoff

执行记录必须使用 docs/harness-execution/TEMPLATE.md，至少包含：

- Batch、任务、start commit 和最终 commit（未授权提交时为 null）；
- changed files；
- 完整命令、退出码、通过/失败/跳过数量；
- Review verdict、rounds、findings；
- deferred findings、未解决风险和回滚方法；
- next_batch。

## 5. 任务级重点与门禁

### BATCH-20 / TASK-011

完成模型调用期间 cancellation、deadline、provider timeout、provider failure 的统一映射。门禁是：不会把取消变成 failed，不会在 terminal 后继续解析 Decision/调用 Dispatcher，不会留下未回收 asyncio task。

### BATCH-21 / TASK-012

完成唯一 ResultNormalizer 和 authority field contract。门禁是：输入 schema 在执行前校验，输出 schema/大小/redaction/provenance 在模型、Event、SSE 前统一处理，raw output 不再直通。

### BATCH-22 / TASK-007

完成 Runtime 写入 canonical Run/Event/Invocation/Result，API 只从 EventStore 投影。门禁是：一个 Run 的 event sequence 可重放，重复消费不产生第二个 Invocation，EventStore 写失败不能伪造成功。

### BATCH-23 / TASK-008

完成 ContextManager 和 model-safe ContextSnapshot。门禁是：principal/tenant/role/scope 只能由 Runtime 注入，Memory 有 provenance/trust/owner/retention，tool output 不能升级为 system instruction。

### BATCH-24 / TASK-009

完成 shared checkpoint、worker lease、durable cancellation、claim/fencing 和 crash recovery。门禁是：同一 Run 只有一个 worker owner，已完成 idempotent invocation 不会重复执行，unknown outcome 不会自动伪造 succeeded。

### BATCH-25 / TASK-013

完成 Provider endpoint、DNS、IPv6、redirect、host/port allowlist 和 /models/check authorization。门禁是：非 local 默认 fail-closed，不能通过用户 endpoint 访问私网或 metadata。

### BATCH-26 / TASK-010

完成 legacy path inventory、specialist/MCP/scheduler 迁移、真实 /chat fake-provider Eval 和 default cutover。门禁是：启用配置下不存在 Dispatcher bypass；默认路径不再调用 LangGraph ToolNode 内部循环；SSE、history、replay、Run state 与 canonical store 一致。

## 6. 最终主 API Eval 场景

真实 FastAPI 主入口必须覆盖至少：

1. 普通 respond/finish；
2. 一次 read-only capability invoke 后继续回答；
3. 未知 capability、版本错误、authority field 和 cross-owner request；
4. side effect 缺少 approval/idempotency、重复 key、payload conflict；
5. model timeout、provider failure、tool timeout、tool cancellation；
6. client disconnect、SSE replay、terminal Run replay；
7. worker crash、lease expiry、resume 和 unknown outcome；
8. prompt injection、tool output injection、Memory trust boundary；
9. Provider SSRF、redirect、DNS rebinding、未授权 /models/check；
10. frontend SSE/Event compatibility。

每个场景都必须验证：Runtime/Dispatcher 调用次数、Run/Event/Invocation 状态、terminal event 数量、owner scope、safe output 和回滚/补偿结果，而不只断言 HTTP 200。

## 7. 允许的回滚策略

- TASK-011～013 失败时只回退到对应已验证 adapter，不放宽安全边界；
- TASK-007～009 失败时保持旧兼容路径，但不得删除或覆盖已写入的 canonical 数据；
- TASK-010 cutover 失败时通过显式 flag 回到已验证、仍经 Dispatcher 约束的兼容路径；
- 不自动重放 unknown side effect，不删除 Run/Event/Memory，不运行生产迁移；
- 当前工作树已有用户修改时，必须先保存 patch 并确认归属，禁止宽范围 reset/restore。

## 8. 完成判定

只有当 BATCH-20～26 全部有真实 execution record、每批 Review verdict 为 pass、没有未处理 High/Medium finding、真实主 API Eval 通过且完整 diff 已审查，才可以更新 agent-runtime-target-architecture.md 的状态说明为已达到目标。此前只能继续使用 Implemented / Partial / Target 状态词，不得把规划文档写成实现证明。
