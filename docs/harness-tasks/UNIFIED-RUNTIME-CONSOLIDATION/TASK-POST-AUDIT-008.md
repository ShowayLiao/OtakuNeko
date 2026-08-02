# TASK-POST-AUDIT-008：ContextManager 与 Memory / Provider Trust Boundary

## 目标

建立唯一的 ContextManager，负责把可信 Runtime context、用户授权范围、Memory provenance、能力 schema、Run state 和模型可见消息组装为 provider-neutral 请求。

```text
trusted principal / tenant / scope
            ↓ Runtime-owned ContextManager
Memory(provenance, trust, budget) + capability metadata + run state
            ↓ redacted model request
ModelGateway
```

模型只能看到经过筛选和预算限制的数据，不能决定 `user_id`、tenant、role、scope、数据库、凭据或审批状态。

## 依赖

- TASK-POST-AUDIT-006 的 Decision Loop 已可运行。
- TASK-POST-AUDIT-007 已冻结 canonical Event/Invocation 关联，Context snapshot 可以按 Run 追溯。

## 允许修改

- `backend/app/harness/`
- `backend/app/memory/`
- `backend/app/api/v1/agent.py` 的 context 注入边界
- `backend/tests/acceptance/`
- `backend/tests/harness/`
- `backend/tests/memory/`
- `backend/tests/evaluation/`
- 本任务对应的 execution record

## 禁止修改

- 不把 provider SDK/LangChain/LangGraph 对象带入 ContextManager 公共契约。
- 不把完整 Memory 原文、Secret、BYOK、数据库句柄、raw provider payload 注入模型。
- 不把用户传入的 identity/scope 当作可信授权来源。
- 不借此任务重写 Memory 数据模型、升级依赖或修改无关业务规则。

## TDD 契约

实现前先增加失败测试，至少覆盖：

1. Runtime 注入的 principal/tenant/role/scope 在模型请求中只以允许的安全摘要或 capability scope 表示，模型参数无法覆盖它们。
2. Memory item 带有来源、时间、owner、trust level 和引用 ID；不可信网页/RSS/MCP/tool output 不能升级为可信事实。
3. Context budget 超限时按确定性优先级裁剪，不静默丢弃系统安全约束；裁剪结果可审计。
4. 跨用户、跨租户、跨 thread 的 Memory 和 capability schema 不会被拼入当前 Run。
5. prompt injection、伪造 authority 字段和恶意 tool output 不能改变 Dispatcher 的授权结果。
6. provider request redaction 与 trace redaction 不泄露 prompt、token、凭据或完整用户数据。

## 实现要求

- ContextManager 是 Runtime 唯一调用入口；API 只提供可信 principal，不自行拼接模型 prompt。
- Memory retrieval 必须返回结构化 provenance，不得只返回字符串列表。
- ModelGateway 接收 provider-neutral `ModelContextSnapshot`，并保留可审计的版本和哈希。
- DecisionParser/Dispatcher 继续执行 authority 字段拒绝、资源级授权和 scope 校验；ContextManager 不能取代 Domain Service 授权。

## 验收

- Acceptance/Eval 覆盖真实主 API 的跨用户、prompt injection、memory trust 和上下文预算场景。
- 后端测试、Ruff、前端协议测试、typecheck、build、Eval 和 `git diff --check` 均有真实退出码。
- Review verdict 为 `pass`，无 blocker/critical/high 或未处理 medium finding。

## 回滚

保留版本化 Context snapshot 和 provenance 数据；通过显式 compatibility adapter 回退到旧消息投影，但禁止恢复模型自带 identity 或直接 provider payload。回滚后必须重新运行 trust-boundary 和 cross-owner 测试。
