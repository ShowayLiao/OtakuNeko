# Gateway 到 Chat 的流式推理与渲染实施计划

> 面向实现者：按 TDD 顺序执行；保留工作区中与本任务无关的已有修改。

## 目标

让 OpenAI-compatible/Provider Adapter、Model Gateway、Runtime、SSE 和前端 Chat projection 形成连续的流式链路，同时保留取消、超时、Provider 错误、Decision 校验和唯一终态语义。

## 设计边界

- Provider Adapter 逐块输出 provider-neutral `reasoning`/`text` delta，并在流结束时累积完整 Decision。
- Gateway 用结构化 stream event 暴露 delta 与最终 `ModelCallResult`；每个 `__anext__()` 使用同一个绝对 deadline，并在取消/超时时关闭 provider iterator。
- Runtime 只把 reasoning delta 投影为独立 `thinking_chunk`；完整结果到达后才交给 `DecisionParser`、Policy 和 Dispatcher。
- 未完成的 JSON Decision 不进入用户可见消息；经过校验的 `respond/finish.content` 仍通过 `message_chunk` 输出。
- 前端 message/reasoning/process 文本进入 reveal 队列，由 `requestAnimationFrame` 逐帧消费；完成、取消、超时和错误等待或清理队列后再落盘。

## 修改文件

- `backend/app/harness/model_types.py`：新增结构化 `ModelStreamEvent` 契约。
- `backend/app/harness/model_gateway.py`：增加 `stream_infer`，累积 Adapter 最终结果，统一取消/超时/错误投影。
- `backend/app/harness/runtime.py`：以 stream gateway 驱动 Decision Loop，逐 delta 发出 `thinking_chunk`，完成后解析执行。
- `backend/tests/harness/test_model_gateway.py`：Adapter delta/final Decision 回归。
- `backend/tests/harness/test_model_gateway_cancellation.py`：stream 取消和 deadline 回归。
- `backend/tests/harness/test_reasoning_forwarding.py`、`test_runtime_orchestration.py`：Runtime 顺序、最终解析和错误回归。
- `frontend/src/hooks/useChatStreaming.ts`：接入 message/reasoning reveal 队列。
- `frontend/src/__tests__/components/chat/useChatStreaming.test.tsx`、`frontend/src/lib/textRevealBuffer.test.ts`：逐帧渲染与终态回归。

## 验证

先运行新增 focused tests 并确认失败，再实现最小代码使其通过；之后运行：

```powershell
uv run --directory backend pytest
uv run --directory backend ruff check app tests
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend test
pnpm --dir frontend build
git diff --check
```

不创建 Batch execution record，也不修改生产配置、数据库 schema 或既有用户修改。
