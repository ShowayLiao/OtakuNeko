# 后端 Mypy 债务清零实施计划

> **面向 AI 代理的工作者：** 按下表一次执行一个质量批次。每批先复现诊断、核对运行时契约，再做最小修复和完整回归；不得以删除测试、扩大忽略或缩小扫描范围制造通过结果。

**目标：** 将后端全量 Mypy 错误从 369 条降到 0，同时保持至少 298 个源文件的扫描覆盖、新增错误阻断和覆盖收缩阻断。

**架构：** `backend/pyproject.toml` 的扫描范围及 `.github/workflows/ci.yml` 的 `check_type_baseline.py` 调用保持不变。每一轮同步删除 `backend/typecheck-baseline.json` 中已经消失的精确指纹，并在 `docs/quality-baselines/` 记录原生 Mypy、基线门禁、回归与审查结果。下表的 Q1–Q11 是质量工作轮次，不是 Harness `BATCH-XX`。

**技术栈：** Python 3.11 类型目标、Mypy 2.3.1、pytest、Ruff、uv 锁定环境。

---

## 起点与边界

2026-10-01 本地验证：`feature-harness`，HEAD `e26e9cd5a379a78b6495d891472dbdadc9d8c8fe`；Mypy 检查 298 个文件、报告 369 条错误，分布在 69 个文件。精确清单共有 191 个指纹，许可总数 369；其中 `app/` 31 条、`tests/` 338 条。工作区已有 A-L0-08 质量修复的六个已修改文件和一份未跟踪报告，属于本任务既有工作，不得覆盖。没有明确批准的 Harness 活动 Batch；若某轮发现必须改变 Harness 控制面行为或后续 Batch 的实施范围，先按仓库 `AGENTS.md` 停止该实施分支，仅完成可独立验证的类型修正和审计。

错误码库存：`arg-type` 173、`union-attr` 75、`call-arg` 61、`index` 15、`assignment` 14、`attr-defined` 11、`list-item` 6、`method-assign` 5、`operator` 3、`var-annotated` 2，以及 `type-var`、`call-overload`、`abstract`、`misc` 各 1。修复目标是全部错误码的实际诊断数归零，而非仅关闭某些错误码。

## 修复规则

1. 对 `None`、联合类型和容器下标先做真实的运行时收窄：局部变量、`is None` 分支或能在运行时失败的断言。连接未建立、断线和关闭状态应有明确结果，不用 `cast` 假定资源存在。
2. 对 Pydantic 测试夹具，保留运行时校验和 `exclude_unset` 的字段集合。动态覆盖输入可用 `model_validate(mapping)`；静态已知输入优先修正真实字段名与必填值。不得以 `model_construct()` 跳过验证。
3. 对 fake gateway、store、session 和 capability，核对真实 Protocol/基类及调用路径。补齐测试替身所需行为，或在测试确实只调用受限接口时定义准确的结构化端口；不得用宽泛 `Any`、`object`、无条件 `cast` 掩盖契约漂移。
4. 对第三方对象的 `attr-defined`、`call-overload` 和 `abstract`，先确认真实 API 与运行时行为，再修正调用、声明或测试替身。已有断言、失败路径和权限边界不得减弱。
5. 每轮只删除实际消失的许可指纹；若修复引出新的诊断，先处理新诊断及根因。清单许可总数必须等于当轮实际错误数，且门禁退出 0。

## 质量批次

表中条数和文件数是当前基线的精确分配。后续轮次的实时诊断可能因前轮类型传播而变化；每轮以重新运行的全量 Mypy 为准。

| 轮次 | 范围 | 当前错误 | 文件 | 验收重点 |
| --- | --- | ---: | ---: | --- |
| Q1 | MCP 客户端 transport、连接池、心跳与 adapter | 22 | 5 | 连接、断线、关闭、超时路径有真实状态收窄；对应 MCP 测试通过 |
| Q2 | MCP 服务端缓存键、工具 schema、Redis 初始化 | 9 | 3 | 身份与幂等语义不变；空配置有明确降级；服务端策略测试通过 |
| Q3 | MCP 协议及客户端测试 | 69 | 5 | 可空流断言与响应结构检查保留；stdio E2E、协议测试通过 |
| Q4 | 主 Runtime 决策与持久化验收测试 | 54 | 3 | fake gateway/store 与真实端口一致；决策和恢复断言保留 |
| Q5 | 审计切换验收测试 | 30 | 3 | API 参数、Capability 替身与当前契约一致 |
| Q6 | 其余验收测试 | 31 | 10 | 安全、副作用、恢复和单一控制者断言保留 |
| Q7 | Runtime 编排、推理转发、协调器测试 | 41 | 3 | 受控 Runtime 接口与测试替身一致 |
| Q8 | 其余 Harness 测试 | 24 | 8 | dispatcher、checkpoint、gateway、store 和 task 类型正确 |
| Q9 | 服务及 API 测试 | 40 | 8 | 业务模型入参、真实服务契约及资源范围保持一致 |
| Q10 | Memory 与 Trace 测试 | 30 | 11 | 结构化事件、存储与脱敏断言保持一致 |
| Q11 | 其余 Agent、Capability、Eval、Proactive 测试 | 19 | 10 | 最后清零所有错误码，原生 Mypy 退出 0 |
| **总计** | | **369** | **69** | |

### Q1 文件

`backend/app/agents/mcp/adapter.py`、`connection_pool.py`、`heartbeat.py`、`sse_transport.py`、`stdio_transport.py`。先用 `backend/tests/agents/mcp/test_transport.py` 和 `test_integration.py` 确认现有连接契约；对 stdio 的 `Process.stdin` / `stdout` 做状态检查，删除 `StreamReader.close()` 调用并验证关闭路径。`_read_loop` 的异常与 pending request 的终止语义必须审查，不能只改注解。

### Q2 文件

`backend/app/agents/registry.py`、`backend/app/main.py`、`backend/app/mcp_server/__init__.py`。MCP 写操作在进入幂等缓存前已有认证检查；类型收窄必须保持这一事实，并继续由可信 `MCPContext` 提供 `user_id`。检查 `Redis.from_url()` 收到空配置时现有回退行为，再决定是否需要显式分支。验证 `backend/tests/mcp/test_policy.py`、`test_server.py`、`test_protocol_hardening.py`。

### Q3 文件

`backend/tests/mcp/test_stdio_e2e.py`、`test_server.py`、`test_protocol_hardening.py`，以及 `backend/tests/agents/mcp/test_adapter.py`、`test_integration.py`。51 条 stdio E2E 诊断来自对可空进程流的重复访问；抽取有真实断言的局部 reader/writer，不降低协议断言。测试仍需验证真实进程退出、错误响应和超时。

### Q4 文件

`backend/tests/acceptance/test_primary_runtime_decision_loop.py`、`test_primary_runtime_canonical_persistence.py`、`test_runtime_single_owner.py`。逐个对齐 `AgentTask.task_metadata`、`AgentRuntime` 构造参数及 gateway/store/dispatcher 测试替身；不得为通过类型检查创建第二个 Run 控制者。

### Q5 文件

`backend/tests/acceptance/test_task_post_audit_010_api_cutover.py`、`test_task_post_audit_010_entrypoints.py`、`test_task_post_audit_004_contract.py`。先核对当前 API 依赖、`UserRead`、`AsyncSession`、Capability 基类和可信身份注入，再修正测试替身与调用。

### Q6 文件

`backend/tests/acceptance/test_cancel_and_recovery.py`、`test_capability_boundary.py`、`test_harness_baseline.py`、`test_primary_decision_path.py`、`test_primary_harness_flow.py`、`test_primary_harness_recovery.py`、`test_primary_harness_security.py`、`test_primary_harness_side_effects.py`、`test_restart_recovery.py`、`test_run_persistence.py`。重点保持取消、授权、审批、幂等和恢复断言。

### Q7 文件

`backend/tests/harness/test_runtime_orchestration.py`、`test_reasoning_forwarding.py`、`test_coordinator.py`。先核对 `AgentRuntime`、ModelGateway、RunStore、EventStore 的实际签名，再修正 fake 对象及 `AgentTask` 参数。

### Q8 文件

`backend/tests/harness/test_checkpoint.py`、`test_dispatcher.py`、`test_model_gateway.py`、`test_model_gateway_cancellation.py`、`test_result_normalizer.py`、`test_run_store.py`、`test_runtime.py`、`test_task.py`。对 monkeypatch 的 `method-assign` 用 pytest 的注入机制或明确端口；对可空 store/result 做运行时收窄。

### Q9 文件

`backend/tests/services/test_bangumi_client.py`、`test_bangumi_service.py`、`test_collection_service.py`、`test_stats_service.py`、`test_subject_service.py`、`test_user_profile_service.py`，以及 `backend/tests/api/test_collections_write_regression.py`、`test_dashboard_statistics.py`。检查业务模型构造、enum、fake session 与服务签名；保留资源归属和数据库写入断言。

### Q10 文件

`backend/tests/memory/test_injection.py`、`test_interfaces.py`、`test_manager.py`、`test_memory_logging.py`、`test_types.py`；`backend/tests/trace/test_agent_instrumentation.py`、`test_boundary_spans.py`、`test_event_contract.py`、`test_regressions.py`、`test_sql_store.py`、`test_trace.py`。保留不可信内容、脱敏及结构化事件边界。

### Q11 文件

`backend/tests/agents/test_base_agent.py`、`test_chat_schema.py`、`test_multi_agent_integration.py`、`test_recommendation_agent.py`、`test_workflow_lifecycle.py`；`backend/tests/capabilities/test_action_contract.py`、`test_recommendation.py`；`backend/tests/evaluation/test_judge.py`、`test_runner.py`；`backend/tests/proactive/test_scheduler.py`。

## 每轮执行与记录

- [ ] Preflight：记录 `git status --short`、分支、HEAD、任务文件边界和上一轮的门禁输出；区分已有用户修改。
- [ ] 红灯：保存该轮目标文件的原始 Mypy 诊断；必要时先添加复现运行时缺陷的失败测试，再确认失败原因。
- [ ] 实现：只改该轮文件及必要的对应测试；不修改 Mypy 覆盖范围、CI gate、依赖或其他质量轮次。
- [ ] 绿灯：运行目标 pytest、`ruff check`、`ruff format --check`，再运行全量 `mypy --no-pretty app tests alembic scripts __init__.py`，记录退出码、错误数、报错文件数和受检文件数。
- [ ] 清单：只删除已消失的精确指纹，运行 `python scripts/check_type_baseline.py`。现有 `tests/test_type_baseline.py` 必须继续证明新增错误、指纹次数增加和覆盖收缩失败。
- [ ] 回归：运行全量后端 pytest 与 Ruff；改动 Harness、MCP、Memory、Trace 时运行相应安全、恢复及 Eval 检查。记录通过、失败、跳过和警告数。
- [ ] Review：按 `docs/code-review.md` 审查完整未提交 diff；发现问题先修复、复跑，再重新审查。报告每轮结论和剩余风险，不伪造 Harness Batch execution record。

本地锁定环境命令以仓库根目录表示：

```powershell
$env:UV_CACHE_DIR = 'E:\HACCI\Documents\tools\OtakuNeko\.uv-cache'
$env:DEBUG = 'false'
uv run --locked --offline --directory backend mypy --no-pretty app tests alembic scripts __init__.py
uv run --locked --offline --directory backend python scripts/check_type_baseline.py
uv run --locked --offline --directory backend pytest -q --disable-warnings
uv run --locked --offline --directory backend ruff check app tests alembic scripts __init__.py
uv run --locked --offline --directory backend ruff format --check app tests alembic scripts __init__.py
```

最终验收：原生 Mypy 退出 0，报告至少 298 个受检文件；`typecheck-baseline.json` 的 `errors` 为空且 `checked_files` 下限不下降；基线门禁、后端全量测试、Ruff 与适用 Eval 通过；用门禁单元测试证明新增错误及覆盖收缩仍失败；报告 Q1–Q11 的实际结果与完整 diff 审查结论。未经明确授权，不提交、推送或部署。

## Exact file inventory

These paths match the current allowlist. Counts are current errors per file.

### Q1: 22 errors in 5 files

- backend/app/agents/mcp/adapter.py: 2
- backend/app/agents/mcp/connection_pool.py: 2
- backend/app/agents/mcp/heartbeat.py: 2
- backend/app/agents/mcp/sse_transport.py: 3
- backend/app/agents/mcp/stdio_transport.py: 13

### Q2: 9 errors in 3 files

- backend/app/agents/registry.py: 1
- backend/app/main.py: 1
- backend/app/mcp_server/__init__.py: 7

### Q3: 69 errors in 5 files

- backend/tests/agents/mcp/test_adapter.py: 4
- backend/tests/agents/mcp/test_integration.py: 1
- backend/tests/mcp/test_protocol_hardening.py: 6
- backend/tests/mcp/test_server.py: 7
- backend/tests/mcp/test_stdio_e2e.py: 51

### Q4: 54 errors in 3 files

- backend/tests/acceptance/test_primary_runtime_canonical_persistence.py: 11
- backend/tests/acceptance/test_primary_runtime_decision_loop.py: 36
- backend/tests/acceptance/test_runtime_single_owner.py: 7

### Q5: 30 errors in 3 files

- backend/tests/acceptance/test_task_post_audit_004_contract.py: 5
- backend/tests/acceptance/test_task_post_audit_010_api_cutover.py: 22
- backend/tests/acceptance/test_task_post_audit_010_entrypoints.py: 3

### Q6: 31 errors in 10 files

- backend/tests/acceptance/test_cancel_and_recovery.py: 2
- backend/tests/acceptance/test_capability_boundary.py: 5
- backend/tests/acceptance/test_harness_baseline.py: 2
- backend/tests/acceptance/test_primary_decision_path.py: 4
- backend/tests/acceptance/test_primary_harness_flow.py: 4
- backend/tests/acceptance/test_primary_harness_recovery.py: 1
- backend/tests/acceptance/test_primary_harness_security.py: 4
- backend/tests/acceptance/test_primary_harness_side_effects.py: 5
- backend/tests/acceptance/test_restart_recovery.py: 3
- backend/tests/acceptance/test_run_persistence.py: 1

### Q7: 41 errors in 3 files

- backend/tests/harness/test_coordinator.py: 8
- backend/tests/harness/test_reasoning_forwarding.py: 9
- backend/tests/harness/test_runtime_orchestration.py: 24

### Q8: 24 errors in 8 files

- backend/tests/harness/test_checkpoint.py: 5
- backend/tests/harness/test_dispatcher.py: 6
- backend/tests/harness/test_model_gateway.py: 4
- backend/tests/harness/test_model_gateway_cancellation.py: 4
- backend/tests/harness/test_result_normalizer.py: 1
- backend/tests/harness/test_run_store.py: 1
- backend/tests/harness/test_runtime.py: 1
- backend/tests/harness/test_task.py: 2

### Q9: 40 errors in 8 files

- backend/tests/api/test_collections_write_regression.py: 2
- backend/tests/api/test_dashboard_statistics.py: 2
- backend/tests/services/test_bangumi_client.py: 1
- backend/tests/services/test_bangumi_service.py: 5
- backend/tests/services/test_collection_service.py: 17
- backend/tests/services/test_stats_service.py: 2
- backend/tests/services/test_subject_service.py: 3
- backend/tests/services/test_user_profile_service.py: 8

### Q10: 30 errors in 11 files

- backend/tests/memory/test_injection.py: 3
- backend/tests/memory/test_interfaces.py: 4
- backend/tests/memory/test_manager.py: 1
- backend/tests/memory/test_memory_logging.py: 1
- backend/tests/memory/test_types.py: 2
- backend/tests/trace/test_agent_instrumentation.py: 5
- backend/tests/trace/test_boundary_spans.py: 1
- backend/tests/trace/test_event_contract.py: 5
- backend/tests/trace/test_regressions.py: 2
- backend/tests/trace/test_sql_store.py: 5
- backend/tests/trace/test_trace.py: 1

### Q11: 19 errors in 10 files

- backend/tests/agents/test_base_agent.py: 1
- backend/tests/agents/test_chat_schema.py: 1
- backend/tests/agents/test_multi_agent_integration.py: 2
- backend/tests/agents/test_recommendation_agent.py: 2
- backend/tests/agents/test_workflow_lifecycle.py: 3
- backend/tests/capabilities/test_action_contract.py: 1
- backend/tests/capabilities/test_recommendation.py: 1
- backend/tests/evaluation/test_judge.py: 3
- backend/tests/evaluation/test_runner.py: 4
- backend/tests/proactive/test_scheduler.py: 1
