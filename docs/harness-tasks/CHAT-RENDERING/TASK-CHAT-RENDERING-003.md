# TASK-CHAT-RENDERING-003：Run 生命周期、取消、断线 replay 与消息状态

## 目标

让 chat 页面使用 RunView 管理运行中的回答，明确区分 thinking、executing、responding、completed、failed、cancelled 和 timeout，并把 durable Run 的取消和 replay 接入同一状态机。

## 依赖

- `TASK-CHAT-RENDERING-001`、`TASK-CHAT-RENDERING-002` 已通过测试和 Review。
- 后端已有 owner-scoped `GET /runs/{run_id}`、`GET /runs/{run_id}/events` 和 `POST /runs/{run_id}/cancel`。

## 允许修改

- `frontend/src/lib/fetcher.ts`
- `frontend/src/hooks/useChatStreaming.ts`
- `frontend/src/stores/useChatStore.ts`
- `frontend/src/components/chat/index.tsx`
- `frontend/src/components/chat/ChatInput.tsx`
- `frontend/src/components/chat/AgentMessageRenderer.tsx`
- `frontend/src/components/chat/ProcessContainer.tsx`
- `frontend/src/components/chat/FinalAnswerBlock.tsx`
- 相关前端测试、协议 fixture 和 execution record

## 禁止修改

- 不把前端 Zustand/localStorage 当作服务端 Run/Event source of truth。
- 不在点击停止后立即把 pending 节点伪造成 failed；取消请求和 cancelled terminal event 必须分开。
- 不在 SSE 断线时重新提交原始 chat POST。
- 不因刷新或 replay 重新执行已完成 Invocation。
- 不把 failed、cancelled、timeout 统一显示为 completed。

## TDD 契约

实现前先增加失败测试，至少覆盖：

1. live stream 的每个事件和 replay event 都经过同一个 RunView reducer。
2. 相同 sequence 重复到达时，content、processes 和 terminal state 不重复变化。
3. durable Run 断线后从 `after=lastSequence` 补拉，并继续到唯一 terminal event。
4. 未收到 terminal event 的 EOF 不会完成消息；projection/replay 失败时显示可恢复的连接状态。
5. durable Run 点击停止时请求 `/runs/{run_id}/cancel`，UI 显示 cancelling，收到 `run_cancelled` 后才完成。
6. 匿名 Run 不调用需要认证的 Run endpoint；Abort 后保留已经收到的回答内容并使用明确的 stopped/error presentation。
7. timeout、provider failure、tool failure、cancelled 和 partial answer 都能恢复为一致的 Message 状态。

## 实现要求

- Run metadata 至少保存 `runId`、`lastSequence`、durable 标志、phase、terminal status 和 error code；这些是 UI projection，不取代服务端事实源。
- `MessageStatus` 或等价 view model 必须保留 cancelled、timeout、failed 的差异。
- `AgentMessageRenderer`、`ProcessContainer` 和 `FinalAnswerBlock` 必须消费 terminal metadata，不能只根据 `isStreaming` 推导 done。
- 自动滚动只能影响视图，不得影响 event cursor、Run 状态或 replay。
- 取消、断线和刷新期间，已生成的部分回答必须保留；失败信息使用稳定 code 到安全文案的映射。

## 验收

- live、断线 replay、浏览器刷新后的 Run projection 和点击停止的 UI 状态一致。
- 每个 Run 只产生一个 terminal presentation；没有成功后又显示失败或重复回答。
- completed、failed、cancelled、timeout 的消息和过程摘要有明确视觉差异。
- 部分回答、工具结果和错误状态不会被 `onComplete` 或 Abort 清空。
- 相关前端测试、lint/typecheck/build 和 `git diff --check` 有真实退出码。
- 完整 diff Review verdict 为 `pass`。

## 回滚

关闭新的 RunView projection 后保留旧消息 renderer 和旧事件 alias；不取消后端已记录的 Run，不删除 EventStore 数据，不重新提交 chat 请求。
