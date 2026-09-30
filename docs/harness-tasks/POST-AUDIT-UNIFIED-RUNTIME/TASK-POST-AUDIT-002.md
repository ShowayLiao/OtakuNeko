# TASK-POST-AUDIT-002：Runtime 唯一控制、取消与恢复

## 目标

让交互流式、非流式、Scheduler 和恢复入口共用同一个 Run 生命周期：

```text
Run create → context → step/invocation → event → terminal
```

`AgentRuntime`/`RunCoordinator` 是唯一控制者；Graph、Scheduler adapter 和 HTTP API 不再各自决定 terminal state。

## 依赖

- `TASK-POST-AUDIT-001` 的 Decision/Dispatcher contract。
- 当前 `RunStore`、`EventStore`、`SqliteCheckpointStore` 和 `CancellationToken`。

## 允许修改的文件

### 修改

- `backend/app/harness/runtime.py`
- `backend/app/harness/coordinator.py`
- `backend/app/harness/state.py`
- `backend/app/harness/task.py`
- `backend/app/harness/budget.py`
- `backend/app/harness/persistence/run_store.py`
- `backend/app/harness/persistence/event_store.py`
- `backend/app/harness/checkpoint.py`
- `backend/app/agents/langgraph_adapter.py`
- `backend/app/harness/scheduler/execution.py`
- `backend/app/harness/scheduler/repository.py`，仅限 Run 生命周期映射
- `backend/app/api/v1/agent.py`
- `backend/app/api/deps.py`，仅限 Run owner scope
- `backend/app/main.py`，仅限运行时依赖初始化

### 创建

- `backend/app/harness/cancellation_store.py`，如现有 persistence 无法表达 durable cancel
- `backend/tests/acceptance/test_runtime_single_owner.py`
- `backend/tests/acceptance/test_cancel_and_recovery.py`
- `backend/tests/harness/test_scheduler_runtime_contract.py`

## 禁止修改

- 不修改前端 UI 状态语义，除非现有 API 无法表达服务端 terminal 状态。
- 不在本任务中选择或升级 PostgreSQL/Redis 依赖；共享 checkpoint 的后端选择必须记录为部署决策。
- 不通过删除 `AgentTask` 或 `AgentState` 兼容字段解决状态映射问题。
- 不把断线当作成功、不把客户端 abort 当作已持久化 cancel。

## 实施步骤

### 步骤 1：定义唯一 Run 状态机测试

在 `test_runtime_single_owner.py` 覆盖：

- `queued → running → succeeded`。
- `queued → running → failed`。
- `queued → running → cancelled`。
- `queued → running → timeout` 的统一错误映射。
- terminal Run 不允许再次进入 running。
- 同一 Run 只能产生一个 terminal event。
- persistence 失败不能向调用方报告成功。
- `stream()` 和 `execute()` 对同一 fake adapter 使用同一状态契约。

### 步骤 2：收口 `execute()` 和 `stream()`

将 `AgentRuntime.execute()` 改为复用统一 Run lifecycle，而不是直接调用 `adapter.run()` 后自行写 Trace：

```text
execute(task)
  → Coordinator.execute/drive
  → same budget/cancellation/event/result path

stream(task)
  → Coordinator.stream/drive
  → same terminal state
```

如果必须保留不同的输出方式，差异只能是 projection，不得是状态机、预算或错误分类。

### 步骤 3：Scheduler 使用统一 RunRequest

`harness/scheduler/execution.py` 当前维护 Scheduler 自己的 `success/failed/cancelled` 状态。修改为：

- Scheduler lease 仍然保留，用于防止多个 scheduler worker 抢同一个 scheduled task。
- Agent 执行使用统一 `run_id`、`ExecutionContext`、`RunBudget` 和 `RunResult`。
- Scheduler repository 只保存 scheduled-task lease/projection，不创建第二套 Agent Invocation。
- retry 必须根据统一错误分类判断，并携带稳定的 idempotency scope。
- Scheduler retry 不得重复执行已成功的 side effect。

### 步骤 4：增加 durable cancel API

在 `agent.py` 增加 owner-scoped endpoint：

```text
POST /runs/{run_id}/cancel
```

要求：

- 必须认证并校验 Run owner/thread scope。
- 只允许 queued/running/paused Run 被取消。
- 已 succeeded/failed/cancelled/abandoned 的 Run 返回稳定冲突结果。
- 写入 durable cancel command/event。
- 当前 worker 通过共享 cancellation mechanism 感知取消。
- provider/tool adapter 在下一个安全取消点终止。
- API 返回 Run projection，不泄露内部异常或 provider payload。

### 步骤 5：定义断线和重启恢复

恢复行为必须区分：

```text
HTTP/SSE 断线：Run 继续，客户端通过 EventStore replay
请求取消：Run 进入 cancelled，禁止新 Invocation
Worker 重启：lease 过期 Run 进入 recovery/abandoned/resume 之一
Provider timeout：Invocation failed/timeout，Run 由 Coordinator 决定
```

不得因为 SSE 断线重新提交整个 `POST /chat` 并重新执行已完成 Invocation。

### 步骤 6：Checkpoint 和 Event source of truth

- 明确 `RunStore/EventStore` 是 Run 状态事实来源。
- 明确 checkpoint 是 Graph continuation state，不是 Run terminal state。
- 将 checkpoint 的 owner、lease、版本和恢复策略写入配置/部署文档。
- 如果部署为单 Worker，启动时必须 fail fast 或明确限制；不能默认宣称支持多 Worker。

### 步骤 7：Acceptance 测试

`test_cancel_and_recovery.py` 至少覆盖：

- cancel before model call；
- cancel during slow fake provider；
- cancel during slow fake tool；
- SSE disconnect then replay；
- restart after queued/running/paused；
- same idempotency key after reconnect；
- duplicate cancel；
- unauthorized owner accessing/cancelling another user Run。

## 验收条件

- `stream()`、`execute()`、Scheduler 共享同一 terminal Run contract。
- 存在真实 owner-scoped cancel endpoint。
- 客户端断线不会自动重新执行已完成 Invocation。
- cancel/timeout/recovery 都有 Run/Event/Trace 证据。
- 重启语义要么通过共享 checkpoint 验证，要么明确 fail-closed 的单 Worker 限制。
- `RunCoordinator` 是唯一决定 terminal state 的组件。
- 所有相关 acceptance tests 和完整后端测试通过。

## 回滚

- 关闭 cancel projection 不得删除已写入 cancel event。
- 新恢复逻辑失败时只能将 Run 标为 `abandoned`/`attention_required`，不能静默重试副作用。
- 保留旧 replay endpoint 的兼容读取，不恢复旧的重复执行行为。
