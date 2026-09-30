# TASK-HARNESS-006

## 目标

为交互 Run 建立持久化的 Run、Invocation、Event Store，并让 Coordinator 在关键状态转移时追加可重放事件；不修改前端协议。

## 背景

对应 `G-P1-03`、`G-P1-06`、`G-P1-08`。当前 SQL Trace 可持久化聚合 Trace，但聊天没有独立 Run/Invocation/Event 真值；Graph checkpoint 是单独 `data/checkpoints.db`；Docker backend 没有挂载该目录（`backend/app/trace/sql_store.py`; `backend/app/api/v1/agent.py:176-219`; `backend/app/agents/graph.py:44-78`; `docker-compose.yml:73-125`）。参考文档 Batch 5 要求 Run Store、Step/Invocation、Event sequence（参考文档:1964-1970）。

## 允许修改

- 新建 `backend/app/models/agent_run.py`
- 新建 `backend/app/harness/persistence/run_store.py`
- 新建 `backend/app/harness/persistence/event_store.py`
- 新建 `backend/alembic/versions/<new_revision>_add_interactive_run_tables.py`
- `backend/app/harness/coordinator.py`
- `backend/app/harness/runtime.py`
- `backend/app/models/__init__.py`
- `backend/alembic/env.py` 的模型注册
- `backend/tests/harness/test_run_store.py`
- `backend/tests/harness/test_event_store.py`
- `backend/tests/acceptance/test_run_persistence.py`

## 禁止修改

- `frontend/src/` 和现有 SSE event payload
- `backend/app/agents/graph.py` checkpoint 实现
- 现有 `agent_task_def/agent_task_run` 语义、收藏/日程/qB 表
- 删除或重命名现有 `agent_trace/trace_event` 表
- 修改依赖版本；不在本 PR 迁移历史数据

## 实施要求

1. 新增 `AgentRun`：`run_id` 主键、`user_id` nullable、`thread_id`、`status`、`goal_hash`、`model`、`started_at`、`finished_at`、`error_code`、`created_at`；`status` 固定 `queued/running/succeeded/failed/cancelled/paused/abandoned`。
2. 新增 `AgentInvocation`：`invocation_id` 主键、`run_id` 外键、`sequence`、`capability`、`capability_version`、`status`、`input_hash`、`idempotency_key`、`started_at`、`finished_at`、`error_code`；对 `(run_id, sequence)` 和 `(run_id, idempotency_key)` 建唯一约束/索引，空 key 不参与重复约束。
3. 新增 `AgentRunEvent`：`event_id`、`run_id`、单调 `sequence`、`event_type`、`invocation_id` nullable、JSON safe payload、`occurred_at`；append 使用事务和唯一键，重复 event 不产生第二行。
4. `RunStore` 提供 `create/get/transition`，`EventStore` 提供 `append/list_after`；transition 只允许有限状态表，错误返回 `InvalidRunTransition`。
5. Coordinator 在 run start、decision、invocation start/end、message chunk、terminal state 处写事件；写失败不能把外部 Tool 当成功，需返回持久化错误并保留安全状态。
6. 使用 SQLModel/Alembic 的现有模式；启动 `create_all` 不替代 migration。为 SQLite 和 PostgreSQL 写同一行为测试。

## 兼容要求

- 现有 `SqlTraceStore` 继续工作；第一版 Run/Event 可以记录 Trace ID，但不把 Trace 表当作 Run 真值。
- 主聊天 API 的旧响应和 SSE event name 不变；前端继续只消费原事件。
- `AgentTask.task_id` 为空的旧调用仍可运行，Coordinator 生成独立 `run_id`。
- 写操作没有接入前，幂等表只记录 invocation，不触发新副作用。

## 测试

- 单元测试：状态转移矩阵、sequence 唯一性、idempotency payload hash conflict、safe JSON payload 限制。
- 集成测试：临时 SQLite fresh schema 创建/append/list/重启读取；PostgreSQL 测试使用现有可选环境，缺少服务时显式 skip 并报告原因。
- 回归测试：`cd backend && uv run pytest tests/harness tests/trace/test_sql_store.py tests/memory/test_migration.py tests/acceptance/test_run_persistence.py -q`。
- 手工验证：启动后端执行只读聊天，查询 Run 状态和事件数量；确认前端旧 SSE 仍正常。

## 验收标准

- [ ] 每次交互请求有唯一 Run ID，事件 sequence 可按时间/序列读取。
- [ ] 重复 append、重复 terminal transition、不同 payload 复用 idempotency key 都有确定结果。
- [ ] SQLite/PostgreSQL 使用相同模型和状态规则；Alembic revision 可在 fresh DB 应用。
- [ ] Run/Event 失败不会伪造模型/Tool 成功，旧 Trace/SSE/API 兼容。
- [ ] 本 PR 不修改前端，不改变 Graph Loop 和现有业务表。

## 回滚

关闭 `INTERACTIVE_RUN_STORE_ENABLED` 后使用现有 Runtime/Trace 路径；数据库 migration 保留但不删除已有 Run/Event 数据。若写事件失败，回滚为只读回答并明确返回 persistence error，不绕过授权或副作用 policy。

## 输出

- 修改文件列表：记录模型、store、migration、Coordinator hook 和测试。
- 测试结果：报告 SQLite、可用的 PostgreSQL、状态转移和唯一约束结果。
- 未解决问题：记录 checkpoint 共享、SSE replay 和生产卷配置交由 BATCH-07/08。
- 风险说明：说明新增表的 retention、备份和 migration rollback 影响。
