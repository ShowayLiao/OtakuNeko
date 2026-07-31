# TASK-HARNESS-004

## 目标

用 Adapter 统一 ChatOpenAI、DeepSeek、OpenAI-compatible synthesis 的模型调用结果、usage、finish reason、timeout 和 provider error；不改变前端流式事件。

## 背景

对应 `G-P1-05`、`G-P1-09`。当前 Graph 直接创建 `ChatOpenAI`/`DeepSeekChatOpenAI`，Runtime 另有 `OpenAIModelGateway`，Ollama 只在 models/check 中独立调用；没有统一 usage/cost/error contract（`backend/app/agents/graph.py:195-231`; `backend/app/harness/model_gateway.py:32-73`; `backend/app/api/v1/agent.py:412-435`）。参考文档 Batch 3 要求隔离 LangChain/OpenAI-compatible 细节、统一 streaming/usage/error 和模型版本（参考文档:1948-1954）。

## 允许修改

- `backend/app/harness/model_gateway.py`
- `backend/app/agents/graph.py`
- `backend/app/agents/deepseek_chat_model.py`
- `backend/app/api/v1/agent.py` 的 models/check provider adapter 部分
- 新建 `backend/app/harness/model_types.py`
- `backend/tests/harness/test_model_gateway.py`
- `backend/tests/test_deepseek_chat_model.py`
- `backend/tests/agents/test_provider_endpoint.py`
- `backend/tests/evaluation/test_metrics.py`

## 禁止修改

- 前端 `fetcher.ts`/SSE event name
- Runtime 状态机、数据库模型/迁移、全部 Tool/Capability
- provider 依赖版本和真实 BYOK 存储方式
- 将 provider raw message/reasoning 直接写入 Trace 或 public response

## 实施要求

1. 新建 `ModelUsage`：`prompt_tokens/completion_tokens/total_tokens: int | None`、`latency_ms: int`、`estimated_cost_usd: Decimal | None`；缺少 provider usage 时保持 `None`，不得伪造 0。
2. 新建 `ModelCallResult`：`provider/model/operation/status/text/usage/finish_reason/error_code/retryable`；`status` 只能为 `completed/degraded/failed/cancelled`。
3. 新建 `ProviderModelAdapter` protocol，至少提供 `complete(...) -> ModelCallResult` 和 `stream(...) -> AsyncIterator[ModelDelta]`；现有 `OpenAIModelGateway.synthesize()` 通过 adapter 返回结果，Graph 的 provider-specific classes 只负责转换 provider response。
4. 将 provider 异常映射到 `auth、rate_limited、timeout、invalid_request、transient、permanent、cancelled`；HTTP detail 只使用 user-safe message，完整异常仅在受控日志中脱敏记录。
5. 保持 `thinking_start/thinking_chunk/message_chunk/tool_call_*` 事件不变；只在内部 Trace/RunEvent 附加 provider/model/usage/latency。
6. BYOK api key 通过现有 context 传递，模型 adapter 不把它写入 `ModelCallResult`、Trace 或测试快照。

## 兼容要求

- DeepSeek reasoning content 仍按当前事件转换逻辑展示；未提供 usage 的模型不阻塞回答。
- `OpenAIModelGateway.synthesize()` 的调用方签名保持兼容，新增结果信息通过内部记录器获取。
- Ollama `/api/tags` 检查继续使用现有 endpoint validation，不把检查接口误当作聊天 streaming adapter。

## 测试

- 单元测试：OpenAI/DeepSeek/fake Ollama response 的 usage、finish、异常映射和缺失 usage。
- 集成测试：fake streaming provider 产生 reasoning/tool/final chunks，旧 event name 和顺序不变；timeout/cancel 不泄露 api key。
- 回归测试：`cd backend && uv run pytest tests/test_deepseek_chat_model.py tests/agents/test_provider_endpoint.py tests/harness/test_result_contract.py tests/evaluation/test_metrics.py -q`。
- 手工验证：使用本地 fake provider 完成一次普通回答和一次 DeepSeek reasoning 流，检查 Trace 仅含 provider/model/usage，不含 key/raw prompt。

## 验收标准

- [ ] 三种模型调用入口都有统一 `ModelCallResult` 或等价 adapter 输出。
- [ ] usage unknown 保持 `None`，错误分类和 retryable 可被 Runtime 使用。
- [ ] 现有前端 SSE event name、DeepSeek thinking 展示和 models/check 响应兼容。
- [ ] token/cost 统计可被 BATCH-05 读取，但本任务不决定 Run budget。
- [ ] provider secrets 不进入结果、Trace、测试快照或普通 HTTP detail。

## 回滚

保留旧 `ChatOpenAI`/`OpenAIModelGateway` 包装路径，以 provider feature flag 回退；回退时继续使用 user-safe error 和不记录 key 的行为，不回退到 raw exception response。

## 输出

- 修改文件列表：记录 model types、adapters、Graph bridge 和测试。
- 测试结果：报告每个 provider fake response 的 usage/error/stream 结果。
- 未解决问题：记录没有 provider usage 或价格表时的 cost unknown 情况。
- 风险说明：说明本任务只统一模型边界，不改变 Runtime、Tool Registry 或数据库。
