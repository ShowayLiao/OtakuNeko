# 状态、持久化与恢复

## 状态对象分层

| 状态 | 当前载体 | Owner | 生命周期 | 结论 |
|---|---|---|---|---|
| UI Session | Zustand `sessions`, `chatMessages`, `sessionConfigs` | 浏览器 | localStorage；仅 UI | 不是服务端 Run；可被客户端删除/改写显示状态（`frontend/src/stores/useChatStore.ts:52-78,80-247`）。 |
| Chat thread | `make_anonymous_thread` / `make_user_thread` | API + LangGraph `thread_id` | 请求/Checkpoint | 有 owner prefix，但没有 Session/Run 表（`backend/app/api/v1/agent.py:55-73,193-209`; `backend/app/agents/thread_scope.py`）。 |
| `AgentTask` | Pydantic 对象，主聊天只填 `user_id/goal/metadata` | API | 单次请求 | 主聊天不提供 `task_id`，metadata 还携带原始 messages/collections（`backend/app/harness/task.py:1-80`; `backend/app/api/v1/agent.py:193-209`）。 |
| `AgentState` | Pydantic `task/current_step/context/result/status` | `AgentRuntime` | stream generator | 仅可选 `CheckpointStore` 才保存；主聊天没有注入（`backend/app/harness/state.py:1-90`; `backend/app/harness/runtime.py:57-70,181-219`）。 |
| Graph state | LangGraph `CodingAgentState` | `ChatWorkflow` | 每次图运行 + SQLite checkpoint | 有 messages/plan/trace 等，但不是 Harness Run 状态；没有 owner/user_id/budget/cancel 字段（`backend/app/agents/graph.py:23-30`）。 |
| Memory facts | `agent_memory` SQL 表；旧实现还用 LangGraph Store | `MemoryServiceImpl` / `MemoryManager` | user/线程/retention | SQL 主路径有 owner scope；两套实现并存（`backend/app/memory/service.py:1-276`; `backend/app/memory/manager.py:1-220`; `backend/app/memory/sql_repository.py:1-260`）。 |
| Trace | `agent_trace` + `trace_event` 或 InMemory | `SqlTraceStore` / `TraceRecorder` | 通常一次 stream 结束时 | 具备用户范围和 redaction，但不是实时 Event Store（`backend/app/trace/sql_store.py:1-220`; `backend/app/api/v1/agent.py:176-219`）。 |
| Scheduled Run | `agent_task_def` + `agent_task_run` | `SqlTaskRepository` + scheduler | durable lease | 这是目前最接近 Durable Run 的实现，但仅覆盖 Proactive，不覆盖交互聊天（`backend/app/models/agent_task.py:24-80`; `backend/app/harness/scheduler/repository.py:238-319`）。 |

## 主聊天持久化链路

1. 业务 DB：`app.main.lifespan` 调用 `init_db()`，`init_db` 执行 `SQLModel.metadata.create_all`（`backend/app/main.py:35-48`; `backend/app/db/database.py:37-48`）。
2. Graph checkpoint：`ChatWorkflow._ensure_checkpointer()` 创建 `aiosqlite.connect(self.db_path)` 和 `AsyncSqliteSaver`，默认路径 `data/checkpoints.db`（`backend/app/agents/graph.py:44-78`）。
3. Runtime checkpoint：接口存在 `CheckpointStore` 和 `InMemoryCheckpointStore`，但 `api/v1/agent.py` 构造 `AgentRuntime` 时只传 `adapter/trace_store/model_gateway`（`backend/app/harness/checkpoint.py:1-55`; `backend/app/api/v1/agent.py:176-191`）。
4. Trace：Runtime 创建 `AgentTrace`，adapter/graph 记录部分事件，完成或异常时由 `SqlTraceStore.record` 持久化（`backend/app/harness/runtime.py:181-336`; `backend/app/trace/sql_store.py:1-220`）。
5. Memory：聊天结束后再从 checkpoint 读取最近消息做一次 `LLMFactExtractor`，写入 SQL Memory（`backend/app/api/v1/agent.py:233-237`; `backend/app/memory/service.py:237-276`）。

这五个状态链路没有共同的 `run_id`/`invocation_id`/事件序号和事务边界。LangGraph 的 `thread_id`、Trace 的随机 `trace_id`、前端的 session ID、Proactive 的 `run.id` 不是同一个标识体系。

## SQLite / PostgreSQL 模式

| 项目 | local | cloud | 一致性结论 |
|---|---|---|---|
| 业务 DB | `sqlite+aiosqlite`, `./local.db` | `postgresql+asyncpg` | 配置切换明确（`backend/app/core/config.py:22-49`）。 |
| FastAPI cache | InMemoryBackend | 仍是 InMemoryBackend，Redis 仅 ping | cloud 并未得到跨进程 cache（`backend/app/main.py:81-119`）。 |
| Graph checkpoint | SQLite file | 仍是 SQLite file | 没有 PostgreSQL checkpoint adapter；云模式 DB 与图状态分离（`backend/app/agents/graph.py:44-78`）。 |
| SQL migrations | Alembic versions 存在 | `alembic/env.py` 使用 settings DATABASE_URL | 启动只 `create_all`，Dockerfile/compose 未显示自动 `alembic upgrade`（`backend/app/main.py:39-44`; `backend/Dockerfile:19-20`）。 |
| Model registration | `app/models/__init__.py` 导出 task/trace/memory | Alembic `env.py` 只显式导入 collection/subject/user/agent_memory | 未来 autogenerate 的模型元数据完整性未确认（`backend/app/models/__init__.py:1-15`; `backend/alembic/env.py:8-24`）。 |

## 恢复矩阵

| 事件 | 当前行为 | 可否恢复 | 证据/缺口 |
|---|---|---|---|
| SSE 正常结束 | graph checkpoint 可能保存；Runtime state 不保存 | 只能按 thread 查询/继续图，不能按 Run 重放 SSE | `backend/app/api/v1/agent.py:252-409`; G-P1-03 |
| SSE 断开 | 前端 abort/reader close；服务端 Run 没有显式状态端点 | 未实现断线补拉；是否下游取消未确认 | `frontend/src/lib/fetcher.ts:147-177,277-290`; G-P1-03 |
| 用户 stop | UI 把 pending 标成 success；服务端取消状态未落库 | 不可靠 | `frontend/src/hooks/useChatStreaming.ts:285-323`; G-P1-05 |
| provider timeout | 图 model timeout 90s；Graph 捕获后发 error chunk | 不会自动以统一 retry policy 恢复 | `backend/app/agents/graph.py:195-231,470-477`; G-P1-05、G-P1-11 |
| 进程重启（本地） | checkpoint file 可能仍在；内存 cache/Runtime/Trace InMemory 丢失 | 仅图 thread 层可能恢复 | `backend/app/agents/graph.py:44-78`; `backend/app/main.py:81-89` |
| Docker backend 重建 | backend 没有挂载 data | checkpoint 是否保留：按仓库配置不保留 | `docker-compose.yml:73-125`; G-P1-08 |
| Proactive worker 重启 | SQL run 有 lease，过期后可重新 claim | 部分支持；需实际部署单 worker/多 worker 验证 | `backend/app/harness/scheduler/repository.py:238-319`; `backend/app/harness/scheduler/execution.py:83-124` |

## Memory 状态风险

SQL Memory 在 `store_fact` 中按 `user_id`、kind、thread scope 写入并有 retention/rollback，属于正向设计（`backend/app/memory/service.py:68-167`; `backend/app/memory/sql_repository.py`）。但事实提取在回答结束后读取 checkpoint 最近 20 条 message，提示词把对话内容直接作为输入，未区分用户指令、外部 Tool output 和已验证事实（`backend/app/memory/service.py:237-276`; `backend/app/memory/extractor.py:1-160`）。这会让 Memory 成为长期提示注入/错误事实的持久化点，记录为 G-P1-10。

同时 `MemoryManager`/`StoreMemoryRepository` 仍保留另一套 LangGraph Store 语义；两者的 `retrieve_context`/`load_context`、embedding 存储和 namespace 规则不同（`backend/app/memory/manager.py:1-220`; `backend/app/memory/repository.py:1-120`; `backend/app/memory/service.py:169-235`）。当前主路径使用 SQL 版本，但退役边界未明确。
