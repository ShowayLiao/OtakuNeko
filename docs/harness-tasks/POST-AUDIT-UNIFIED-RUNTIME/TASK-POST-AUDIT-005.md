# TASK-POST-AUDIT-005：主路径 Acceptance、Review 与 Hardening

## 目标

用真实的后端主路径证明前四个任务不是孤立单元测试，而是已经形成可运行、可恢复、可审计的 Harness。

## 依赖

- `TASK-POST-AUDIT-001` 至 `TASK-POST-AUDIT-004` 全部完成。
- 每个前置任务的失败测试、实现测试和回归测试均已通过。

## 允许修改的文件

- `backend/tests/acceptance/`
- `backend/tests/harness/`
- `backend/tests/capabilities/`
- `backend/tests/mcp/`
- `backend/tests/memory/`
- `backend/tests/trace/`
- `backend/tests/evaluation/`
- `backend/evals/datasets/`
- `backend/evals/config/`
- `backend/app/evaluation/`，仅限 gate/report wiring
- `.github/workflows/`，仅限接入现有测试和 Eval gate
- `docs/harness-audit/`、`docs/harness-tasks/`、`docs/harness-execution/` 的本批记录

## 禁止修改

- 不通过删除测试、降低断言、关闭 Policy/redaction 或屏蔽失败来通过 gate。
- 不把 LLM judge 的非确定性结果当成唯一安全 gate。
- 不在 fixture 写入真实 Secret、Token、完整用户数据或 raw Provider payload。
- 不修改生产业务行为来适配测试期望。

## 主路径场景矩阵

### 基础执行

- 单次只读 Capability。
- 两次顺序 Capability 调用。
- 多个无依赖只读调用的并发或确定性顺序。
- 最终 `respond`。
- 模型返回非法 Decision。

### 安全边界

- 未认证请求。
- 错误用户 scope。
- 模型伪造 `user_id` / `principal_id`。
- 未注册 capability。
- Policy deny。
- side effect 缺少幂等 Key。
- approval principal/action 不匹配。
- Tool/MCP/RSS 输出包含 prompt injection。

### 运行控制

- provider error。
- tool error。
- timeout。
- cancellation before/within model call。
- cancellation before/within tool call。
- token/model/cost budget exceeded。
- generator/client disconnect。
- Run persistence failure。

### 恢复与幂等

- SSE `Last-Event-ID` replay。
- replay 不重新执行已完成 Invocation。
- worker restart 后 Run 状态查询。
- stale lease 的 recovery/abandoned 行为。
- 相同 idempotency key replay。
- 相同 key 不同 payload conflict。
- side effect 状态未知时 attention required。

### 观测和数据治理

- Run/Invocation/Event/Trace 使用同一 ID。
- Event sequence 单调且 owner-scoped。
- Trace 默认 redaction。
- raw prompt/CoT/secret 不进入日志。
- unknown usage 被报告为 unknown。
- Memory provenance、expiry、owner、namespace 正确。

## 必须创建的主路径测试

建议至少包含：

```text
backend/tests/acceptance/test_primary_harness_flow.py
backend/tests/acceptance/test_primary_harness_security.py
backend/tests/acceptance/test_primary_harness_recovery.py
backend/tests/acceptance/test_primary_harness_side_effects.py
```

每个测试必须从 Runtime 或 API 主入口开始，不能只直接实例化被测 adapter。

## 验证命令

后端：

```powershell
uv run --directory backend pytest
uv run --directory backend ruff check app tests
```

前端协议回归：

```powershell
pnpm.cmd --dir frontend test
```

若任务修改了前端类型、构建或 lint 相关文件，再运行：

```powershell
pnpm.cmd --dir frontend lint
pnpm.cmd --dir frontend typecheck
pnpm.cmd --dir frontend build
```

额外 Harness/Eval：

```powershell
uv run --directory backend pytest tests/harness tests/acceptance tests/evaluation tests/trace -q
uv run --directory backend python -m app.evaluation.runner --config evals/config/observability.yaml
git diff --check
```

每条命令必须记录：退出码、通过/失败/跳过数量、警告、未运行原因。

## Review 流程

Review 阶段只审查、不修改：

1. 阅读完整未提交 diff。
2. 对照本任务和 `docs/code-review.md`。
3. 检查是否存在第二套 Run 状态机。
4. 检查主 LLM 是否仍能绕过 Dispatcher。
5. 检查 identity、resource scope、side effect、幂等、审批和恢复。
6. 检查测试是否真实经过主路径。
7. 输出 `pass` 或 findings。

发现 blocker/critical/high 或未处理 medium 时，退出 Review，进入 remediation；修复后重新运行全部相关验证并重新审查完整 diff。

## 最终验收

最终 Review 必须满足：

- `verdict: pass`；
- 无 blocker/critical/high Finding；
- 无未处理 medium Finding；
- 任务清单全部完成；
- 允许/禁止文件范围一致；
- 真实测试命令有退出码；
- 回滚路径和未解决风险明确；
- 执行记录使用 `docs/harness-execution/TEMPLATE.md`；
- 后续没有被本任务隐式扩大范围的 Batch。
