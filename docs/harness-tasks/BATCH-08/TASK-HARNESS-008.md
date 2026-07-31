# TASK-HARNESS-008

## 目标

为交互 Run 绑定可恢复的 LangGraph checkpoint、服务重启状态和取消传播，不改变 Run/Event schema 或前端 replay 协议。

## 背景

对应 `G-P1-03`、`G-P1-08`。当前 `ChatWorkflow._ensure_checkpointer()` 每次打开 `data/checkpoints.db` 的 `AsyncSqliteSaver`，而 `AgentRuntime` 主聊天没有传入 `CheckpointStore`；Docker backend 没有挂载 `data/`（`backend/app/agents/graph.py:44-88`; `backend/app/api/v1/agent.py:176-219`; `docker-compose.yml:73-125`）。参考文档 Batch 6 要求 checkpoint、暂停、approval、重启恢复和取消传播（参考文档:1972-1978）。

## 允许修改

- `backend/app/harness/checkpoint.py`
- `backend/app/agents/graph.py` 的 checkpoint/cancel adapter 部分
- `backend/app/agents/langgraph_adapter.py`
- `backend/app/api/v1/agent.py` 的 workflow 生命周期 wiring
- `backend/app/core/config.py`
- `docker-compose.yml` 的 backend data volume 配置
- `backend/tests/agents/test_graph_checkpoint.py`
- `backend/tests/agents/test_workflow_lifecycle.py`
- `backend/tests/harness/test_checkpoint.py`
- `backend/tests/acceptance/test_restart_recovery.py`

## 禁止修改

- Run/Event 数据模型与 Alembic（BATCH-06 已定义）
- 前端 SSE/fetcher、全部 Tool/Capability、qBittorrent/收藏/日程 Service
- 将本地 SQLite 文件直接宣称为多 worker 共享存储而不做并发测试
- 删除现有 `data/checkpoints.db` 兼容读取能力

## 实施要求

1. 扩展 checkpoint port：`save(run_id, thread_id, state)`, `load(run_id, thread_id)`, `mark_abandoned(run_id, reason)`；保持 `InMemoryCheckpointStore` 测试实现，新增可配置 file/DB adapter，不让 Runtime 依赖 LangGraph 类型。
2. `ChatWorkflow` 接收已解析的 checkpoint path/adapter 和 immutable `run_id/thread_id`；同一个 run 不重复打开多条无关连接，`close()` 必须在成功、失败、cancel、generator close 后执行。
3. `CancellationToken` 从 BATCH-05 传入；Graph/adapter 在开始、每个模型事件、Tool 事件后检查；取消只产生一次 `cancelled` terminal event，不把前端停止当作成功。
4. 对服务重启：Run 状态为 running 且 lease 过期时标为 `abandoned` 或由受控 recovery worker 恢复；恢复不得自动重放已完成的 side-effect invocation。
5. Docker 只增加明确的 backend data volume/配置说明；如果部署采用 shared PostgreSQL checkpoint，则以 adapter 接口接入，不在本任务强行替换 LangGraph provider。
6. `resume_chat` 的 approval interrupt 只能恢复同一 user/thread/run scope；`approve/reject` 不得来自模型输出或未认证 query。

## 兼容要求

- 本地默认 `data/checkpoints.db` 仍可用于开发；路径可通过 settings 覆盖。
- 旧 thread history/reasoning API 继续工作；未携带 run_id 的旧请求使用兼容 run 创建路径。
- Proactive scheduler 的 lease 机制不被修改，交互 checkpoint 与 scheduled run 保持标识隔离。
- 多 worker 未验证共享 checkpoint 前，部署配置应明确单 worker/共享存储约束。

## 测试

- 单元测试：checkpoint save/load/close、重复恢复、取消 token、approval user scope、非法状态恢复。
- 集成测试：temp SQLite 写入后关闭 workflow，再新建 workflow 读取；fake provider 在 cancel 后不再收到下一次调用；服务重启模拟不重复 invocation。
- 回归测试：`cd backend && uv run pytest tests/agents/test_graph_checkpoint.py tests/agents/test_workflow_lifecycle.py tests/harness/test_checkpoint.py tests/trace/test_agent_instrumentation.py -q`。
- 手工验证：`docker compose config` 检查 backend data volume；启动一次只读聊天后重启 backend，查询 Run/checkpoint 状态。

## 验收标准

- [ ] checkpoint 有明确 run/thread scope 和关闭语义。
- [ ] cancel 能传播到 adapter/provider 边界，terminal state 为 cancelled。
- [ ] 重启不会把 running/已完成副作用隐式重放；无法恢复时标记 abandoned 并可查询。
- [ ] approval resume 有认证和 owner scope。
- [ ] SQLite/dev 与实际 Docker 配置差异被测试/文档明确，没有声称未验证的多 worker 能力。

## 回滚

通过 `HARNESS_CHECKPOINT_ADAPTER=legacy` 回退现有 `AsyncSqliteSaver`；保留 Run/Event 状态为 abandoned 的记录，不删除 checkpoint 文件。若取消桥接不稳定，禁用新 cancel adapter 并继续 fail closed，不把 abort 视为 succeeded。

## 输出

- 修改文件列表：记录 checkpoint port、Graph lifecycle、config/compose 和测试。
- 测试结果：报告 temp DB reopen、cancel、approval scope、compose config 结果。
- 未解决问题：记录生产 shared checkpoint backend 和多 worker lease 的运行态证据。
- 风险说明：说明旧 checkpoint 与新 run_id 映射的兼容范围。
