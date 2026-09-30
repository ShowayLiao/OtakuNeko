# CHAT-RENDERING 任务规划

> 目标：让前端 chat 页面消费当前 Runtime-owned `/chat` 主路径的结构化 Event，并稳定渲染回答、Capability 过程、终态、取消、超时和断线恢复。
>
> 当前状态：planned / 未创建活动 Batch。本文档和子任务只是审计后的实施计划，不是执行记录。
>
> 审计基线：[`docs/harness-audit/15-chat-rendering-audit.md`](../../harness-audit/15-chat-rendering-audit.md)。

## 1. 目标架构

~~~text
SSE live event / EventStore replay
        → RuntimeEvent normalizer
        → RunView reducer
        → Message / ProcessNode projection
        → Chat renderer
~~~

前端不拥有 Run 控制权，不把 localStorage 作为 Run/Event source of truth，也不通过视觉状态推断后端终态。后端 Runtime Event 是事实，前端只维护可重建的展示 projection。

## 2. 依赖顺序

| 任务 | 目标 | 依赖 | 状态 |
|---|---|---|---|
| [TASK-CHAT-RENDERING-001](TASK-CHAT-RENDERING-001.md) | Runtime Event 归一化与终态契约 | 当前 `fetcher.ts` 与 primary event fixture | planned |
| [TASK-CHAT-RENDERING-002](TASK-CHAT-RENDERING-002.md) | Capability Invocation 过程投影与安全展示 | 001 | planned |
| [TASK-CHAT-RENDERING-003](TASK-CHAT-RENDERING-003.md) | Run 生命周期、取消、断线 replay 与消息状态 | 001、002 | planned |
| [TASK-CHAT-RENDERING-004](TASK-CHAT-RENDERING-004.md) | 主路径协议回归与发布门禁 | 001～003 | planned |

一次只实施一个任务。前置任务未通过测试和 Review 时，不得修改后续任务的实现范围。

## 3. 全局不变量

- `run_id` 只作为 Run 关联 ID；不能单独推断 durable persistence。
- live SSE 和 replay event 必须进入同一个 normalizer/reducer。
- `sequence` 单调递增且去重；重复事件不能重复追加回答或创建 Invocation 节点。
- `invocation_id` 是工具过程的唯一关联键；`capability` 是安全的能力名称，不等同于用户可控的展示文案。
- `run_completed`、`run_failed`、`run_cancelled`、`run_timeout` 和 canonical replay 别名必须产生唯一终态。
- 取消请求不是取消完成；UI 必须等待 Runtime 终态或明确的 projection 状态。
- Tool output、MCP、RSS、网页和历史内容默认是不可信数据；只显示 safe、bounded、可标记来源的投影。
- 不把 `model_call`、usage、raw provider payload 或 Chain-of-Thought 当作普通聊天内容展示。
- 不删除旧兼容事件解析，除非 primary parity、回滚路径和任务范围明确允许。

## 4. 共同允许与禁止范围

允许范围由每个子任务单独列出。默认允许：

- `frontend/src/lib/fetcher.ts`
- `frontend/src/hooks/useChatStreaming.ts`
- `frontend/src/stores/useChatStore.ts`
- `frontend/src/components/chat/`
- `frontend/src/lib/*.test.ts`
- `frontend/src/__tests__/components/chat/`
- 与当前 SSE contract 直接相关的 `backend/tests/acceptance/` 测试 fixture
- 本任务包和对应审计链接

禁止：

- 重写 Runtime、Dispatcher、Capability、Memory、MCP 或 LangGraph loop。
- 用前端字段伪造 `user_id`、tenant、scope、approval 或资源归属。
- 将 raw provider payload、Secret、完整 Prompt、完整 BYOK 或完整用户数据写入日志、fixture 或 UI。
- 删除旧失败测试、降低断言、吞掉未知事件或把未知 EOF 视为 completed。
- 修改生产数据库、生产部署、无关依赖和未列出的业务页面。

## 5. 共同验收门槛

- 前端：`pnpm --dir frontend lint`、`pnpm --dir frontend typecheck`、`pnpm --dir frontend test`、`pnpm --dir frontend build`，按任务范围执行并记录退出码。
- 后端相关 contract test：覆盖 `/chat` primary event 字段和 `Run/Event` replay；不得只直接实例化一个 mock reducer。
- 必须覆盖 ordinary response、single/multi-tool、denied/failed tool、provider failure、timeout、cancel、disconnect/replay、duplicate sequence 和未收到终态的 EOF。
- 必须验证匿名 Run 不调用需要认证的 durable endpoint，持久化 Run 能按 owner scope replay。
- `git diff --check` 通过；完整未提交 diff 按 `docs/code-review.md` 审查。
- Review verdict 为 `pass`，无 blocker、critical、high 或未处理 medium finding；执行记录必须使用明确的 Batch 归属。

## 6. 回滚

- 保留旧事件 alias 和兼容 projection，按任务级 feature flag 或显式 adapter 回滚。
- 不清理 EventStore、RunStore 或 Invocation 数据；回滚后仍以 canonical event 重建 UI。
- 如果终态或 sequence 语义不一致，停止自动重试和新 UI 补偿，回退前端 projection 并保留事件供审计。
