# TASK-HARNESS-007

## 目标

让 SSE 成为持久化 RunEvent 的投影，支持按 `Last-Event-ID`/sequence 补拉；断线不重复执行已完成 Invocation。

## 背景

对应 `G-P1-03`、`G-P1-06`。当前后端只在 SSE 包装层生成 `stream_sequence`，前端 reader 没有 `Last-Event-ID` 或 Run 查询；断开后直接完成本地消息（`backend/app/api/v1/agent.py:220-231`; `frontend/src/lib/fetcher.ts:147-177,277-290`; `frontend/src/hooks/useChatStreaming.ts:532-548`）。BATCH-06 提供 durable EventStore，本任务只接 projection，不修改 Runtime/数据库 schema。

## 允许修改

- `backend/app/api/v1/agent.py` 的 SSE/Run read route
- 新建或修改 `backend/app/api/v1/run.py`（若项目路由结构采用独立文件）
- `frontend/src/app/api/v1/chat/route.ts`
- `frontend/src/lib/fetcher.ts`
- `frontend/src/hooks/useChatStreaming.ts`
- `backend/tests/acceptance/test_sse_replay.py`
- `frontend/src/lib/fetcher.test.ts`
- `frontend/src/app/api/v1/chat/route.test.ts`

## 禁止修改

- `backend/app/models/`、Alembic、Run/Event schema
- `backend/app/agents/graph.py`、Tool/Capability 实现、Model Gateway
- 前端消息持久化格式 `chat-storage`
- 通过重发 POST 代替 event replay

## 实施要求

1. 增加 `GET /api/v1/runs/{run_id}`，按认证 user/thread scope 返回 `status、last_sequence、error_code、started_at、finished_at`，不存在或越权统一返回 404。
2. 增加 `GET /api/v1/runs/{run_id}/events?after=<sequence>`，只返回当前 user 可见的 safe `RunEvent`；`after` 负数/过大值有明确 400/空列表语义。
3. SSE 请求读取 `Last-Event-ID` header 或 `after` query，并从 EventStore 发送 sequence 大于该值的事件；每帧使用 SSE `id:`，保留现有 `event:`/`data:` 字段。
4. 前端 `fetcher.ts` 在收到网络断开且 Run 未 terminal 时保存 `run_id/last_sequence`，重连只调用 replay endpoint，不重新提交原始 POST；保留当前 callback 兼容层。
5. 前端只在服务端 terminal event/status 为 succeeded/failed/cancelled 后更新最终状态；不能把 Abort 当作 success。
6. 事件 payload 只使用 BATCH-02 safe envelope；不把完整 Prompt、BYOK、raw exception、CoT 放到 replay。

## 兼容要求

- 没有 `Last-Event-ID` 的旧客户端仍能接收实时 SSE。
- 现有 `event` 名称和 callback 映射不变；新增 `id`/`run_id` 可被旧客户端忽略。
- anonymous thread 只能访问其当前临时请求允许的事件，不能通过猜 run_id 读取用户 Run。
- replay 不触发 LLM、Tool、Memory extraction 或外部副作用。

## 测试

- 单元测试：SSE `id`/sequence、after 边界、无效 JSON/safe payload、旧无 header 兼容。
- 集成测试：发送 fake Run 事件到 EventStore，读取 N 之后只收到 N+1；断开/重连不增加 invocation count；越权 run 返回 404。
- 回归测试：`cd backend && uv run pytest tests/acceptance/test_sse_replay.py tests/trace/test_sql_store.py -q`。
- 前端测试：`cd frontend && pnpm vitest run src/lib/fetcher.test.ts src/app/api/v1/chat/route.test.ts`，覆盖断开、重连、terminal status。

## 验收标准

- [ ] 断线后可以按 sequence 补拉，且不会重新执行 POST/LLM/Tool。
- [ ] Run/status/event API 有认证和 thread/user scope。
- [ ] 旧 SSE 客户端兼容，新客户端不会把取消标成成功。
- [ ] replay payload 通过 safe envelope/redaction，未泄露 secret/Prompt/CoT。
- [ ] 本 PR 未修改 Runtime、DB schema、Graph 或 Tool。

## 回滚

关闭 replay route/前端重连开关，旧客户端继续使用单次 SSE；保留 EventStore 数据和 `id` 字段，不允许回滚为自动重复提交带副作用的 POST。

## 输出

- 修改文件列表：记录 API projection、Next proxy、fetcher/hook 和测试。
- 测试结果：报告 sequence、越权、断线重连和旧客户端兼容结果。
- 未解决问题：记录下游 provider/tool cancellation 和 checkpoint restart 交由 BATCH-08。
- 风险说明：说明 EventStore 若不可用时的安全降级行为。
