# TASK-CHAT-RENDERING-001：Runtime Event 归一化与终态契约

## 目标

把 `frontend/src/lib/fetcher.ts` 从旧事件名和旧 payload 假设迁移到一个兼容 live/replay 的 RuntimeEvent normalizer，首先修复正常回答被误判为失败的问题。

## 依赖

- [`15-chat-rendering-audit.md`](../../harness-audit/15-chat-rendering-audit.md) 已确认 G-CHAT-001、G-CHAT-005。
- 当前后端 primary `/chat` Event 字段和 EventStore replay 字段已经由源码测试确认。

## 允许修改

- `frontend/src/lib/fetcher.ts`
- `frontend/src/lib/fetcher.test.ts`
- `backend/app/api/v1/agent.py`，仅限为 chat SSE 增加明确的 `durable`/projection 元数据；不得改变 Runtime Event 事实或执行流程
- `backend/tests/acceptance/` 中与该 SSE 元数据直接相关的 contract test
- 本任务对应 execution record 和审计链接

## 禁止修改

- 不重写 `AgentRuntime`、EventStore、Dispatcher 或 LangGraph loop。
- 不把 `run_id` 当作 durable 的充分条件。
- 不删除旧 `tool_start/tool_end`、`run.succeeded` 等兼容 alias，除非有独立 parity 测试和回滚路径。
- 不把没有 terminal event 的 EOF 伪造为 completed、failed 或 cancelled。

## TDD 契约

实现前先增加失败测试，至少覆盖：

1. 实时 `run_completed` 被归一化为 `succeeded`，不会进入 error 分支。
2. 实时 `run_failed`、`run_cancelled`、`run_timeout` 被归一化为对应 terminal status。
3. replay 的 `run.succeeded`、`run.failed`、`run.cancelled` 与实时终态进入同一 callback/reducer 输入。
4. canonical `run.failed` 携带 `status=timeout` 或 `error_code=timeout` 时归一化为 timeout，而不是普通 failed。
5. `run_id` 存在但没有 durable 标志时，不调用 `/runs/{id}/events`；匿名流仍能正常结束。
6. event id、payload sequence 和 replay sequence 的游标取最大值，非法 sequence 不会污染 cursor。
7. 重复 event 不重复触发 terminal callback。

## 实现要求

- 定义有限的 RuntimeEvent/terminal status 类型，避免继续使用无边界 `any` 作为协议判断依据。
- 将 event name、payload type、terminal status 和 sequence 在一个函数中归一化。
- 保持旧兼容 event 的读取能力，但不让兼容 alias 绕过新的终态检查。
- 将 `hasDurableRun` 改为后端明确元数据或经过认证、owner-scoped projection 验证的结果；不能从 `run_id` 猜测。
- `onComplete` 只在明确终态或明确的非 durable 完成条件成立时结束；未知 EOF 必须触发 recovery/error 状态。

## 验收

- `fetcher.test.ts` 覆盖 primary live fixture、legacy live fixture、primary replay fixture 和断线补拉。
- 成功回答从 `/chat` live stream 结束后最终状态为 completed，不产生 `Error:` 内容。
- 失败、取消和超时有稳定 terminal status 与 error code，不被归为 success。
- 现有兼容事件测试继续通过。
- 相关前端测试、typecheck、lint 和 `git diff --check` 有真实退出码。
- 完整 diff Review verdict 为 `pass`。

## 回滚

保留旧 callback 适配层和 event alias；若新 normalizer 发现未知事件，只回滚 chat projection feature flag，不回退后端 Runtime 或删除已持久化事件。
