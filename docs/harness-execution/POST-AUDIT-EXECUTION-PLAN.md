# POST-AUDIT Unified Runtime 执行计划

> 类型：执行计划，不是 Batch execution record。
> 当前状态：planned。
> 只有用户批准具体实施并开始一个 Batch 后，才能根据 `TEMPLATE.md` 创建 `BATCH-XX-execution.md`。

## 1. 执行目标

在不伪造测试、不删除兼容层、不扩大业务范围的前提下，依次完成：

```text
001 Decision / Dispatcher
002 Runtime ownership / Cancel / Recovery
003 Capability / Tool / Side Effect convergence
004 Model / Memory / Deployment convergence
005 Primary-path acceptance / Review / Hardening
```

## 2. 启动前必须确认

```powershell
git status --short
git branch --show-current
git rev-parse HEAD
git log -5 --oneline
```

确认：

- 当前没有无法归属的用户修改。
- 当前没有其他活动 Harness Batch。
- 前置任务和 commit 与 `docs/harness-tasks/INDEX.md` 一致。
- 本次批准的任务文件和允许修改范围明确。
- 没有将历史审计结论误当作当前源码事实。

## 3. 权威资料阅读顺序

每个实际 Batch 开始前必须阅读：

1. `docs/architecture/standard-agent-harness-reference.md`
2. `docs/standard-agent-harness-reference-and-codex-audit-guide.md`
3. `docs/harness-audit/12-post-batch13-current-audit.md`
4. `docs/harness-tasks/INDEX.md`
5. 当前任务目录和前置任务文件
6. `docs/code-review.md`
7. 修改路径下更具体的 `AGENTS.md` / `AGENTS.override.md`

## 4. 每个任务的执行循环

### Preflight

- 记录分支、commit、工作区和文件边界。
- 运行该任务指定的基线测试。
- 查找真实入口、调用关系和现有测试。
- 将文档目标与源码事实分开记录。

### TDD / Implementation

- 先写能证明缺口的失败测试。
- 运行失败测试，保存失败原因。
- 实现最小 adapter/contract 变化。
- 保持旧只读兼容路径，禁止 side effect 绕过新边界。
- 每一组改动后运行对应 focused tests。

### Verification

至少运行适用的：

```powershell
uv run --directory backend pytest
uv run --directory backend ruff check app tests
pnpm.cmd --dir frontend test
git diff --check
```

如果修改了前端 lint/type/build 文件，增加：

```powershell
pnpm.cmd --dir frontend lint
pnpm.cmd --dir frontend typecheck
pnpm.cmd --dir frontend build
```

如果涉及 Eval、数据库或部署，必须运行任务文件中列出的额外命令，并记录未运行项目及原因。

### Review

Review 只审查完整未提交 diff，不修改代码。检查：

- Runtime 是否仍存在第二套控制面。
- 主 LLM 是否能直接触达 Tool/Domain Service。
- Decision、Invocation、Result、Event 是否使用同一 Run/ID/schema。
- identity、tenant、scope 是否来自可信上下文。
- side effect 是否有 policy、approval、timeout、cancel、retry、idempotency、compensation。
- SSE 是否只是 Event Store projection。
- 测试是否真实通过主路径。
- 是否存在 Secret、raw prompt、CoT、raw provider payload 或完整用户数据泄漏。

### Remediation

若存在 blocker/critical/high，或 medium 未处理：

1. 停止当前 Review。
2. 记录 finding、证据和影响。
3. 在同一任务允许范围内修复。
4. 重新运行完整相关验证。
5. 重新审查完整 diff，而不是只审查最后一处修改。

### Handoff

执行记录必须说明：

- 任务和 commit；
- changed files；
- 完整测试命令、退出码、通过/失败/跳过数量；
- Review verdict 和 remediation rounds；
- deferred findings；
- 未解决风险；
- 回滚方法；
- 下一任务或明确 `next_batch: null`。

## 5. 批次边界建议

建议一个任务对应一个批准的 Batch，避免一次变更同时改动主 Graph、数据库、部署、Memory 和前端协议：

| 任务 | 主要边界 | 不应顺手处理 |
|---|---|---|
| 001 | Decision / Dispatcher / 主聊天 read-only canary | Scheduler、生产 migration、qB write |
| 002 | Runtime / Run / Cancel / Recovery | Capability 业务规则、Provider 升级 |
| 003 | Registry / Tool / MCP / side effect | 新增业务能力、qB 资源模型的猜测 |
| 004 | Model / Memory / checkpoint / deployment | 模型替换、生产数据迁移执行 |
| 005 | Acceptance / Eval / Review / CI gate | 无测试证据的架构宣称 |

### 5.1 Unified Runtime Consolidation 后续规划

POST-AUDIT-001～005 完成后，仍不能把主聊天描述为完全统一的 AgentRuntime 架构。BATCH-19 已完成 TASK-POST-AUDIT-006 的 canary seam；后续任务按以下顺序推进：

1. TASK-POST-AUDIT-006：将主聊天接入 Runtime-owned Decision Loop。
2. TASK-POST-AUDIT-007：统一 Invocation、Result、Event、Trace 和 SSE 的 canonical pipeline。
3. TASK-POST-AUDIT-008：建立 ContextManager，统一 trusted context、Memory provenance 和模型可见上下文。
4. TASK-POST-AUDIT-009：实现 shared checkpoint、durable cancellation、lease 和 worker recovery。
5. TASK-POST-AUDIT-010：退役 legacy bypass，补真实主 API Acceptance/Eval 并重新评估 maturity。

完整任务边界见 [`../harness-tasks/UNIFIED-RUNTIME-CONSOLIDATION/README.md`](../harness-tasks/UNIFIED-RUNTIME-CONSOLIDATION/README.md) 及其 TASK-POST-AUDIT-006～010 文件。TASK-POST-AUDIT-007 之前不得把 canary 默认切换为生产主路径。

## 6. Review 输出模板

实际执行时复制到对应 `BATCH-XX-execution.md`：

```yaml
review_result:
  batch: null
  verdict: changes_required
  summary: ""
  findings: []
  reviewed_commands: []
  reviewed_files: []
  deferred_findings: []
  remediation_rounds: 0
```

## 7. 终止条件

必须停止当前任务并向用户报告：

- 发现未授权跨用户访问或 Secret 泄漏；
- 需要修改未授权目录或生产数据；
- 无法确定副作用的幂等/补偿/回滚语义；
- 关键测试失败且当前范围无法修复；
- 计划与源码事实严重不一致；
- 连续三轮 Review 仍未通过；
- 当前上下文不足以可靠完成下一步。
