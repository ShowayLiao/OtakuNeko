# 移除 LangGraph 兼容残留实施计划

> **面向 AI 代理的工作者：** 实施前必须获得用户批准，并将下列执行单元映射到一个明确批准的活动 Batch；实施阶段先使用 `test-driven-development`，再使用 `subagent-driven-development` 或 `executing-plans`。

**目标：** 移除仅为旧 LangGraph/旧 Agent Adapter 运行模型保留的 Evaluation/Harness 兼容层，使所有启用的 Harness 调用只经过当前 Runtime-owned Decision Loop，同时保持 canonical Run/Event/Invocation/Checkpoint/Trace 语义和已验证的 fail-closed 边界。

**架构：** `stream_decision()` 是唯一包含模型调用、Decision 解析、Policy、Dispatcher 和终态推进的循环。需要非流式结果的调用方只能使用 `collect_decision()`，它收集同一事件流，不复制循环。Deterministic Eval 使用 fake ModelGateway、真实 Dispatcher 和 deterministic capability handlers；未迁移的 specialist 入口继续返回结构化 `dispatcher_required`，不得恢复旧 adapter 直调。

**技术栈：** Python 3.11、FastAPI、Pydantic、SQLModel/SQLAlchemy、SQLite/PostgreSQL、当前 Harness contracts、ModelGateway、Dispatcher、pytest 和 Ruff。

---

## 1. 执行前提与范围

### 1.1 当前工作树基线

- 分支：`feature-harness`；当前 HEAD：`bb8df1b966e068a917b2cf9c10b8d7e690efeec1`（`feat(harness): complete AgentRuntime primary cutover`）。该提交包含此前工作区中 Harness/Agent/API/测试的用户变更；本计划不得把该提交的成果重复计入本次实现。
- 当前工作区目前只剩本计划文件未跟踪；实施前仍必须重新运行 `git status --short`、`git branch --show-current` 和 `git rev-parse HEAD`，并不得使用 `git reset --hard`、宽范围 `git restore` 或 `checkout` 覆盖任何新产生的用户修改。
- 本文件是规划变更，不是活动 Batch execution record。当前没有明确批准的活动 Batch 时，只能审计、规划和基线检查；不得直接实施本计划，也不得伪造 `BATCH-XX-execution.md`。
- 真正实施前必须保存当前脏工作树的显式文件清单/patch，确认允许与禁止文件范围，创建或更新经批准的活动 Batch execution record，并在每个执行单元之间完成验收和 Review。

### 1.2 目标与非目标

目标：

- Eval 真实调用 `AgentRuntime.stream_decision()`；
- Runtime 内只有一个 Decision Loop；
- 旧 Coordinator、adapter、synthesis、task-id checkpoint 和 fallback 路径不再可达；
- scheduler 的普通受支持任务继续工作，未迁移 specialist fail closed；
- 结构化结果、canonical persistence、取消、超时、恢复、审计和安全 Eval 不被削弱。

非目标：

- 不删除 `backend/app/memory/` 中仍被使用的 LangGraph Store 边界；
- 不删除 `backend/app/capabilities/langchain_adapter.py`、`pyproject.toml`、`uv.lock`；
- 不修改数据库 schema、生产数据、生产部署、前端事件协议或外部副作用实现；如实现确需这些变更，立即停止并请求确认；
- 不把历史 Batch execution record 当作本轮完成证明；
- 不为了清理符号删除仍表达 Runtime 不变量的测试。

### 1.3 权威不变量

- Agent Runtime 是一次 Run 的唯一控制者；LLM 只能提出版本化 Decision。
- 所有 Capability/Tool/Workflow/Subagent/MCP 调用均经过 Policy、资源授权和 Dispatcher；未迁移入口必须 fail closed。
- SSE 只是 EventStore 的投影；Run/Event/Invocation/Checkpoint 仍是事实源。
- 外部数据默认不可信；模型、SSE、Trace、Memory 和 Eval 不接收 raw provider payload 或未界定的 Tool output。

## 2. 已核对的源码事实

| 路径与符号 | 当前行为 | 本计划处理 |
|---|---|---|
| `backend/app/evaluation/adapter.py::RuntimeEvaluationTarget`、`OfflineOrchestrationAdapter` | Fixture 事件经过 `AgentRuntime.execute()`，并保留旧事件外壳归一化 | 改为 deterministic Runtime target，调用 `stream_decision()`；只消费 canonical Event |
| `backend/app/harness/runtime.py::AgentRuntime` | 同时存在 `execute()`、`resume()`、`stream()`、`_legacy_stream()`、`execute_decision()` 和 `stream_decision()` | `stream_decision()` 保留唯一循环；`execute_decision()` 必须删除或变成只收集 `stream_decision()` 的 `collect_decision()` 薄 façade |
| `backend/app/harness/coordinator.py::RunCoordinator` | 接收任意 adapter，驱动旧循环、legacy chunks 和 `synthesize()` | 删除；canonical persistence 留在 Runtime |
| `backend/app/harness/checkpoint.py` | Run-scoped `save/load` 与 `save_state/load_state`、`task:{task_id}` fallback 并存；`close()` 是生命周期钩子 | 删除 task-id 兼容语义；`close()` 不因名称被误删，是否保留单独按资源生命周期验证 |
| `backend/app/harness/result.py::AgentResult` | `from_raw()` 接受任意 dict/异常，`from_invocation_result()` 做兼容转换 | 调用方显式构造 typed result；保留版本化 `InvocationResult` 到领域结果的单一、显式映射 |
| `backend/app/harness/model_gateway.py` | `LangChainModelAdapter` 和旧 `synthesize()` 只被兼容路径/测试引用 | repo-wide 引用确认后删除；保留 provider-neutral Gateway/adapter |
| `backend/app/harness/scheduler/execution.py` | 普通 scheduled task 仍调用 `runtime.execute()`；specialist 已有 Dispatcher-required 保护 | 普通任务改走 `collect_decision()`；specialist 继续结构化 fail closed |
| `backend/app/api/v1/agent.py` | 主 `/chat` 和 approval resume 已调用 `stream_decision()` | 保持 API、Run/Event 查询和 replay 契约；不恢复旧入口 |

完整引用基线必须覆盖 `execute_decision`、`execute/stream/resume`、`RunCoordinator`、`save_state/load_state`、`AgentResult.from_raw/from_invocation_result`、`FeatureFlagRoutingAdapter`、`LangChainModelAdapter`、`ModelGateway.synthesize` 和删除文件的所有生产/测试引用。

## 3. 执行单元与依赖

下列执行单元是规划建议，不代表已经创建活动 Batch。每个单元应映射到一个批准的 Batch 或一个明确允许的 Task；一次只实施一个单元，并在单元末尾暂停 Review。

```text
P1  Evaluation deterministic target
  ↓
P2  Typed result / ModelGateway bridge cleanup
  ↓
P3  Single Runtime loop + scheduler migration
  ↓
P4  Run-scoped checkpoint cleanup
  ↓
P5  Repo-wide cleanup, docs sync and final verification
```

P2 和 P3 均依赖 P1 的失败契约；P4 只有在 P3 不再依赖 task-id facade 后才能执行；P5 必须最后执行。任何单元发现历史 checkpoint、外部 Python API 或 specialist 仍需要旧入口，都停止该单元并另立迁移任务。

## 4. P1：Evaluation deterministic Runtime target

**允许修改：**

- `backend/app/evaluation/adapter.py`
- `backend/app/evaluation/runner.py`
- `backend/evals/config/fast.yaml`
- `backend/evals/config/observability.yaml`
- `backend/tests/evaluation/test_runner.py`
- 必要时 `backend/evals/README.md` 和 fixture schema

**禁止修改：** 生产数据库、依赖锁文件、前端协议、真实外部副作用和未列出的 Harness 实现。

- [ ] 步骤 1：在 `test_runner.py` 增加失败契约：deterministic target 不实例化旧 adapter/Graph；真实调用 `stream_decision()`；输出事件必须包含 `run_id`、单调 `sequence` 和唯一 terminal event；旧 `RuntimeEvaluationTarget`、`create_offline_target` 不再导出。
- [ ] 步骤 2：运行 `uv run --directory backend pytest tests/evaluation/test_runner.py -q`，确认新增断言在旧实现上失败。
- [ ] 步骤 3：实现明确命名的 deterministic target。fake ModelGateway 只返回可控 ModelResponse；Dispatcher 使用真实 `Dispatcher`、Policy/ExecutionContext 和 deterministic capability handlers，不把 Policy/ResultNormalizer 替换成 fake。不得把 raw provider payload 写入 fixture。
- [ ] 步骤 4：把 `normalize_events()` 收紧为只接受 canonical Runtime Event；删除 `ScriptedProviderWorkflow`、`OfflineOrchestrationAdapter`、旧 target 和 `tool_calls/all_events` 专用归一化分支；同步迁移测试。
- [ ] 步骤 5：fast/observability 配置显式绑定 deterministic target；full Eval 继续使用 `create_production_target`，且生产 target 仍经过 `ModelGateway → DecisionParser → Dispatcher`。
- [ ] 步骤 6：运行 `uv run --directory backend pytest tests/evaluation -q`、两条 deterministic Eval 命令，并记录退出码和报告。

验收：Eval 不再依赖 adapter；普通、工具调用、拒绝、失败、取消/超时至少各有一个可控 fixture；事件归一化不接受旧外壳。

## 5. P2：Typed result 与 ModelGateway bridge cleanup

**允许修改：**

- `backend/app/harness/result.py`
- `backend/app/harness/model_gateway.py`
- `backend/app/harness/capability_adapter.py`
- `backend/app/agents/recommendation_agent.py`
- `backend/app/harness/runtime.py` 中 specialist 结果调用点
- `backend/tests/harness/test_result_contract.py`
- `backend/tests/harness/test_model_gateway.py`
- 受影响的 specialist/trace 测试

**禁止修改：** Capability 业务实现、数据库 schema、Memory LangGraph Store 和生产 provider 配置。

- [ ] 步骤 1：增加失败测试，证明 `AgentResult` 的构造只接受 typed、结构化字段；任意 dict/异常不能再由 `from_raw()` 隐式吞掉。
- [ ] 步骤 2：运行 `uv run --directory backend pytest tests/harness/test_result_contract.py tests/harness/test_model_gateway.py -q`，确认失败。
- [ ] 步骤 3：让 `RecommendationAgent`、`CapabilityAdapter` 和 Runtime specialist 路径显式构造 `AgentResult`；保留一个清晰、版本化的 `InvocationResult`→typed domain result 映射，禁止 raw provider payload 进入模型、SSE、Trace 或 Eval。
- [ ] 步骤 4：确认 repo-wide 只有兼容路径引用 `LangChainModelAdapter`/`synthesize()`；若存在生产调用，先迁移到 canonical Decision feedback，再删除类和方法。不得只删除测试来制造“无引用”。
- [ ] 步骤 5：运行结果、Gateway、specialist、trace 相关测试和 Ruff；记录失败/跳过原因。

验收：typed result 的字段、状态、错误和 safe output 可验证；旧转换桥不再成为默认入口；`LangChainModelAdapter` 与 `synthesize()` 无未处理生产引用。

## 6. P3：单一 Runtime Loop 与 scheduler 迁移

**允许修改：**

- `backend/app/harness/runtime.py`
- `backend/app/harness/coordinator.py`（删除）
- `backend/app/harness/__init__.py`
- `backend/app/harness/routing_adapter.py`（删除）
- `backend/app/harness/scheduler/execution.py`
- 受影响的 `backend/tests/harness/`、`backend/tests/acceptance/`、`backend/tests/agents/`、`backend/tests/trace/`

**禁止修改：** 前端事件协议、生产部署、数据库 schema 和未列出的业务 Service。

- [ ] 步骤 1：在 Runtime 和 scheduler 测试中增加失败契约：`stream_decision()` 是唯一循环；`execute_decision()` 不得再自行调用 ModelGateway/Dispatcher；旧 adapter、Coordinator、routing wrapper 和 `synthesize()` 不可导入。
- [ ] 步骤 2：运行相关 Harness/Acceptance/Trace 测试，确认旧实现失败。
- [ ] 步骤 3：删除 `AgentAdapter`、`StreamingAgentAdapter`、adapter 构造参数、`adapter_name`、`execute()`、旧 `resume()`、`stream()`、`_legacy_stream()`、旧 trace/fallback/synthesis 逻辑和 `RunCoordinator`。
- [ ] 步骤 4：如 scheduler 或其他非流式调用方需要结果，新增 `collect_decision()`：它只能 `async for` 消费 `stream_decision()` 并返回同一 `RunResult`；不得包含模型调用、Decision parse、Dispatcher 调用或第二套 terminal 状态机。
- [ ] 步骤 5：scheduler 的 `weekly_recommendation`/`seasonal_scan` 使用 `collect_decision()` 并保留成功、超时、取消、重试和 repository finish 语义；specialist/未注册任务返回结构化 `dispatcher_required` 或 `unsupported_task`，不能恢复旧 agent 直调。
- [ ] 步骤 6：迁移仍表达 Runtime 不变量的测试到 `stream_decision()`/`collect_decision()`；仅删除验证旧 Graph chunk、旧 task-id 或旧 facade 的测试，并为“旧入口不存在/旁路 fail closed”增加断言。
- [ ] 步骤 7：运行 `uv run --directory backend pytest tests/harness tests/acceptance tests/agents tests/trace -q`，确认主 API、Run/Event persistence、recovery、negative authorization、取消/超时和 scheduler 普通路径均通过。

验收：`stream_decision()` 是唯一循环；普通 scheduler 任务不被无故禁用；未迁移 specialist 不可绕过 Dispatcher；删除旧入口不会使 SSE/Run/Event 退回内存事实源。

## 7. P4：Checkpoint Run-scoped cleanup

**允许修改：**

- `backend/app/harness/checkpoint.py`
- `backend/app/harness/runtime.py` 中 checkpoint 调用点
- 必要时 `backend/app/api/v1/agent.py` 的调用清理
- `backend/tests/harness/test_checkpoint.py`
- `backend/tests/acceptance/test_restart_recovery.py`
- `backend/tests/acceptance/test_cancel_and_recovery.py`

**禁止修改：** 历史生产 checkpoint 数据、数据库 schema/迁移、Memory 的 `run_checkpoint_config()` 真实调用关系。

- [ ] 步骤 1：增加失败测试，要求所有保存、恢复、租约和取消操作显式提供合法 `run_id` 与 `thread_id`；`task:{task_id}` 不得作为 fallback。
- [ ] 步骤 2：运行 checkpoint/recovery/cancellation 测试确认失败。
- [ ] 步骤 3：删除 `CheckpointStore.save_state/load_state`、`_legacy_states`、`_legacy_scope` 和 `task:{task_id}` fallback；更新 fixture 的 AgentTask metadata。
- [ ] 步骤 4：保留并验证 lease fencing、abandoned、durable cancellation、terminal guard 和 SQLite single-worker fail-closed。`close()` 是生命周期接口，不因被列为兼容符号而盲删；只有确认没有资源生命周期需要时才清理调用。
- [ ] 步骤 5：若发现历史 task-id checkpoint 必须继续恢复，立即停止本单元，报告数据范围、迁移方案和回滚路径，不在本计划内猜测迁移。
- [ ] 步骤 6：运行 `uv run --directory backend pytest tests/harness/test_checkpoint.py tests/acceptance/test_restart_recovery.py tests/acceptance/test_cancel_and_recovery.py -q`。

验收：checkpoint 只有 `(run_id, thread_id)` 契约；重启、取消、租约丢失和 terminal replay 不重复执行 Invocation；SQLite 多 worker 仍明确 fail closed。

## 8. P5：repo-wide 清理、文档同步与最终 Review

**允许修改：** 本计划已列出的 `backend/app/evaluation/`、`backend/app/harness/`、受影响测试、Eval README/config，以及源码验证后确需同步的当前架构文档。

**禁止修改：** 历史 Batch execution record、依赖锁、生产部署、数据库 schema、前端协议和未列出的业务代码。

- [ ] 步骤 1：运行完整引用清理，范围必须覆盖 `backend/app` 和 `backend/tests`，并包含 `execute_decision`：

```powershell
rg -n --hidden -g '!**/__pycache__/**' -g '!**/.pytest_cache/**' 'LangGraphAdapter|ChatWorkflow|AgentAdapter|StreamingAgentAdapter|FeatureFlagRoutingAdapter|RunCoordinator|OfflineOrchestrationAdapter|RuntimeEvaluationTarget|create_offline_target|execute_decision|_legacy_stream|save_state|load_state|AgentResult\.from_raw|AgentResult\.from_invocation_result|LangChainModelAdapter|ModelGateway\.synthesize|\.synthesize\(' backend/app backend/tests
```

- [ ] 步骤 2：确认 `pyproject.toml/uv.lock` 中保留的 LangGraph 依赖仍有 Memory/Store 真实使用；在交付中明确“移除 Harness 兼容层”不等于“删除全部 LangGraph 依赖”。
- [ ] 步骤 3：源码验证后才同步当前架构/审计文档；不得把本计划或历史 execution record 写成实现证明。
- [ ] 步骤 4：运行完整后端门禁：

```powershell
uv run --directory backend pytest
uv run --directory backend ruff check app tests
uv run --directory backend python -m app.evaluation.runner --config evals/config/fast.yaml
uv run --directory backend python -m app.evaluation.runner --config evals/config/observability.yaml
```

- [ ] 步骤 5：有有效凭据才运行 full Eval；无凭据则跳过并记录原因，不伪造通过：`uv run --directory backend python -m app.evaluation.runner --config evals/config/full.yaml`。
- [ ] 步骤 6：运行 `git diff --check`、`git diff --stat` 和完整未提交 diff Review；区分本计划新增内容与用户既有修改。
- [ ] 步骤 7：文档/路径检查：`rg -n "standard-agent-harness-reference|harness-execution|BATCH-[0-9]+" AGENTS.md docs`。若修改了前端或事件协议，停止并请求确认；经批准后另行运行前端 lint/typecheck/test/build。

## 9. 回滚与停止条件

- 回滚使用实施前保存的显式文件清单/patch 或独立 commit；不得用宽范围命令覆盖用户修改。
- 不删除 canonical Run/Event/Invocation/Memory 数据；不通过恢复旧 adapter 来恢复未经 Dispatcher 的执行权限。
- 发现旧 task-id checkpoint、外部 Python API、scheduler specialist 或启用的旁路仍有硬依赖时，立即停止对应单元并报告路径、符号和影响。
- 发现未知副作用状态时暂停自动 retry，进入对账、补偿或人工核查；不得把超时当成失败后直接重做。
- 连续三轮 Review 未通过时停止当前活动 Batch，不扩大范围。

## 10. 预期交付与完成门槛

完成后应得到：

- 只有 `stream_decision()` 拥有模型/Decision/Dispatcher 循环；非流式调用只通过 `collect_decision()` 收集同一流；
- Eval、主 API、scheduler 和测试均不依赖旧 adapter/coordinator/task-id facade；未迁移 specialist 明确 fail closed；
- Decision、InvocationResult、Run/Event、Checkpoint、Policy、Dispatcher、Trace 和安全 Eval 仍由当前源码验证；
- 完整后端测试、Ruff、deterministic Eval、full Eval（如有凭据）、清理检查、`git diff --check` 和完整 Review 均有真实退出码；
- 回滚方式、未解决风险、未运行项目及原因记录在活动 Batch execution record 中。

本计划只有在用户批准并建立活动 Batch 后才能进入实施；计划阶段不创建虚假 execution record、不提交、不 push、不创建 PR。
