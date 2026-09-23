# BATCH-04 执行记录

> Batch：`BATCH-04`
> Task：`TASK-HARNESS-004`
> 开始时间：`2026-07-31 23:50 Asia/Shanghai`
> 当前分支：`feature-harness`
> 起始 commit：`2c5a1e327326c473dcf54c87cd51a64448104e64`
> 记录状态：`completed`

## 1. Preflight

### 工作区和前置条件

```text
git status --short: clean（仅存在 Git ignore/cache 访问警告）
git branch --show-current: feature-harness
git rev-parse HEAD: 2c5a1e327326c473dcf54c87cd51a64448104e64
前置 Batch 及 commit: BATCH-03 8488d32；执行记录 finalization 2c5a1e3
当前任务允许修改: harness/model_gateway.py；agents/graph.py、deepseek_chat_model.py；api/v1/agent.py 的 models/check provider adapter；新建 harness/model_types.py；TASK-HARNESS-004 列出的测试和本执行记录
当前任务禁止修改: frontend fetcher/SSE event name；Runtime 状态/DB/全部 Tool/Capability；provider 依赖、真实 BYOK 存储；不得把 raw message/reasoning 写入 Trace/public response
```

### 权威资料

- `docs/architecture/standard-agent-harness-reference.md`
- `docs/standard-agent-harness-reference-and-codex-audit-guide.md`
- `docs/harness-audit/00-executive-summary.md` 至 `11-task-backlog.md`
- `docs/harness-tasks/INDEX.md`
- `docs/harness-tasks/BATCH-04/TASK-HARNESS-004.md`
- `docs/code-review.md`

### 基线命令

| 命令 | 退出码 | 通过 | 失败 | 跳过 | 警告/备注 |
|---|---:|---:|---:|---:|---|
| `$env:DEBUG='false'; uv run --no-cache --directory backend pytest tests/test_deepseek_chat_model.py tests/agents/test_provider_endpoint.py tests/harness/test_result_contract.py tests/evaluation/test_metrics.py -q` | 0 | 19 | 0 | 0 | 20 warnings |

## 2. 源码事实和不一致

| 文件/符号 | 实际行为 | 任务预期 | 处理方式 |
|---|---|---|---|
| `app.harness.model_gateway.OpenAIModelGateway.synthesize` | 直接调用 `AsyncOpenAI` 并只返回字符串，无 usage/finish/error contract | 通过 provider adapter 产生 `ModelCallResult`，保持 synthesize 兼容 | 增加 adapter/last result/trace metadata |
| `app.agents.graph.ChatWorkflow.stream_chat` | 直接实例化 ChatOpenAI/DeepSeekChatOpenAI | provider-specific 对象由 adapter/factory 负责，保留 SSE 事件名 | 增加统一 LangChain adapter bridge，不改 graph loop |
| `app.api.v1.agent.check_connection` | OpenAI-compatible 异常直接写入 HTTP detail | 只返回 user-safe provider error | 复用安全错误映射；保留 Ollama `/api/tags` 检查 |

## 3. 实施记录

### 变更范围

- 新增 `ModelUsage`、`ModelDelta`、`ModelCallResult`、`ProviderModelAdapter`。
- OpenAI-compatible、DeepSeek/LangChain 和 Ollama models/check 通过安全 provider 结果/错误边界接入。
- 保持 `OpenAIModelGateway.synthesize()` 和既有 thinking/tool/message SSE event name 兼容。

### 关键决策

- provider 缺失 token usage 时保留 token 字段为 `None`，只记录实际 latency，不伪造 0 或 cost。
- provider key 只留在 request context/client，禁止进入 `ModelCallResult`、Trace data、HTTP detail 和测试快照。
- provider 异常统一为有限错误码和 retryable；完整异常仅由受控日志记录。

### 兼容与回滚

- 兼容入口：`synthesize` 仍返回 `str`，DeepSeek reasoning 转换和所有现有 SSE event 名不变，Ollama endpoint validation 保留。
- 回滚：移除本 Batch 实现提交及执行记录 finalization，不触碰 BATCH-03。

## 4. Verification

| 命令 | 退出码 | 通过 | 失败 | 跳过 | 已知警告 |
|---|---:|---:|---:|---:|---|
| `$env:DEBUG='false'; uv run --no-cache --directory backend pytest tests/harness/test_model_gateway.py tests/test_deepseek_chat_model.py tests/agents/test_provider_endpoint.py tests/harness/test_result_contract.py tests/evaluation/test_metrics.py -q` | 0 | 26 | 0 | 0 | 20 warnings |
| `$env:DEBUG='false'; uv run --no-cache --directory backend ruff check app tests` | 0 | - | 0 | - | clean |
| `$env:DEBUG='false'; uv run --no-cache --directory backend pytest`（首次完整验证） | 1 | 534 | 1 | 0 | 111 warnings；既有 Graph safe error wording 兼容失败 |
| `$env:DEBUG='false'; uv run --no-cache --directory backend pytest tests/agents/test_graph_dual_node.py::TestStreamChatEventFlow::test_error_event_on_exception -q` | 0 | 1 | 0 | 0 | remediation pass |
| `$env:DEBUG='false'; uv run --no-cache --directory backend pytest`（remediation 后完整验证） | 0 | 535 | 0 | 0 | 110 warnings |
| `$env:DEBUG='false'; uv run --no-cache --directory backend ruff check app tests`（remediation 后） | 0 | - | 0 | - | clean |
| `git diff --check` | 0 | - | 0 | - | clean |

未运行项目及原因：未运行 frontend lint/typecheck/test/build，因为本 Batch 只修改 backend；未运行真实 provider、Ollama、DeepSeek 或 BYOK 请求，使用 fake provider 覆盖正常/stream/error 路径，避免外部副作用和 Secret 暴露。

备注：一次临时 `python -c` 手工命令因单行 class 定义语法错误退出 1，未作为验证证据；随后以 7 个 fake provider 测试和完整 535 项回归替代并通过。

## 5. Review

```yaml
review_result:
  batch: BATCH-04
  verdict: pass
  summary: "完整未提交 diff 与 remediation 后完整验证审查通过；ModelCallResult/usage/error、Graph SSE 兼容、Trace 安全字段和 models/check user-safe 错误边界满足任务要求。"
  findings: []
  reviewed_commands:
    - "git diff --check"
    - "uv run --no-cache --directory backend pytest"
    - "uv run --no-cache --directory backend ruff check app tests"
    - "provider fake complete/stream/error tests"
    - "Graph event compatibility tests"
  reviewed_files:
    - "backend/app/harness/model_types.py"
    - "backend/app/harness/model_gateway.py"
    - "backend/app/agents/deepseek_chat_model.py"
    - "backend/app/agents/graph.py"
    - "backend/app/api/v1/agent.py（models/check 部分）"
    - "backend/tests/harness/test_model_gateway.py"
    - "backend/tests/test_deepseek_chat_model.py"
    - "backend/tests/agents/test_provider_endpoint.py"
    - "backend/tests/harness/test_result_contract.py"
    - "backend/tests/evaluation/test_metrics.py"
    - "docs/harness-execution/BATCH-04-execution.md"
  deferred_findings: []
```

Review 检查项：无 blocker/critical/high/medium finding；未修改前端 SSE、Runtime、DB、Tool/Capability 或 provider 依赖；provider key、raw prompt/message/reasoning 未进入 ModelCallResult、Trace、HTTP models/check detail 或测试断言。

Remediation rounds：1（修复 Graph 既有 `LLM 不可用` 安全文案兼容性后重跑完整验证）

## 6. Handoff

```yaml
batch_result:
  batch: BATCH-04
  status: committed
  commit: 116e6ef
  tasks_completed:
    - "ModelUsage/ModelDelta/ModelCallResult/ProviderModelAdapter"
    - "OpenAI-compatible complete/stream adapter 与安全错误映射"
    - "OpenAIModelGateway synthesize 兼容桥接、usage/finish/latency Trace metadata"
    - "Graph LangChain provider factory/adapter bridge，保持 SSE event names"
    - "DeepSeek reasoning 与 models/check provider adapter 兼容"
  tests:
    passed:
      - "backend targeted: 26"
      - "backend full: 535"
      - "backend ruff: pass"
      - "Graph event compatibility: pass"
    failed: []
    skipped: []
  review:
    verdict: pass
    rounds: 1
    deferred_findings: []
  changed_files:
    - "backend/app/harness/model_types.py"
    - "backend/app/harness/model_gateway.py"
    - "backend/app/agents/deepseek_chat_model.py"
    - "backend/app/agents/graph.py"
    - "backend/app/api/v1/agent.py"
    - "backend/tests/harness/test_model_gateway.py"
    - "docs/harness-execution/BATCH-04-execution.md"
  unresolved_risks:
    - "Provider pricing table/cost estimation remains None when no pricing source is configured; BATCH-05 consumes usage but does not infer cost."
    - "Runtime budget/cancellation remains outside this Batch and is deferred to BATCH-05."
  next_batch: "按 INDEX 重新确认 BATCH-05 前置条件"
```
