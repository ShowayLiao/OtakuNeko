# TASK-HARNESS-005

## 目标

让 `AgentRuntime` 成为唯一的交互 Run Coordinator：统一 terminal state、步骤/Tool/模型预算、超时、取消和 Graph error 处理，同时保留 LangGraph 作为内部 Loop Adapter。

## 背景

对应 `G-P1-01`、`G-P1-05`、`G-P1-11`。当前 `AgentRuntime.stream()` 负责外层 state/trace/结果 synthesis，`FeatureFlagRoutingAdapter` 负责路由，`ChatWorkflow` 负责真实 `think → tools → think → speak` Loop；Graph 把异常转为 error chunk 后结束，可能绕过 Runtime failed 分支（`backend/app/harness/runtime.py:181-336`; `backend/app/harness/routing_adapter.py:19-66`; `backend/app/agents/graph.py:90-108,470-477`）。

## 允许修改

- `backend/app/harness/runtime.py`
- 新建 `backend/app/harness/coordinator.py`
- 新建 `backend/app/harness/budget.py`
- `backend/app/harness/state.py`
- `backend/app/agents/langgraph_adapter.py`
- `backend/app/harness/routing_adapter.py`
- `backend/tests/harness/test_runtime.py`
- `backend/tests/harness/test_runtime_orchestration.py`
- `backend/tests/harness/test_coordinator.py`
- `backend/tests/agents/test_langgraph_adapter.py`
- `backend/tests/trace/test_agent_instrumentation.py`

## 禁止修改

- `backend/app/agents/graph.py` 的节点拓扑和 ToolNode 实现
- 数据库/迁移、SSE 前端协议、qB/收藏/日程业务 Service
- 通过一次性重写替换 LangGraph
- 将模型 chain-of-thought 当作 Runtime decision 或 public state

## 实施要求

1. `RunBudget` 字段固定为 `max_steps、max_tool_calls、max_model_calls、deadline_seconds、max_total_tokens、max_cost_usd`；缺省值必须有限，且 `None` 只允许表示 provider 不提供 usage，不表示无限预算。
2. `CancellationToken` 使用 `asyncio.Event`，提供 `cancel()`、`is_cancelled()`、`raise_if_cancelled()`；Coordinator 在 adapter 启动、每个事件、每次模型/Tool边界检查。
3. `RunCoordinator.stream(task, context, budget, cancellation)` 只允许产生一个 terminal `RunResult`；它消费 BATCH-02 的 `RunEvent`，将 Graph `error` event 映射为 `failed`，而不是把 generator 正常结束当作成功。
4. `AgentRuntime` 保留现有构造入口，内部委托 Coordinator；现有 `AgentRuntime.execute/stream` 调用者不需要立即迁移。
5. 预算超限返回 `budget_exceeded`；模型/Tool timeout、cancelled、policy denied、transient error 走明确状态，禁止通用 `except Exception` 后标记 completed。
6. 本任务只做运行时内存状态；不新增 SQL Run/Event 表，持久化由 BATCH-06 处理。

## 兼容要求

- `ChatWorkflow` 仍然可以执行多次 Tool Calling，`recursion_limit=24` 在本任务中只是 Graph 内部上限；Coordinator budget 更严格时优先终止。
- legacy adapter 仍能返回旧 chunk；Coordinator 同时生成内部 RunEvent。
- Proactive scheduler 当前 `AgentRuntime.execute()` 行为保持兼容，不强制其立即使用交互 stream coordinator。
- 现有 specialist synthesis `max_model_calls` 不能突破 RunBudget。

## 测试

- 单元测试：预算边界、取消幂等、非法状态转移、Graph error chunk、正常空流、重复 terminal event。
- 集成测试：fake model/tool 运行 normal/single/multi/error/timeout/cancel；断言 Runtime 最终 status 与 Trace event 一致。
- 回归测试：`cd backend && uv run pytest tests/harness tests/agents/test_langgraph_adapter.py tests/trace/test_agent_instrumentation.py tests/acceptance/test_end_to_end.py -q`。
- 手工验证：真实应用完成一次只读动漫查询；触发前端 stop 后，Coordinator 状态为 cancelled 而不是 completed。

## 验收标准

- [ ] 交互路径只有 Coordinator 进行 terminal state transition。
- [ ] Graph error 不再静默成为成功结束；cancel/timeout/budget 状态可区分。
- [ ] max steps/tool/model/token/cost/deadline 字段均有消费点或明确 `unknown` 计数。
- [ ] 现有 AgentRuntime、Proactive、LangGraph adapter 测试通过，未修改 DB/frontend。

## 回滚

保留 `AgentRuntime` 旧 adapter facade，通过 `HARNESS_COORDINATOR_ENABLED` 关闭新 Coordinator；关闭时只允许 read-only legacy Graph，所有 side-effect path 仍受 BATCH-01/后续 policy 保护。

## 输出

- 修改文件列表：记录 Coordinator、Budget、Cancellation、adapter 和测试。
- 测试结果：逐项报告 terminal state、预算和取消断言。
- 未解决问题：记录交互 state 尚未持久化、SSE 尚未补拉的边界。
- 风险说明：说明 BATCH-06 前，进程重启仍可能丢失交互 Run 状态。
