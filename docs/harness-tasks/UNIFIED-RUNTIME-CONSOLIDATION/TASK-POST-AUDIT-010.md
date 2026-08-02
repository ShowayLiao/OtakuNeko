# TASK-POST-AUDIT-010：Legacy Bypass 退役、主 API Eval 与最终 Hardening

## 目标

在 TASK-006～009 全部通过后，关闭并最终删除未经 Dispatcher 的旧执行旁路，使主聊天、specialist、MCP、Workflow 和 Subagent 都只能由 AgentRuntime → Dispatcher 控制，并以真实主 API fake-provider Eval 作为最终门禁。

```text
User / API
  → AgentRuntime
  → ModelGateway → DecisionParser
  → Policy / Approval / Dispatcher
  → Capability / Tool / MCP / Workflow / Subagent
  → canonical Event / Result / Trace / Eval
```

## 依赖

- TASK-POST-AUDIT-006～009 均已通过 Review。
- `HARNESS_PRIMARY_DECISION_LOOP_ENABLED` 已完成 canary、持久化、恢复和 parity 验证。

## 允许修改

- `backend/app/api/v1/agent.py`
- `backend/app/agents/graph.py`
- `backend/app/agents/langgraph_adapter.py`
- `backend/app/agents/router.py`、specialist adapter 和 MCP adapter
- `backend/app/harness/`
- 相关 capability/tool/workflow/subagent 入口
- `backend/tests/acceptance/`、`backend/tests/harness/`、`backend/tests/evaluation/`
- `frontend/` 仅限已验证的 SSE/Event contract 兼容变更
- `docker-compose.yml`、启动检查和本任务 execution record

## 禁止修改

- 不先删除兼容实现再补测试。
- 不关闭 redaction、权限、approval、timeout、cancel、retry、idempotency、audit 或 compensation 来取得 Eval 通过。
- 不伪造 provider/tool 结果，不把 fake-only 通过写成真实主 API 已通过。
- 不升级无关依赖、不修改生产数据库或执行生产部署。

## TDD 契约

实现前先增加失败测试，至少覆盖：

1. 主 API fake provider 端到端路径不实例化 LangGraph `ToolNode` 循环，所有执行都可追溯到 Dispatcher。
2. specialist、MCP、Workflow、Subagent 的每个启用入口都拒绝绕过 Runtime/Dispatcher 的直接执行。
3. 无 flag、错误 flag、配置缺失和旧 client 版本均有明确兼容或 fail-closed 行为。
4. 真实主 API Eval 覆盖 ordinary response、tool invoke、denied、approval、timeout、cancel、provider failure、unknown outcome、cross-owner 和 prompt injection。
5. 全部 Run/Event/Trace/Invocation ID 可关联，SSE replay 与 history projection 与 canonical store 一致。
6. legacy symbols 退役后不存在未处理 TODO、空接口、伪实现或死配置。

## 实现要求

- 先把 legacy adapter 收敛为只承载 provider-specific 对象的 adapter，再移除内部循环控制权。
- 逐个入口提供迁移证据和 rollback 条件；不能用全局开关隐藏未迁移能力。
- 最终默认路径必须是 Runtime-owned；回滚只能回到已验证且仍受 Dispatcher 约束的兼容 adapter。
- 把最终 maturity、剩余风险和 deferred findings 写回审计文档，不把“测试存在”当作“生产路径已接入”。

## 验收

- 主 API fake-provider Acceptance/Eval 达到配置门槛；安全、取消、恢复、幂等、审计和 redaction 门禁全部通过。
- 后端全量测试、Ruff、前端 lint/test/typecheck/build、Eval 和 `git diff --check` 均有真实退出码。
- 完整未提交 diff Review verdict 为 `pass`，无 blocker/critical/high 或未处理 medium finding。
- 审计结论明确标记目标架构是否达到 Level 4/5，及任何仍需人工确认的外部副作用。

## 回滚

保留每个已退役入口的版本化兼容 adapter 和 feature flag，按单入口回滚；禁止全局恢复未经 Dispatcher 的直接 ToolNode/MCP/Domain Service 路径。回滚后再次运行主 API Eval、权限和 replay parity。
