# 当前架构：源码事实模型

## 审计边界与入口

后端由 FastAPI 组装，`app.main:app` 在生命周期中初始化业务数据库、可选 Proactive scheduler 和缓存；所有 `/v1` 路由在 `backend/app/api/v1/__init__.py:5-18` 汇总。聊天入口是 `POST /api/v1/chat`，收藏、日程、RSS、Trace、Memory、Proactive 是并列 HTTP 边界（`backend/app/api/v1/__init__.py:7-18`; `backend/app/api/v1/agent.py:90-249`）。

浏览器先请求 Next.js route；该 route 只转发 `authorization`、`content-type`、`x-api-key`、`x-provider-endpoint`，并把请求体流转给后端（`frontend/src/app/api/v1/chat/route.ts:9-35`）。前端会话、消息、模型配置和正在显示的 Tool/Thought 节点主要在 Zustand `chat-storage` 中（`frontend/src/stores/useChatStore.ts:64-86,80-247`）。

## C4 Context

```text
用户浏览器
  ├─ Next.js Chat Route ──HTTP/SSE──> FastAPI Agent API
  ├─ REST ───────────────> FastAPI 业务 API
  └─ localStorage/Zustand 保存 token、会话消息和 BYOK 配置

FastAPI Agent API
  ├─ LLM Provider：OpenAI-compatible / DeepSeek / Ollama 检查路径
  ├─ Bangumi / 业务 Service：动漫、收藏、日程、推荐
  ├─ qBittorrent：RSS/自动下载规则
  ├─ SQLite/PostgreSQL：业务表、Memory、Trace
  ├─ LangGraph SQLite checkpoint：图状态
  └─ Redis 配置存在，但缓存实现实际使用 InMemoryBackend
```

证据：LLM provider 和 BYOK 由 `agent.py` 解析（`backend/app/api/v1/agent.py:76-112,412-435`）；缓存分支虽然连接 Redis，但初始化的仍是 `InMemoryBackend`（`backend/app/main.py:75-119`）；业务数据库通过 `DATABASE_URL` 切换 SQLite/PostgreSQL（`backend/app/core/config.py:39-49`; `backend/app/db/database.py:7-48`）。

## Container / Component 映射

| 当前模块 | 源码职责 | 参考 Harness 组件映射 | 边界判断 |
|---|---|---|---|
| `api/v1/agent.py` | HTTP 入参、BYOK、线程归属、SSE 包装、请求后 Memory | API/stream routes、Run ingress | 现在同时组装 Runtime、Graph、Memory、Trace，入口过重（`backend/app/api/v1/agent.py:90-249`）。 |
| `harness/runtime.py` | `AgentTask`/`AgentState` 初始化、adapter 流包装、可选 trace/checkpoint、结果合成 | Runtime/coordinator/lifecycle | 只在传入 store 时持久化；主聊天没有传入 `checkpoint_store`（`backend/app/harness/runtime.py:57-70,181-336`; `backend/app/api/v1/agent.py:176-219`）。 |
| `agents/graph.py` | LangGraph 状态图、模型调用、ToolNode、speak、图 checkpoint | Loop adapter、checkpoint adapter、model/context boundary | 实际 Agent Loop 所有者是它，不是 `AgentRuntime`（`backend/app/agents/graph.py:90-108,195-298`）。 |
| `harness/routing_adapter.py` | Feature flag、路由、specialist 结果转发 | Decision/delegation adapter | 与 Graph Loop 叠加，形成两层控制面（`backend/app/harness/routing_adapter.py:19-66`）。 |
| `agents/registry.py` + `agents/tools.py` | LangChain Tool 注册和静态 7 工具 | Tool Registry / adapters | 主聊天每次请求注册静态工具；没有使用 Capability Registry（`backend/app/api/v1/agent.py:161-175`; `backend/app/agents/tools.py:8-26`）。 |
| `capabilities/*` | ActionDescriptor、用户范围业务动作、Service 调用 | capabilities/definitions/dispatcher | 契约更结构化，但与主聊天 Tool Registry 分叉（`backend/app/capabilities/types.py:10-53`; `backend/app/capabilities/registry.py:1-65`）。 |
| `mcp_server/*` | Exposure、schema、可信 Context、side-effect/idempotency policy | capability gateway / external tool boundary | 安全边界较完整，但 `entry.py` 暴露集目前与聊天主路径断开（`backend/app/mcp_server/entry.py:38-64`; `backend/app/mcp_server/__init__.py:296-353`）。 |
| `memory/*` | checkpoint 上下文、SQL facts、LLM fact extraction | context selector / memory store | SQL 实现进入聊天；`MemoryManager`/LangGraph Store 是重复路径（`backend/app/api/v1/agent.py:137-150`; `backend/app/memory/manager.py:1-220`）。 |
| `trace/*` | trace span、redaction、SQL/InMemory store、查询 API | observability/tracing/audit | 主聊天 trace 结束后才写 SQL，SSE 中间事件不是独立 Event Store（`backend/app/api/v1/agent.py:176-219`; `backend/app/trace/sql_store.py:1-220`）。 |
| `harness/scheduler/*` | 定时任务、lease、重试、task run | durable task scheduler | Proactive 有独立持久化和租约，但与交互聊天 Run 不是同一生命周期（`backend/app/main.py:45-73`; `backend/app/harness/scheduler/repository.py:238-319`）。 |
| `services/*` | Domain/integration：Bangumi、收藏、日程、qBittorrent | Harness 外部 Domain/Integration | 业务服务不应依赖具体 LLM 框架；当前部分工具直接持有全局 Capability（`backend/app/agents/tools/search.py:1-114`; `backend/app/services/qb_service.py:11-217`）。 |

## 依赖方向

```text
Frontend / REST
      ↓
API route ──→ AgentRuntime ──→ FeatureFlagRoutingAdapter ──→ AgentRouter/Specialist
      │                                      └──────────────→ LangGraphAdapter
      │                                                              ↓
      └────────→ ChatWorkflow ──→ ChatOpenAI/DeepSeek + ToolNode ──→ static tools
                                                                          ↓
                                                               Capability/Service/External API

Memory/Trace/DB are injected by the API, while graph owns its own checkpoint connection.
```

聊天 API 同时构造 `ChatWorkflow`、`LangGraphAdapter`、`AgentRegistry`、Router、Runtime、Memory 和 Trace Store（`backend/app/api/v1/agent.py:130-219`）。这说明当前依赖方向能运行，但 Composition Root 没有把 Runtime 的持久化、预算、取消和政策作为单一入口。

## 外部系统与数据存储

| 系统 | 当前连接点 | 持久性/异步边界 |
|---|---|---|
| OpenAI-compatible/DeepSeek | `ChatOpenAI`、`DeepSeekChatOpenAI`、`AsyncOpenAI` | provider timeout 90s 只在部分 adapter/gateway 设置（`backend/app/agents/graph.py:195-231`; `backend/app/harness/model_gateway.py:32-73`）。 |
| qBittorrent | 同步 `qbittorrentapi.Client`，每次 `QBService` 初始化登录 | FastAPI 同步路由；无 Agent Run 关联、审计或幂等（`backend/app/api/v1/rss.py:16-105`; `backend/app/services/qb_service.py:24-43`）。 |
| PostgreSQL/SQLite | SQLModel async engine；启动时 `create_all` | 与 Alembic 并存；图 checkpoint 固定 SQLite（`backend/app/db/database.py:7-48`; `backend/app/agents/graph.py:44-78`）。 |
| Redis | `Redis.from_url().ping()` | 只用于启动探测，缓存仍是进程内，重启丢失（`backend/app/main.py:91-119`）。 |
| LangGraph checkpoint | `data/checkpoints.db` / `AsyncSqliteSaver` | 进程内 graph connection；Docker backend 无该目录卷挂载（`backend/app/agents/graph.py:69-78`; `docker-compose.yml:73-125`）。 |

## 关键边界结论

- **Loop owner**：当前是 `ChatWorkflow._compile_graph` 和 `stream_chat`，因为它定义节点、条件边、ToolNode、模型绑定和 recursion limit（`backend/app/agents/graph.py:90-108,195-298`）。
- **Runtime owner**：当前只拥有外层状态/trace/结果合成，不拥有每一步的模型决策或 Tool invocation（`backend/app/harness/runtime.py:181-305`）。
- **业务副作用 owner**：RSS、收藏、日程由各自 API/Service 直接控制；MCP 的 policy 只保护 MCP 调用路径，不能保护 `/v1/rss`（`backend/app/mcp_server/__init__.py:296-353`; `backend/app/api/v1/rss.py:16-105`）。
- **Session owner**：前端 UI session ID、后端 thread scope、LangGraph checkpoint thread_id 是三个相关但不同的概念；没有独立的持久化 Run/Session 映射表（`frontend/src/stores/useChatStore.ts:52-62`; `backend/app/api/v1/agent.py:55-73,193-209`; `backend/app/agents/graph.py:242-247`）。
