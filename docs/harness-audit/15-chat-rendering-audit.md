# Chat 页面 Runtime Event 渲染审计

> 审计状态：planned / 未实施
>
> 审计基线：`feature-harness` / `ffb7fbd8c8a96ddf45e428c20c3696fe5465377d` / 2026-08-02。
>
> 审计范围：只覆盖 `frontend` chat 页面对当前 `/api/v1/chat` Runtime Event 的解析、状态归约和聊天过程渲染；不重新评估整个 Agent Harness 的架构成熟度。
>
> 关联架构：[`docs/architecture/agent-runtime-target-architecture.md`](../architecture/agent-runtime-target-architecture.md)。

## 1. 审计目的与结论

本审计回答一个问题：后端主聊天路径已经切换到 Runtime-owned Decision Loop 和 canonical Run Event 后，前端 chat 页面是否能正确显示回答、Capability 调用、失败、取消、超时和断线恢复。

当前结论：

~~~text
Chat projection: Not ready / High correctness gap
~~

后端主路径已经发送结构化 Runtime Event，但前端仍保留旧 LangGraph/Tool event 的字段和终态假设。当前至少有两个 High finding：

1. 实时主路径发送 `run_completed`，前端只识别 `run.succeeded` 等点号终态，正常回答可能在流结束时被标记为错误。
2. 主路径工具事件发送 `capability`、`invocation_id`、`argument_keys`，前端要求 `name`、`id`、`inputs`，因此工具过程不会被渲染。

本审计不把前端存在 replay 代码、类型声明或测试文件当作协议已经接入的证明；必须以真实事件字段、主路径调用和失败测试共同证明。

## 2. 当前源码事实

### 2.1 后端主路径事件

- `backend/app/api/v1/agent.py::_primary_decision_loop_enabled()` 默认启用 Runtime-owned 主路径，`/chat` 调用 `AgentRuntime.stream_decision()`。
- `backend/app/api/v1/agent.py` 对主路径事件直接使用 `chunk_data["type"]` 作为 SSE event，并使用 Runtime 的 `sequence` 作为 SSE id；API 不再为主路径重新分配事件序号。
- `backend/app/harness/runtime.py::stream_decision()` 依次产生 `thinking_start`、`model_call`、`model_decision`、`tool_call_start`、`tool_call_end`、`message_start`、`message_chunk`、`message_end` 和唯一终态事件。
- 主路径工具事件的字段是 `invocation_id`、`capability`、`argument_keys`、`status`、`error_code`、`output`；Invocation status 使用 `succeeded`、`failed`、`denied`、`cancelled`、`timeout` 语义。
- 主路径实时终态使用 `run_completed`、`run_failed`、`run_cancelled`、`run_timeout`。EventStore 的 canonical projection 会将部分终态映射为 `run.succeeded`、`run.failed`、`run.cancelled`，因此实时流和 replay 返回的 event name 不能靠字符串猜测，必须经过统一归一化。
- 后端提供 `GET /runs/{run_id}`、`GET /runs/{run_id}/events?after=` 和 `POST /runs/{run_id}/cancel`；取消接口返回的是取消请求事实，最终状态仍由 Runtime 的终态事件确认。

主要证据：

- `backend/app/api/v1/agent.py:443`、`:635`、`:655`～`:664`
- `backend/app/harness/runtime.py:889`、`:903`、`:967`、`:1011`、`:1028`、`:998`～`:1008`
- `backend/app/api/v1/agent.py:236`～`:318`

### 2.2 前端事件消费和渲染

- `frontend/src/lib/fetcher.ts::handleFrame()` 只将 `run_status`、`run.succeeded`、`run.failed`、`run.cancelled` 识别为终态，未覆盖实时主路径的 `run_completed`、`run_timeout`、`run_failed`、`run_cancelled`。
- `hasDurableRun` 当前由 `currentRunId !== null` 推导，但 Runtime 为匿名和持久化请求都会产生 `run_id`；`run_id` 只能作为关联 ID，不能单独证明 EventStore 可访问。
- `tool_call_start` 和 `tool_call_end` 当前要求 `data.name`，并读取 `data.id`、`data.inputs`；主路径使用 `capability`、`invocation_id` 和 `argument_keys`，所以主路径工具事件会被静默丢弃。
- `useChatStreaming.ts` 直接根据旧 callback 修改 `ProcessNode`，并把后端 Invocation status 强制转换为前端的 `success/error` 类型；`succeeded` 等主路径状态没有明确归一化。
- `stopGeneration()` 当前主要执行 Abort；它没有把当前 `run_id` 与后端取消请求及最终 `run_cancelled` 事件绑定起来。
- `AgentMessageRenderer` 主要根据 `isStreaming`、是否有内容和是否存在 pending process 推导状态；`MessageStatus` 没有独立表达 cancelled、timeout 和失败原因。
- `ProcessStepItem` 会直接把工具 details/output 转成 JSON 展示；前端应只显示后端 safe output 和有限大小的摘要，不能把 raw provider payload 或模型内部推理当作用户消息。

主要证据：

- `frontend/src/lib/fetcher.ts:178`～`:207`、`:234`～`:242`、`:370`～`:393`
- `frontend/src/hooks/useChatStreaming.ts:286`～`:324`、`:444`～`:505`、`:536`～`:579`
- `frontend/src/stores/useChatStore.ts:39`～`:72`
- `frontend/src/components/chat/AgentMessageRenderer.tsx:20`～`:33`
- `frontend/src/components/chat/ProcessStepItem.tsx:210`～`:275`

### 2.3 当前测试事实

- `frontend/src/lib/fetcher.test.ts` 主要使用旧的 `tool_start`、`tool_end` 和点号终态 replay fixture。
- 当前测试没有覆盖实时 `run_completed`、`run_timeout`、`run_cancelled`，也没有覆盖 `capability/invocation_id/argument_keys` 工具 payload。
- `frontend` 现有组件测试验证了旧 ProcessNode 的视觉行为，但没有从 Runtime primary event 归约到 ProcessNode 的完整路径。

因此现有前端测试通过不能证明当前后端主路径的 chat 渲染已经通过。

## 3. 目标渲染契约

前端应采用单一的事件归一化和 RunView reducer：

~~~text
SSE live event / EventStore replay
        ↓
RuntimeEvent normalize
        ↓
RunView reducer: run_id + sequence + phase + terminal status
        ↓
Message / ProcessNode projection
        ↓
Chat renderer
~~~

RunView 最少包含：

~~~typescript
{
  runId: string;
  durable: boolean;
  lastSequence: number;
  phase: 'thinking' | 'executing' | 'responding' | 'completed'
    | 'failed' | 'cancelled' | 'timeout';
  content: string;
  processes: ProcessNode[];
  errorCode?: string;
}
~~~

事件归一化规则：

| Runtime Event | Chat projection 行为 |
|---|---|
| `thinking_start` | 进入 thinking；只显示安全的阶段提示 |
| `model_call` | 更新阶段或折叠元信息；不显示 raw provider payload、usage 或 CoT |
| `model_decision` | `respond/finish` 进入 responding；`invoke` 等待对应 Invocation |
| `tool_call_start` | 以 `invocation_id` 创建节点，`capability` 作为名称，`argument_keys` 作为有限详情 |
| `tool_call_end` | 按 `invocation_id` 更新节点，归一化 status、error_code 和 safe output |
| `message_start` / `message_chunk` / `message_end` | 开始并追加回答；允许一个最终 chunk，不假设 token 数量 |
| `run_completed` / `run.succeeded` | completed |
| `run_failed` / `run.failed` | failed；若 `status` 或 `error_code` 为 timeout，则为 timeout |
| `run_cancelled` / `run.cancelled` | cancelled |
| `run_timeout` / `run.failed(status=timeout)` | timeout |

前端必须以 `sequence` 做单调游标和去重；live 和 replay 必须经过同一 reducer。未收到终态的 EOF 不能被直接当作成功或失败，持久化 Run 应先查询 projection/replay。

## 4. 未闭合 Gap

### G-CHAT-001：实时 Runtime 终态未被正确归一化

- 严重性：High
- 类别：correctness / compatibility
- 证据：后端主路径实时发送 `run_completed` 等下划线事件；`frontend/src/lib/fetcher.ts::handleFrame()` 只识别 `run_status` 和点号终态。
- 影响：正常回答结束后 `terminalStatus` 为空；`useChatStreaming.ts::onComplete()` 可能把有 `run_id` 的正常 Run 当作异常完成，消息显示为空或 error。
- 必须完成：统一映射实时和 replay 的终态名称；canonical `run.failed` 必须结合 `status/error_code=timeout` 恢复为 timeout；并在未收到终态时执行 Run projection/replay，而不是凭 EOF 推断结果。

### G-CHAT-002：主路径 Invocation 字段不匹配导致工具过程丢失

- 严重性：High
- 类别：correctness / contract
- 证据：后端发送 `invocation_id/capability/argument_keys`；前端 `tool_call_start/end` 仅检查 `data.name`。
- 影响：聊天过程只显示泛化的 thinking，不显示真正的 Capability 调用、结果和失败；多步 Decision Loop 无法被用户正确理解。
- 必须完成：以 `invocation_id` 做稳定关联，以 `capability` 渲染安全名称，以 `argument_keys` 渲染有限参数摘要，并归一化 Invocation status。

### G-CHAT-003：Run 生命周期、取消和断线恢复没有进入同一渲染状态机

- 严重性：High
- 类别：recovery / operations / correctness
- 证据：前端跟踪 `sequence`，但 live callback 和 replay 没有共享明确的 RunView reducer；停止操作主要 Abort SSE，未绑定后端 `cancel` 请求和最终终态。
- 影响：断线、浏览器刷新或点击停止后，前端可能丢失 Run 状态、重复追加事件、把取消显示成失败，或在后端仍运行时结束 UI。
- 必须完成：保存当前 `run_id` 和 `lastSequence`，对 durable Run 使用 cancel/projection/replay，按 sequence 去重，并等待唯一 terminal event 再完成渲染。

### G-CHAT-004：消息和过程组件无法准确表达失败、取消和超时

- 严重性：Medium
- 类别：correctness / UX
- 证据：`MessageStatus` 只有 `thinking/generating/completed/error`；`AgentMessageRenderer` 主要使用 `isStreaming` 推导 `done`；`ProcessContainer` 没有消费 terminal error code。
- 影响：失败或取消的消息可能显示为“思考完成”，空回答没有明确原因，用户无法区分取消、超时、Capability 失败和 Provider 失败。
- 必须完成：扩展 Run/Message status 或增加 terminal metadata，渲染稳定的安全错误摘要，并保留已生成的部分回答。

### G-CHAT-005：前端协议测试仍以兼容事件为主

- 严重性：Medium
- 类别：testing / release gate
- 证据：`frontend/src/lib/fetcher.test.ts` 覆盖旧 `tool_start/tool_end` 和点号 replay，但没有覆盖 Runtime primary 的实时事件字段和终态。
- 影响：协议升级后测试仍然通过，但真实 chat 页面不显示工具、误判终态或无法恢复。
- 必须完成：增加 primary event fixture、live/replay parity、重复 sequence、失败/取消/超时和匿名/持久化边界测试。

### G-CHAT-006：工具过程展示没有明确 safe-output 和大小边界

- 严重性：Low
- 类别：security / UX
- 证据：`ProcessStepItem` 对 details/output 直接 JSON.stringify 后展示；当前组件没有独立的字段级截断和 untrusted 标识。
- 影响：过大的 Capability 输出会占用聊天面板；不可信外部内容容易被用户误认为系统事实。
- 必须完成：只展示 safe output 的 bounded summary，增加 untrusted/provenance 提示；不展示完整模型推理或 raw provider payload。

## 5. 任务映射与依赖

~~~text
TASK-CHAT-RENDERING-001  Runtime Event normalize / terminal contract
              │
              ├── TASK-CHAT-RENDERING-002  Capability process projection
              │
              └── TASK-CHAT-RENDERING-003  Run lifecycle / cancel / replay
                                      │
                                      └── TASK-CHAT-RENDERING-004  Primary chat contract gate
~~~

任务包：[`docs/harness-tasks/CHAT-RENDERING/README.md`](../harness-tasks/CHAT-RENDERING/README.md)。

| Gap | 首个处理任务 | 后续任务 |
|---|---|---|
| G-CHAT-001 | TASK-CHAT-RENDERING-001 | 003、004 |
| G-CHAT-002 | TASK-CHAT-RENDERING-002 | 004 |
| G-CHAT-003 | TASK-CHAT-RENDERING-003 | 004 |
| G-CHAT-004 | TASK-CHAT-RENDERING-003 | 004 |
| G-CHAT-005 | TASK-CHAT-RENDERING-001 | 004 |
| G-CHAT-006 | TASK-CHAT-RENDERING-002 | 004 |

本任务包没有活动 Batch 编号。实施时必须由用户或项目流程明确创建 Batch，并为每个任务生成独立 execution record；本审计不代表任何任务已经完成。

## 6. 完成门禁

只有同时满足以下条件，才能将 Chat projection 标记为 Implemented：

1. 实时 SSE 和 EventStore replay 使用同一 RuntimeEvent normalizer 和 reducer。
2. `run_completed`、`run_failed`、`run_cancelled`、`run_timeout` 及其 canonical replay 别名都有确定性终态映射；canonical `run.failed(status=timeout)` 不得降级成普通 failed。
3. `tool_call_start/end` 能按 `invocation_id` 正确渲染 Capability 名称、状态、错误和 safe output。
4. sequence 单调、重复事件不重复追加内容或工具节点，未收到终态的 EOF 不会被伪造为成功。
5. durable Run 的取消、projection、replay 和浏览器刷新行为有测试；匿名 Run 不访问需要认证的 durable endpoint。
6. chat UI 明确区分 completed、failed、cancelled 和 timeout，并保留部分回答和安全错误摘要。
7. 不渲染 raw provider payload、Secret、完整 Prompt 或 Chain-of-Thought；工具输出有大小边界和不可信提示。
8. 前端 lint、typecheck、Vitest、build、适用后端主 API contract test 和 `git diff --check` 均有真实退出码。
9. 完整未提交 diff Review verdict 为 `pass`，没有 blocker、critical、high 或未处理 medium finding，且回滚路径明确。

## 7. Deferred 与不在本轮范围

- 不重写 `AgentRuntime`、DecisionParser、Dispatcher、Capability Service 或 LangGraph compatibility loop。
- 不把前端 `chat-storage` 当作服务端 Run/Event Store；前端只保存 UI projection 和可恢复的 Run 引用。
- 不在本任务包中修改 Provider、Memory、MCP、qBittorrent、Schedule 或数据库 schema。
- 不新增自由格式的前端事件协议；如当前 API 缺少明确的 `durable` 标识，只允许增加最小的 chat projection 元数据，不改变 Runtime 事件事实。
- 不通过删除旧兼容事件测试、屏蔽错误或把终态强制映射为 completed 来取得通过。

## 8. 回滚原则

- 保留旧 event alias 的解析能力，回滚只能关闭新的 reducer/渲染 feature flag，不能恢复绕过 Runtime 的后端执行路径。
- 不删除已持久化的 Run/Event/Invocation；刷新或回滚后通过 Run projection 和 Event replay 重建 UI。
- 发现 sequence、终态或 Invocation 关联异常时停止自动补偿和重试，只回退前端显示逻辑并保留原始 canonical 事件供核查。
- 当前任务没有活动 Batch，任何后续实现必须先识别工作区已有修改并使用显式文件列表提交。
