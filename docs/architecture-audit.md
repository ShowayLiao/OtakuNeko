# OtakuNeko Agent Architecture Audit

> 状态：历史快照，已被 `docs/reports/rfc-106-acceptance.md`（2026-07-30）及其后续提交部分取代。原审计未记录可复现的 commit SHA；以下结论只代表 2026-07-22 审计时的工作树，不应作为当前架构状态或验收证据。

> 审计日期：2026-07-22
> 审计对象：`backend/app`、`backend/tests`、`frontend/src`、部署与迁移配置；结论基于审计结束前的当前工作树。审计期间 `backend/app/mcp_server/*` 存在并发未提交修改，因此 MCP 部分按最终复核快照评价。
> 限制：本次只分析，不修改业务代码。除本报告外未写入项目文件。

## Executive Summary

OtakuNeko 已经不是传统 CRUD 项目的“Agent 零起点”。当前代码具备 LangGraph 工作流、SQLite checkpoint、短期/长期 Memory 接口、Capability Registry、MCP Server、Agent Harness、Trace API 和 SSE 工具事件等基础构件。真正的短板不是目录缺失，而是这些构件尚未形成统一、持久、可恢复、可审计的运行时闭环。

当前最关键的问题是：

1. `backend/app/api/v1/agent.py:47` 的 `_get_or_create_memory()` 创建 `MemoryServiceImpl`，`chat_endpoint()` 在 `backend/app/api/v1/agent.py:152-154` 将其注入 `ChatWorkflow`；但 `ChatWorkflow.stream_chat()` 在 `backend/app/agents/graph.py:234-240` 调用 `load_context()`，而 `MemoryServiceImpl` 只在 `backend/app/memory/service.py:92` 提供 `retrieve_context()`。类契约自省确认 `MemoryServiceImpl.load_context=False`。因此登录用户的真实聊天主链路会在加载 Memory 时发生接口错配。
2. Agent 的长期 Memory 与 Trace 使用模块级 `InMemoryStore` / `InMemoryTraceStore`（`backend/app/api/v1/agent.py:40-43`）；进程重启、多 worker 和横向扩容会造成数据丢失或视图分裂。LangGraph 对话 checkpoint 虽写入 `data/checkpoints.db`（`backend/app/agents/graph.py:45-74`），但与业务库、任务状态、Trace 和 Memory 分属不同生命周期。
3. `AgentTask`、`AgentState`、`CheckpointStore` 已有契约，但 `AgentTask.task_id` 默认为空（`backend/app/harness/task.py:19`），聊天端点未分配持久任务 ID（`backend/app/api/v1/agent.py:164-168`），且主路径构造 `AgentRuntime` 时没有传入 `checkpoint_store`（`backend/app/api/v1/agent.py:146-147`）。Harness 状态保存能力因此没有接入生产聊天路径。
4. Tool/Capability 层成熟度高于其他维度：`ActionDescriptor` 已有名称、描述、输入 Schema、认证和副作用标记（`backend/app/capabilities/types.py:14-35`），MCP 调度也执行认证、side-effect 与幂等策略（`backend/app/mcp_server/__init__.py:305-338`）。但 action 缺少输出 Schema 和独立版本；Agent 仍通过 `ToolRegistry` + 静态 `ALL_TOOLS` 装配（`backend/app/agents/registry.py:5-38`、`backend/app/agents/tools.py:18-26`），Capability Registry 主要服务 MCP，尚非全系统唯一能力源。
5. 数据库 CRUD 分层可用，但并不严格。四个 Repository 内约有 83 处查询/事务原语；Service/API 仍约有 26 处直接数据库原语。典型越层点包括 `sync_user_collections()`（`backend/app/services/bangumi_service.py:233-247`）、`sync_bangumi_data()`（`backend/app/services/bangumi_data_sync.py:188-218`）、`get_user_stats()`（`backend/app/services/stats_service.py:46-59`）以及认证依赖（`backend/app/api/deps.py:65-66,110`）。

## Audit Method and Evidence

- 扫描 114 个后端 Python 源文件、86 个前端 TypeScript/TSX 源文件。
- 逐项检索数据库访问、状态、Memory、Context、Tool、Trace、任务、Artifact、知识实体和 API。
- 对 Agent/Memory/Harness/Trace/Capability/MCP 相关测试运行：`269 passed, 22 warnings in 12.72s`。
- 测试警告包括 Pydantic V2 class-based config 弃用，以及 `tests/agents/test_graph_dual_node.py` 中一次 aiosqlite worker 在线程结束后访问已关闭 event loop 的资源生命周期警告。
- 现有 269 个测试通过不否定 Memory 装配问题：旧 `MemoryManager` 测试调用 `load_context()`，新 `MemoryServiceImpl` 测试调用 `retrieve_context()`；`tests/harness/test_api_regression.py:28-35` 又用 `FakeWorkflow` 替换真实 `ChatWorkflow`，没有覆盖二者的真实装配边界。

## Current Architecture

### 项目语言与技术栈

| 区域 | 当前实现 | 证据 |
|---|---|---|
| Backend | Python 3.11+、FastAPI、Pydantic、SQLModel/SQLAlchemy Async | `backend/pyproject.toml`、`backend/requirements.txt`、`backend/app/main.py:1-6` |
| Agent | LangGraph StateGraph、LangChain tools、OpenAI-compatible provider、SSE | `backend/app/agents/graph.py:4-12,90-108`、`backend/app/api/v1/agent.py:104-205` |
| Database | SQLite 本地 / PostgreSQL 云端，Alembic | `backend/app/core/config.py:14-45`、`backend/alembic/versions/*` |
| Memory | LangGraph checkpoint + Store、BM25 + embeddings hybrid retrieval | `backend/app/memory/service.py:28-52,92-153` |
| Tool/Capability | LangChain `@tool`、Capability Registry、MCP stdio server | `backend/app/agents/tools.py:18-26`、`backend/app/capabilities/registry.py:14-64`、`backend/app/mcp_server/entry.py:27-47` |
| Observability | Python logging、SSE process events、in-memory Agent Trace | `backend/app/core/logging.py:35-169`、`backend/app/harness/runtime.py:100-131` |
| Async task | Celery 目录存在但未实现 | `backend/app/worker/celery_app.py:1` |
| Frontend | Next.js 16、React 19、TypeScript、Zustand、SSE client | `frontend/package.json`、`frontend/src/hooks/useChatStreaming.ts:325-584` |
| Deployment | PostgreSQL、Redis、backend、qBittorrent、frontend 五服务 | `docker-compose.yml:7-124` |

### 服务边界

当前后端可分为以下边界：

- HTTP API：`backend/app/api/v1/*`，负责鉴权、请求/响应和 SSE。
- 业务 Service：`backend/app/services/*`，覆盖收藏、条目、排班、Bangumi/豆瓣同步、统计、用户画像和 qBittorrent。
- Repository：`backend/app/repositories/*`，覆盖 User、Subject、Collection、Schedule。
- Agent Runtime：`backend/app/agents/*` + `backend/app/harness/*`。
- Memory：`backend/app/memory/*`。
- Capability/MCP：`backend/app/capabilities/*` + `backend/app/mcp_server/*`。
- Trace：`backend/app/trace/*` + `backend/app/api/v1/trace.py`。
- Frontend：页面 → Zustand store/hooks → services/fetcher → FastAPI。
- 外部系统：Bangumi API/HTML、OpenAI-compatible LLM、qBittorrent、PostgreSQL、Redis。

### 模块依赖关系

```text
frontend page/component
  -> frontend hook/service
  -> FastAPI router
     -> service -> repository -> SQLModel/DB
     -> AgentRuntime -> LangGraphAdapter -> ChatWorkflow
        -> ToolRegistry -> LangChain tools -> Capability -> service/external API
        -> AsyncSqliteSaver (conversation checkpoint)
        -> MemoryServiceImpl -> MemoryRepository -> InMemoryStore
     -> InMemoryTraceStore

MCP stdio
  -> ExposureMap/MCP policy
  -> CapabilityRegistry
  -> Capability -> service/repository/external API
```

未在显式 `app.*` import 中发现 Service ↔ Repository 或 Agent ↔ Memory 的静态闭环；因此没有证据证明存在已触发的循环依赖。不过存在 import-time 装配耦合：`backend/app/api/v1/__init__.py:2` 同时导入 `agent` 与 `trace`，而 `backend/app/api/v1/agent.py:36-42` 又导入 `app.api.v1.trace` 并在模块加载时注入 store。建议把它归类为“隐式初始化顺序依赖”，而不是已证实的循环依赖。

### 数据流

#### 普通业务 CRUD

1. 前端 Service 附带 localStorage 中的 JWT（`frontend/src/services/client.ts:5-6`）。
2. FastAPI router 通过 `get_current_user()` 解析身份（`backend/app/api/deps.py:20-66`）。
3. Router 调用业务 Service；多数 Service 调用 Repository。
4. Repository 使用 AsyncSession/SQLModel 查询并自行 commit/rollback。
5. Schema/`adaptersV2.py` 将 ORM 与外部 API 数据转为统一响应。

#### Agent 聊天

1. `useChatStreaming.startStreaming()` 将当前会话消息、角色 Prompt、模型、温度和 `thread_id` 发往后端（`frontend/src/hooks/useChatStreaming.ts:325-353`）。
2. `chat_endpoint()` 过滤客户端 system 消息、构造 owner-scoped thread ID，并创建 `ChatWorkflow`、`LangGraphAdapter`、`AgentRuntime`、Memory 和 AgentTask（`backend/app/api/v1/agent.py:119-178`）。
3. `ChatWorkflow` 编译 `think -> tools -> think -> speak` 图（`backend/app/agents/graph.py:90-108`），使用 SQLite saver 保存 LangGraph checkpoint。
4. `stream_chat()` 尝试装入 Memory 上下文、绑定工具、设置 24 步递归上限和 90 秒 provider timeout（`backend/app/agents/graph.py:195-247`）。
5. LangGraph events 被转换成 thinking/tool/message SSE，前端将其写入过程节点和消息状态（`frontend/src/hooks/useChatStreaming.ts:373-548`）。
6. 成功结束后，对已登录用户抽取长期事实（`backend/app/api/v1/agent.py:192-193`）；Trace Runtime 只保存任务级 start/end/failure 结果。

#### 收藏同步

1. `collections.py` 的 `/sync/bgm`、`/upload/douban` 或 `/sync/manual` 进入同步 Service（`backend/app/api/v1/collections.py:347-455`）。
2. Bangumi/豆瓣客户端抓取外部数据。
3. `backend/app/schemas/adaptersV2.py` 执行大量字段归一化。
4. Repository batch upsert Subject/Collection；部分 Service 同时直接查询/写数据库。

### 核心业务流程

- 用户登录与 JWT 鉴权：`backend/app/api/v1/auth.py:32-89`。
- Bangumi/豆瓣收藏导入、标准化与 upsert：`backend/app/api/v1/collections.py:347-455`、`backend/app/services/collection_service.py`、`backend/app/schemas/adaptersV2.py`。
- 条目查询与详情同步：`backend/app/api/v1/subjects.py:30-230`。
- 放送/观看排班：`backend/app/api/v1/endpoints/schedules.py:18-264`。
- RSS/qBittorrent 订阅管理：`backend/app/api/v1/rss.py:18-98`、`backend/app/services/qb_service.py:75-237`。
- Agent 动漫搜索、资料查询、用户画像与推荐解释：`backend/app/agents/graph.py`、`backend/app/agents/tools.py`、`backend/app/capabilities/*`。

### Architecture Checklist

- [x] 存在 domain/service/repository 形态的分层，但缺少独立 domain entity/use-case 层，且执行不严格。
- [x] 未发现已证实的静态循环依赖。
- [x] 存在跨模块直接调用：Capability → Service、Agent Tool → Capability、API → 多个 Service/Repository/Model。
- [x] 存在全局状态：`_store`、`_trace_store`、`_memory_services`（`backend/app/api/v1/agent.py:40-44`）以及前端持久 Zustand stores。
- [x] 存在隐藏业务逻辑：`backend/app/schemas/adaptersV2.py:102-914` 承载外部数据归一化；`backend/app/agents/graph.py:195-490` 同时承担上下文、LLM、工具和事件翻译；`backend/app/services/qb_service.py:115-144` 在 upsert 内隐式执行删除后重建。

## Architecture Overview

### Current

当前是“分层 CRUD + 内嵌 Agent 子系统”的模块化单体。业务库、LangGraph checkpoint、Memory store、Trace store 和前端 localStorage 各自持有不同部分的状态。Capability/MCP 已建立结构化能力边界，但 HTTP Agent 仍直接装配运行时和进程内 store，任务、事件与 Artifact 没有成为统一的一等领域对象。

### Recommended

保留模块化单体部署，先演进为单进程也可可靠运行的 Agent-native Backend：

```text
Agent API
  -> Agent Application Service
     -> TaskRepository / RunRepository
     -> AgentRuntime
        -> ContextBuilder
        -> CapabilityRegistry (唯一能力源)
        -> CheckpointRepository
        -> MemoryService
        -> EventSink / TraceRepository
        -> ArtifactRepository

Business capabilities
  -> Domain/Application services
  -> Repositories
  -> SQLite/PostgreSQL
```

这里不建议立即拆微服务。先把状态与接口统一并可持久恢复，再根据吞吐和故障域拆 worker 或独立服务。

## Database Assessment

### 1.1 数据访问模式

- ORM：SQLModel + SQLAlchemy AsyncSession（`backend/app/db/database.py:1-40`）。
- Repository：存在 `UserRepo`、`SubjectRepo`、`CollectionRepo`、`ScheduleRepository`。
- Service 直接数据库：存在。最明确的是 `bangumi_service.sync_user_collections()`、`bangumi_data_sync`、`stats_service.get_user_stats()` 和 `subject_service` 尾部的写入逻辑。
- API 直接数据库：鉴权依赖直接 select User；部分 router 管理 rollback。业务查询大多仍通过 Service/Repository。
- SQL 散落：未发现应用源码中的手写 SQL 字符串；但 ORM 查询散落在 Repository、Service 和 API dependency 三层。
- 模型与业务耦合：中高。`Subject` 直接镜像 Bangumi/豆瓣 payload，大量 `JSON` 字段保存 `tags`、`infobox`、`rating`、`collection`（`backend/app/models/subject.py:33-44`），使外部源格式、存储模型与推荐/知识检索逻辑耦合。

#### Database Access Points

下表的“数量”是 `(db|session).execute/exec/add/delete/commit/refresh/rollback` 静态匹配数，用于展示分布，不等价于独立 SQL 数。

| 层 | 文件 | 数量 | 代表行 / pattern |
|---|---|---:|---|
| Repository | `backend/app/repositories/user_repo.py` | 16 | `create():36-42`、`get_by_id():61`、`update():182-188` |
| Repository | `backend/app/repositories/subject_repo.py` | 22 | `get_by_source():97-109`、`batch_upsert():421-573` |
| Repository | `backend/app/repositories/collection_repo.py` | 18 | `create():47-55` 及 CRUD/batch upsert |
| Repository | `backend/app/repositories/schedule_repo.py` | 27 | `get_by_user():36-37`、`batch_upsert():342-448`、`upsert():452-544` |
| Service | `backend/app/services/bangumi_data_sync.py` | 7 | `sync_bangumi_data():188-218,272-275,322-340` |
| Service | `backend/app/services/bangumi_service.py` | 5 | `sync_user_collections():233-247,332` |
| Service | `backend/app/services/subject_service.py` | 3 | `:469-475` |
| Service | `backend/app/services/stats_service.py` | 1 | `get_user_stats():46-59` |
| Service | `backend/app/services/collection_service.py` | 1 | rollback at `:413`；查询主要委托 Repository |
| Service | `backend/app/services/douban_service.py` | 1 | rollback at `:102` |
| API/dependency | `backend/app/api/deps.py` | 2 | `get_current_user():65-66`、`get_optional_user():110` |
| API | `backend/app/api/v1/collections.py` | 5 | router 级 rollback：`:142,182,243,291,337` |
| API | `backend/app/api/v1/auth.py` | 1 | router 级 rollback：`:89` |
| Agent state DB | `backend/app/agents/graph.py` | 独立通道 | `AsyncSqliteSaver` + `aiosqlite.connect()`：`:69-78` |

### 1.2 当前数据库职责

| 职责 | 当前 | 证据 |
|---|---|---|
| 纯 CRUD | YES | User/Subject/Collection/Schedule repositories |
| 状态存储 | YES | 收藏状态、观看排班、同步时间 |
| 缓存 | PARTIAL | `AnimeBroadcastMetadata` 明确作为 bangumi-data 缓存（`backend/app/models/broadcast_metadata.py:7-21`）；HTTP cache 实际为内存 |
| 配置 | NO | Pydantic Settings/env，`backend/app/core/config.py:5-52` |
| 任务状态 | NO | 业务库没有 AgentTask/Run 表 |
| 历史记录 | PARTIAL | Collection/Subject 有更新时间；Agent history 在独立 SQLite checkpoint，不在业务库 |
| 知识存储 | PARTIAL | Subject JSON 文档可查询，但不是关系化知识图谱或检索索引 |

**Current Database Role：** 用户、条目、收藏、排班和同步缓存的事务存储；Agent conversation checkpoint 另存 SQLite；Memory/Trace 主要在进程内。

**Future Agent Database Role：** 在保留业务表的基础上，增加 `agent_task`、`agent_run`、`agent_checkpoint_ref`、`memory_fact`、`agent_event`、`artifact` 与 `artifact_link` 等持久实体。LangGraph checkpoint 可以继续使用官方 saver，但必须与 task/run 建立稳定关联并支持 PostgreSQL 生产后端。

## Agent State Assessment

### 已存在

- 运行图状态：`CodingAgentState` 有 messages、reasoning、plan、completed_steps、terminal output（`backend/app/agents/graph.py:23-29`）。
- 通用 Harness 状态：`AgentState` 有 task、current_step、context、result、status（`backend/app/harness/state.py:10-25`）。
- 对话 checkpoint：`AsyncSqliteSaver`，按 owner-scoped thread ID 保存（`backend/app/agents/graph.py:69-78`、`backend/app/agents/thread_scope.py:38-66`）。
- 历史查询/删除/线程列表：`backend/app/api/v1/agent.py:208-365`。
- Resume API：`resume_chat()` 使用 `Command(resume=decision)`（`backend/app/api/v1/agent.py:289-338`）。

### 实际能力判断

- [x] Agent 运行状态保存：YES（LangGraph conversation checkpoint），但 Harness task state 未接主路径。
- [x] 任务恢复：PARTIAL。可以按 thread 恢复 LangGraph state；没有持久 task/run 记录、租约、owner worker 或恢复队列。
- [ ] 失败恢复：NO。Runtime 标记 failed，但主路径不保存 Harness checkpoint；没有 retry policy、attempt、next_retry_at。
- [x] 暂停/继续：PARTIAL/NOT OPERATIONAL。接口存在，但普通 `chat_endpoint()` 创建 `ChatWorkflow` 时未设置 `enable_interrupt=True`（`backend/app/api/v1/agent.py:143-144`），而中断点只在该标志为真时编译（`backend/app/agents/graph.py:104-107`）。当前主路径不能形成可恢复的审批暂停点。
- [x] 历史追踪：PARTIAL。消息/部分 reasoning 有 checkpoint；Trace 仅进程内且只记录任务级生命周期。

**Missing: Durable Agent State Store**

项目不是完全缺少 Agent State Store，而是缺少统一、生产级、可跨进程恢复的 Task/Run State Store。

## Memory Capability

| Memory 类型 | 结论 | 具体证据与限制 |
|---|---|---|
| Working | YES / PARTIAL | `CodingAgentState` 和 `AgentState.context` 存在；`plan`/`completed_steps` 字段存在，但当前 think/speak 图没有完整计划执行器 |
| Short | YES | LangGraph checkpoint 保存 messages；前端 `useChatStore` 也持久化 sessions/messages（`frontend/src/stores/useChatStore.ts:52-100,240`） |
| Long | YES / BROKEN IN MAIN PATH | `MemoryServiceImpl` 有事实提取与 hybrid retrieval（`backend/app/memory/service.py:58-190`），但 store 是进程内，且主链路方法名错配 |
| Episode | PARTIAL | checkpoint 可保留消息、工具结果和 reasoning；Trace 模型支持 steps/events（`backend/app/trace/__init__.py:20-67`），但 Runtime 未向 trace 添加 tool/node step |

```text
Memory Capability:

Working: YES (partial execution semantics)
Short: YES
Long: YES (currently non-durable and integration-broken)
Episode: PARTIAL
```

其他具体问题：

- `MemoryServiceImpl.store_fact()` 计算 `new_vec` 用于去重（`backend/app/memory/service.py:66-77`），但 `StoreMemoryRepository.put_fact()` 没有保存 embedding（`backend/app/memory/repository.py:37-52`）；后续 `get_facts()` 只能读取默认空 embedding（`:54-67`）。Vector retriever 因此可能每次重新嵌入或无法复用向量，取决于其实现路径。
- Memory namespace 绑定 thread，而非稳定 user profile；同一用户不同 thread 的长期偏好不能自然共享。
- `_memory_services` 以 `(api_key, base_url)` 为 key（`backend/app/api/v1/agent.py:47-61`），将 provider credential 组合与 Memory service 生命周期耦合；虽然事实 namespace 隔离 thread，但 service cache 仍是进程全局状态。

## Tool / Capability System

### 结构化程度

- [x] Metadata：`ActionDescriptor.name/description`。
- [x] 动态发现：`CapabilityRegistry.list_names()/list_actions()`（`backend/app/capabilities/registry.py:49-58`）；MCP `tools/list`（`backend/app/mcp_server/__init__.py:468-475`）。
- [x] 输入 Schema：`ActionDescriptor.input_schema`，且 MCP 对 schema 做校验（`backend/app/mcp_server/__init__.py:64-160`）。
- [x] 权限控制：`requires_auth`、`is_side_effect`、trusted `MCPContext`、side-effect policy 和 idempotency key。
- [ ] 输出 Schema：`CapabilityResult` 统一 success/error envelope，但每个 action 没有机器可发现的 `output_schema`。
- [ ] Tool/Action 版本化：MCP Server 有 `SERVER_INFO.version`（`backend/app/mcp_server/__init__.py:29`），但 capability/action 本身没有 `version`、deprecated/sunset 或兼容策略。

### 主要分裂

`CapabilityRegistry` 与 `ToolRegistry` 是两个注册系统：

- MCP 使用 `build_registry()` 注册 Anime、Recommendation、Schedule、Media（`backend/app/mcp_server/entry.py:27-34`）。
- ChatWorkflow 默认注册静态 `ALL_TOOLS`（`backend/app/agents/graph.py:56-58`、`backend/app/agents/tools.py:18-26`）。
- Anime/Profile/Search LangChain tools 已包装 Capability，这是好的过渡；但 schedule/media capability 没进入默认 Agent 工具集，MCP 动态 client 也只有显式 `register_mcp()` 后才生效（`backend/app/agents/registry.py:17-38`）。

**结论：** Tool 系统具备 Agent-native 基础，但下一步不是再造 Registry，而是收敛唯一描述符与装配入口，并为输出、版本和审计补齐契约。

## Event / Trace Assessment

### Current Observability

**Level: Medium-Low**

- [ ] 记录用户行为：仅普通请求日志/业务日志，没有统一 user event model。
- [x] 记录 Agent 行为：Runtime 记录 task_start/end/failure 的最终 Trace；SSE 暴露 thinking/message 生命周期。
- [x] 记录 Tool 调用：SSE 有 tool delta/start/end 与 duration；但这些没有写入 `AgentTrace.steps/events`。
- [x] 记录错误：日志、SSE error、Trace failed status。
- [ ] 可完整 debug 一次 Agent 运行：NO。Trace store 重启即失，且 `AgentRuntime.stream()` 没把每个 chunk/tool/node 写入 Trace；`AgentTrace.steps` 通常为空。

具体证据：

- Trace 模型设计支持 step/event（`backend/app/trace/__init__.py:20-67`）。
- Runtime 只创建 trace、mark completed/failed、record（`backend/app/harness/runtime.py:100-131`），没有 `add_step()` 调用。
- API 可按用户查询 Trace（`backend/app/api/v1/trace.py:31-59`），权限边界正确。
- `_trace_store` 是进程级全局、最多 500 条（`backend/app/api/v1/agent.py:41-42`），多 worker 不共享。
- `backend/app/core/logging.py:15-192` 有 request context filter，但 Agent task/run/trace ID 没贯穿所有日志。

## Knowledge Layer Assessment

当前知识表示是“业务文档数据”，不是知识图谱：

- `Subject` 覆盖 Anime 等多类型条目，tags/meta_tags/infobox/rating 使用 JSON（`backend/app/models/subject.py:15-58`）。
- `Collection` 通过 `(source, source_id)` 逻辑关联 Subject，并存用户评分/评论/标签（`backend/app/models/collection.py:15-37`）。
- Staff/Character 只存在 API schema 或即时工具结果，例如 `StaffInfo`、`character_name`（`backend/app/schemas/bangumi.py:4-25`），没有持久模型。
- 没有 `Character`、`Studio`、`Staff`、`Genre`、`Relation` 实体，也没有 `similar_to` 或边表。
- 可检索能力主要是 SQL/外部 Bangumi search；Memory hybrid retrieval 检索用户事实，不检索动漫知识库。

```text
Current:
Subject(JSON tags/infobox) <-logical source/source_id-> Collection

Recommended:
Anime/Subject -> SubjectTag -> Tag
Anime/Subject -> Credit(role) -> Person/Studio
Anime/Subject -> CharacterAppearance -> Character
Anime/Subject -> SubjectRelation(type) -> Anime/Subject
```

不建议第一阶段直接引入图数据库。先在 PostgreSQL 中将高价值关系正规化，并建立可增量更新的检索文档/embedding 索引；只有出现多跳关系查询和规模证据后再评估图数据库。

## Context Engineering Assessment

当前存在 Context 构建行为，但没有独立 `ContextBuilder`：

- 角色 Prompt 在 API 层拼接（`backend/app/api/v1/agent.py:119-125`）。
- 长短 Memory 在 `MemoryServiceImpl.retrieve_context()` 拼成字符串 summary（`backend/app/memory/service.py:92-153`）。
- ChatWorkflow 把 summary 插到消息头，并用 `trim_messages(max_tokens=8000, strategy="last")` 控制窗口（`backend/app/agents/graph.py:135-150,233-240`）。
- 递归步数 24、provider timeout 90 秒（`backend/app/agents/graph.py:20,211-247`）。
- 外部评论单条摘要截断 300 字（`backend/app/services/bangumi_service.py:643-648`）。

Checklist：

- [x] 自动选择相关信息：长期事实使用 BM25 + vector top-k；业务知识仍依赖模型主动调用工具。
- [x] 控制 token：有固定 8000 token trim；没有按模型窗口、预算、工具输出成本动态分配。
- [ ] 压缩历史：没有 LLM/规则滚动摘要；仅保留最后消息和截断。
- [x] 动态构建 prompt：Persona + Memory summary + conversation 动态组合，但逻辑分散在 API、Memory、Graph 三处。

**建议落点：** 抽出 `ContextBuilder.build(ContextRequest) -> ContextBundle`，让 `chat_endpoint()` 只传身份/目标，让 `ChatWorkflow` 只消费已预算的 context bundle。选择器、token budget、压缩策略和证据来源必须在 bundle 中可追踪。

## Task System Assessment

- [ ] 长任务：没有可靠后台任务执行器。
- [ ] 异步执行：HTTP/LangGraph 使用 async，但请求断开即失去业务级运行所有权；这不等于持久异步任务。
- [ ] 重试：MCP connection pool 有连接重试（`backend/app/agents/mcp/connection_pool.py:113-159`），Agent task 没有 retry/attempt/backoff。
- [x] 超时：LLM 90 秒、MCP transport 30 秒等局部 timeout；没有 task deadline/cancellation policy。
- [ ] 状态恢复：LangGraph thread 可恢复，Task Runtime 不可恢复。

`backend/app/worker/celery_app.py:1` 只有 TODO；Docker Compose 也没有 worker/scheduler 服务。`AgentTask` 是请求内 DTO，不是持久任务实体。

## File and Resource / Artifact Assessment

应进入 Artifact Layer 的对象包括：导入的豆瓣文件、导出的 Calendar/CSV、封面图片缓存、torrent、下载任务与最终媒体文件。

当前：

- `Subject.images/image` 只存远端 URL/JSON（`backend/app/models/subject.py:33-35`）。
- qBittorrent/RSS 状态由外部服务持有，`QBService` 直接调用同步 SDK（`backend/app/services/qb_service.py:11-237`）。
- Docker 将下载目录映射到 `data/qbittorrent_downloads`（`docker-compose.yml:89-109`）。
- 前端 `downloadCSV()` 直接触发浏览器下载（`frontend/src/services/CalendarService.ts:265`）。
- 未发现 Artifact/File 模型、checksum、MIME、owner、retention、task/run link 或生成来源。

Checklist：

- [ ] 文件 metadata
- [ ] 文件生命周期
- [ ] Agent 产生文件记录
- [ ] 文件关联 task

**结论：Missing: Artifact Layer。**

## API Design Assessment

当前已有 `/api/v1/chat*`、`/api/v1/trace*`，而不是纯 CRUD：

- Agent：`POST /api/v1/chat`、history、reasoning、resume、threads（`backend/app/api/v1/agent.py:104-368`）。
- Trace：`GET /api/v1/trace`（`backend/app/api/v1/trace.py:31-59`）。
- 业务：subjects、collections、schedules、RSS、users、dashboard、Bangumi。

建议不要机械增加所有名词路由，而按一等资源补齐：

| 建议资源 | 是否需要 | 原因 |
|---|---|---|
| `/agent` | 可选 | 现有 `/chat` 可保留兼容；新 API 更适合 `/agent/tasks` 或 `/agent/runs` |
| `/task` | YES | 创建、查询、取消、重试、恢复长任务 |
| `/event` | YES | 按 run cursor/SSE 重放持久事件，而非只依赖活连接 |
| `/artifact` | YES | 上传、生成、下载、关联 task/run |
| `/capability` | YES（至少内部/管理） | 可发现能力、Schema、版本、权限 |
| `/memory` | 谨慎 | 仅提供用户可审计/删除的 memory facts；不要暴露底层 store |

所有新资源应以 `task_id/run_id` 作为关联键，并继续使用 owner-scoped authorization。

## Strong Coupling Findings

### 1. Agent HTTP 端点承担 Composition Root 与业务编排

**File:** `backend/app/api/v1/agent.py`
**Class/Function:** `_get_or_create_memory()`、`chat_endpoint()`
**Problem:** Router 同时处理 provider policy、Prompt 拼接、thread ownership、Workflow/Adapter/Runtime/Memory/Trace 构造、SSE 序列化和事实抽取；模块级 store 又让初始化顺序与 worker 生命周期耦合。
**Severity:** HIGH
**Recommendation:** 将 `chat_endpoint()` 的 `backend/app/api/v1/agent.py:132-199` 下沉到明确的 `AgentApplicationService.start_run()`；API 仅负责验证请求和流式传输 `RunEvent`。

### 2. 新旧 Memory 契约断裂

**File:** `backend/app/api/v1/agent.py:47-58,152-154`、`backend/app/agents/graph.py:234-240`、`backend/app/memory/service.py:92`
**Class/Function:** `MemoryServiceImpl`、`ChatWorkflow.stream_chat()`
**Problem:** 注入对象的接口与调用方不一致，登录用户主链路会在上下文加载处失败。
**Severity:** CRITICAL
**Recommendation:** 让 `ChatWorkflow` 类型依赖 `MemoryService` 并只调用接口定义的 `retrieve_context()`；增加真实 `ChatWorkflow + MemoryServiceImpl` 集成测试，不能再以 `FakeWorkflow` 代替该边界。

### 3. Agent 状态分裂在四种存储生命周期

**File:** `backend/app/agents/graph.py:45-74`、`backend/app/api/v1/agent.py:40-43`、`frontend/src/stores/useChatStore.ts:80-100,240`
**Problem:** checkpoint 在 SQLite、facts/trace 在进程内、UI history 在 localStorage；没有 task/run 真相源。
**Severity:** HIGH
**Recommendation:** 建立 Task/Run 聚合与持久 repository；各 store 都通过 run ID 关联，前端本地状态只作为 cache。

### 4. ChatWorkflow 职责过载

**File:** `backend/app/agents/graph.py`
**Class/Function:** `ChatWorkflow._ensure_checkpointer()`、`_trim_and_clean()`、`stream_chat()`
**Problem:** 同一类负责数据库连接、工具发现、模型 provider 配置、Context 裁剪、图执行和底层事件转译。`stream_chat()` 超过 290 行，隐藏状态 `_speak_prompt` 还在 workflow instance 上变更。
**Severity:** HIGH
**Recommendation:** 分离 WorkflowFactory、ContextBuilder、ModelFactory、EventMapper 和 CheckpointProvider；Graph node 只保留确定性状态转换。

### 5. Service/Repository 边界不一致

**File:** `backend/app/services/bangumi_service.py:233-247`、`backend/app/services/bangumi_data_sync.py:188-218`、`backend/app/services/stats_service.py:46-59`
**Problem:** Service 直接 select/add/commit，导致事务边界散落，未来 Agent capability 复用这些 Service 时难以统一幂等、重试和 unit of work。
**Severity:** MEDIUM-HIGH
**Recommendation:** 将查询/写入移入针对用例的 Repository 方法；commit 由 application-level unit of work 统一控制，而不是每个 Repository 方法自行提交。

### 6. 外部数据转换逻辑隐藏在 Schema 模块

**File:** `backend/app/schemas/adaptersV2.py:102-914`
**Function:** `bangumi_subject_to_subjectlist()`、`bangumi_collection_to_*()`、`douban_to_*()`、calendar adapters
**Problem:** Schema 文件承载数百行业务映射、默认值、标签提取和多数据源兼容逻辑；它既不是纯 DTO，也不是明确 Anti-Corruption Layer。
**Severity:** MEDIUM
**Recommendation:** 按数据源拆成 Bangumi/Douban mapper，并把归一化规则放入 source adapter；Schema 只保留验证契约。

### 7. qBittorrent 同步 SDK 阻塞 async API

**File:** `backend/app/services/qb_service.py:17-43,75-237`、`backend/app/api/v1/rss.py:18-98`
**Class:** `QBService`
**Problem:** `qbittorrentapi.Client` 是同步调用，FastAPI endpoint 直接调用它；连接、RSS 查询和 mutation 会阻塞 event loop。并且 upsert 隐式“删除后重建”（`:115-144`），没有 task/event/artifact 记录。
**Severity:** MEDIUM-HIGH
**Recommendation:** 通过 worker/thread adapter 执行阻塞调用，将 download/RSS mutation 建模为可追踪 task，并记录外部 resource ID。

### 8. Redis 配置与实际缓存实现不一致

**File:** `backend/app/main.py:46-74`
**Function:** `lifespan()`
**Problem:** 云模式会连接并 ping Redis，但成功后仍初始化 `InMemoryBackend`，注释也说明“暂时使用内存缓存”。多 worker cache 不一致，Redis 只成为健康检查依赖。
**Severity:** MEDIUM
**Recommendation:** 明确选择真正 Redis backend，或移除伪 Redis 依赖；Agent run/memory 不应误用 HTTP response cache。

## Migration Risk Assessment

### 可以直接保留

- SQLModel 业务模型与现有 Alembic 迁移，尤其 User/Subject/Collection/Schedule 的唯一约束。
- FastAPI router 的鉴权边界和 owner-scoped thread ID：`backend/app/agents/thread_scope.py`。
- `BaseCapability`、`ActionDescriptor`、`CapabilityResult`、`CapabilityRegistry` 的基本方向。
- MCP exposure allowlist、trusted context、side-effect/idempotency policy。
- `AgentTask`、`AgentState`、`AgentRuntime`、Trace 模型的契约形态。
- SSE event taxonomy 与前端过程节点 UI。
- Bangumi/豆瓣/qBittorrent 客户端与现有业务算法，作为 adapter 保留。

### 需要抽象

- `chat_endpoint()` 的 application orchestration。
- `ChatWorkflow` 的 Context、Model、Tool、Checkpoint、Event mapping 职责。
- Repository/UoW 事务边界，覆盖 Service 直接 DB 的路径。
- Capability 与 LangChain Tool 的统一描述符/adapter。
- Memory/Trace/Checkpoint 的持久存储接口和 run 关联。
- `adaptersV2.py` 的外部数据 Anti-Corruption Layer。
- qBittorrent 的阻塞 adapter 与任务化执行。

### 需要重写或新增

- 生产级 `TaskRepository` / `RunRepository` 与 worker claim/retry/cancel 状态机。
- DB-backed Trace/Event Store，并让 Tool/Node/LLM 事件真正落库。
- Artifact metadata/lifecycle/link layer。
- `Character`/`Person`/`Studio`/Relation 等正规化知识模型（按需求增量建设）。
- Celery/其他队列执行器；当前 `backend/app/worker/celery_app.py:1` 无可保留实现。

## Agent Readiness Score

| 维度 | 分数 | 判断 |
|---|---:|---|
| Database | 6/10 | ORM、Repository、迁移和双数据库模式存在；越层访问与事务分散 |
| Agent State | 5/10 | LangGraph checkpoint/history 存在；无统一持久 Task/Run，暂停恢复未接通 |
| Memory | 4/10 | 分层接口、抽取和 hybrid retrieval 存在；主链路接口错配且长期 store 非持久 |
| Tool System | 7/10 | Descriptor、Schema、discovery、auth、MCP policy 较完整；缺输出 Schema/action version 和唯一注册源 |
| Event System | 4/10 | SSE 与 Trace 模型存在；Trace 只记录生命周期且进程内 |
| Knowledge Layer | 3/10 | 有丰富 Subject 文档，但没有关系实体和知识检索层 |
| Context Engineering | 5/10 | 有 memory retrieval、trim 和动态 Prompt；没有独立 builder、压缩与预算策略 |
| Task System | 2/10 | DTO/Runtime 骨架存在；无队列、重试、持久任务、worker |
| Artifact Layer | 1/10 | 有文件/下载行为，无 Artifact 模型和生命周期 |
| API | 5/10 | 已有 chat/history/resume/trace；缺 Task/Event/Artifact/Capability 一等资源 |

**Overall Agent Readiness: 4.2/10**

这个分数表示“可以在现有代码上演进”，但不适合直接把长任务、并发 worker 或重要自动化副作用交给 Agent 运行时。

## Critical Problems

1. `MemoryServiceImpl` 与 `ChatWorkflow` 的真实装配接口不兼容，且测试未覆盖该边界。
2. Agent Task/Run 没有持久真相源；Memory、Trace、checkpoint、前端 history 生命周期分裂。
3. 暂停/继续 API 存在，但普通聊天运行未编译 interrupt point，无法形成可靠审批恢复流程。
4. Trace 不记录实际 node/tool event，不能复盘一次 Agent run；进程重启即丢失。
5. Capability/MCP 与 Chat Tool 装配仍是双 Registry，权限与版本契约尚未统一到所有调用入口。
6. Service 直接数据库和 Repository 内部 commit 使 Agent 重试/幂等/事务控制难以统一。
7. 没有后台任务执行器和 Artifact Layer，下载、导入、导出无法被 Agent 作为可恢复产物管理。

## Recommended Refactor Order

### Phase 0: Repair the Existing Agent Path

- 统一 `MemoryService` 调用契约，并增加真实装配集成测试。
- 为 chat run 分配稳定 `task_id/run_id`，贯穿 SSE、日志、Trace、checkpoint 和 Memory。
- 明确 interrupt 的启用规则，验证 pause → process restart → resume。

**Exit criteria:** 登录用户真实 chat + memory 流程通过；一次 run 能以 run ID 查询状态和错误。

### Phase 1: Database and State Abstraction

- 新增 Task/Run/Event/MemoryFact 的 repository 与迁移。
- 把 Harness `CheckpointStore` 接入主路径；生产使用 PostgreSQL/官方持久 saver。
- 收敛 Service 直接数据库访问和 transaction/UoW 边界。

**Exit criteria:** 服务重启后可恢复 pending/paused run；多 worker 看到一致状态。

### Phase 2: Capability Registry Convergence

- 以 `ActionDescriptor` 为唯一能力定义；LangChain/MCP/OpenAI function 均由 adapter 生成。
- 增加 `output_schema`、action version、deprecation、permission scopes、cost/timeout/idempotency metadata。
- 让默认 Agent 和 MCP 使用同一 exposure/policy 决策层。

**Exit criteria:** 任一 capability 只注册一次；所有入口发现到同一 Schema 和权限策略。

### Phase 3: Memory and Context Layer

- 持久化 user-scoped facts，区分 user/profile、thread、run 三种 namespace。
- 建立独立 ContextBuilder，执行相关性选择、token budget、tool output 压缩、来源标注。
- 将 Memory 提取变为 run 完成后的异步任务，失败可重试且不阻断主回答。

**Exit criteria:** Context bundle 可测试、可解释、可重放；Memory 不依赖进程或 provider credential cache。

### Phase 4: Agent Runtime, Events and Workers

- 实现 task state machine：pending/running/paused/succeeded/failed/cancelled，带 attempt、lease、deadline。
- worker 从持久队列 claim；每个 node/tool/LLM 事件写 Event Store。
- SSE 从 Event Store 按 cursor 推送，支持断线重连和 replay。

**Exit criteria:** 长任务在请求断开、worker crash 后可恢复；一次运行可完整 debug。

### Phase 5: Artifact and Knowledge Layer

- 建立 Artifact metadata、owner、checksum、MIME、storage URI、retention、task/run link。
- 将导入、导出、torrent、下载结果纳入 Artifact/Task。
- 按实际推荐和关系查询需求逐步正规化 Character/Staff/Studio/Relation，并建立检索索引。

**Exit criteria:** Agent 产生或消费的文件可追踪、可授权、可清理；知识检索返回可引用证据。

## Migration Plan

### 数据模型建议

建议先增加，不迁移现有业务表：

- `agent_task(id, user_id, goal, status, priority, created_at, deadline_at)`
- `agent_run(id, task_id, attempt, status, worker_id, started_at, ended_at, error_code, error_detail)`
- `agent_event(id, run_id, seq, event_type, payload_json, created_at)`，唯一约束 `(run_id, seq)`
- `agent_checkpoint(run_id, thread_id, saver_ref, updated_at)`，只存引用或必要 metadata
- `memory_fact(id, user_id, scope_type, scope_id, content, importance, embedding_ref, source_run_id, created_at)`
- `artifact(id, user_id, storage_uri, mime_type, size, checksum, status, created_by_run_id, expires_at)`
- `artifact_link(artifact_id, entity_type, entity_id, relation)`

### 兼容迁移策略

1. 保留现有 `/api/v1/chat`，内部改为创建 Task/Run，再流式代理 run events。
2. 先双写 Trace/Event，验证一致后再用持久 Event Store 驱动查询与 SSE replay。
3. 先让 `StoreMemoryRepository` 增加 PostgreSQL 实现；旧 `InMemoryStore` 只用于测试。
4. 通过 adapter 让现有 `@tool` 继续工作，同时逐个切换为 Descriptor 生成；不要一次删除 `ALL_TOOLS`。
5. qBittorrent/导入/导出先任务化，再加入 Artifact；业务 CRUD 不需要等待 Agent Runtime 重构完成。
6. 知识模型按查询价值逐表迁移，不对 `Subject.infobox/tags` 做一次性破坏性拆分；先双写正规化关系。

### 风险与控制

| 风险 | 触发点 | 控制 |
|---|---|---|
| 重复副作用 | worker retry、MCP write action | action idempotency key + DB unique constraint + outbox/event record |
| 状态双写不一致 | checkpoint、run、event 分库 | run ID、事务内 event append、对账任务 |
| Memory 泄漏 | thread ID/namespace 错误 | 延续 `make_user_thread()` owner scope，Memory 强制 user scope |
| SSE 重复/乱序 | reconnect/replay | `(run_id, seq)` 唯一序号，前端按 cursor 去重 |
| 工具权限旁路 | LangChain 与 MCP 双入口 | 同一 PolicyEngine 在 adapter 前执行 |
| 迁移停机 | 新表/索引 | additive migration、双写、后台回填、可回滚 feature flag |
| 外部 API 阻塞 | qBittorrent 同步 SDK | thread/worker adapter + timeout + circuit breaker |

## Final Decision

**是否具备演进为 Agent-native Backend 的基础：YES，但仅达到“可演进骨架”，尚未达到“生产级 Agent Runtime”。**

最值得保留的是 Capability/MCP 契约、LangGraph checkpoint、Harness/Trace 模型和现有业务分层；最先要解决的不是引入更多框架，而是修复 Memory 主链路、建立持久 Task/Run/Event 真相源、统一能力注册与权限入口。完成 Phase 0-2 后，项目才适合继续投入 Long Memory、worker 和 Artifact 自动化。
