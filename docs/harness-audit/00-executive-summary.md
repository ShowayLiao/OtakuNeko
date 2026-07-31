# OtakuNeko AI Agent Harness 审计摘要

## 结论

本审计以当前源码为准，权威对照文档实际位于 [`docs/standard-agent-harness-reference-and-codex-audit-guide.md`](../standard-agent-harness-reference-and-codex-audit-guide.md)，而不是提示中给出的 `docs/architecture/standard-agent-harness-reference.md`；参考文档的 §20 明确要求本目录的 12 个文件（参考文档:1695-1713）。

当前成熟度判定为 **Level 1.5：Agent Loop 已存在，Controlled Runtime 只有局部能力，未达到可靠 Level 2，也未达到 Durable Harness Level 3**。判定依据是：LangGraph 已经执行 `think -> tools -> think -> speak`，并设置 `recursion_limit=24`（`backend/app/agents/graph.py:20,90-108,242-247`）；但聊天主路径没有统一 Run Coordinator、统一 Invocation、持久化 Run/Step/Event、断线补拉、取消状态落库或全局预算（`backend/app/api/v1/agent.py:176-219`; `backend/app/harness/runtime.py:181-336`）。参考文档把这些分别列为 Level 1、2、3 的判据（参考文档:1576-1599）。

安全上有一个应立即阻断的 **P0**：qBittorrent RSS 读写路由只依赖配置开关，没有 `get_current_user`，而服务会使用服务器配置的 qBittorrent 凭据执行操作（`backend/app/api/v1/rss.py:16-105`; `backend/app/api/deps.py:76-90`; `backend/app/services/qb_service.py:24-43,95-217`）。本轮识别 **11 个 P1 Gap**，详见 [`07-gap-analysis.md`](07-gap-analysis.md)。P0/P1 数量是按本目录 Gap ID 统计，不把“未确认”问题计入已确认 Gap。

## 最高风险 5 项

1. **G-P0-01 未认证的 qBittorrent 外部副作用**：`/rss/add`、`/upsert`、`/remove`、`/set-rule`、`/remove-rule` 暴露修改能力；当前证据足以判定为未授权外部副作用风险（`backend/app/api/v1/rss.py:28-93`）。
2. **G-P1-03 SSE/服务重启后的 Run 状态不可恢复**：聊天请求创建 `AgentRuntime`，但没有传入 `checkpoint_store`，而图 checkpoint 是单独的本地 SQLite 文件；Docker 后端未挂载 `data/`（`backend/app/api/v1/agent.py:176-219`; `backend/app/harness/runtime.py:57-70`; `backend/app/agents/graph.py:44-78`; `docker-compose.yml:73-125`）。
3. **G-P1-01 Agent Loop 所有权分裂**：`AgentRuntime` 包装流并可做一次结果合成，`FeatureFlagRoutingAdapter` 负责路由，`ChatWorkflow` 才真正控制模型/工具循环；不存在统一的 Decision/Invocation 边界（`backend/app/harness/runtime.py:181-305`; `backend/app/harness/routing_adapter.py:19-66`; `backend/app/agents/graph.py:90-108,195-298`）。
4. **G-P1-02 Tool Registry、Schema、权限和结果归一化未统一**：主聊天使用静态 `ALL_TOOLS` 和 `ToolRegistry`，Capability/MCP 各有另一套注册/暴露协议；主聊天工具结果直接把原始内容送到 SSE（`backend/app/agents/graph.py:44-64,384-468`; `backend/app/agents/registry.py:1-55`; `backend/app/capabilities/registry.py:1-65`; `backend/app/mcp_server/__init__.py:296-353`）。
5. **G-P1-04 写操作缺少跨边界幂等/补偿**：qBittorrent `upsert` 是“删除后重新添加”，中途失败没有补偿；HTTP RSS 路由没有幂等键；日程 Capability 只计算哈希而不读取/写入幂等存储（`backend/app/services/qb_service.py:115-151`; `backend/app/api/v1/rss.py:28-93`; `backend/app/capabilities/schedule.py:78-149`）。

## 最值得保留的设计

- `ThreadScope` 和认证依赖用于聊天历史、收藏、日程、Memory、Trace 的用户范围控制；例如聊天线程由 `make_user_thread(user.id, public_id)` 生成（`backend/app/api/v1/agent.py:55-73`），收藏和日程路由把资源查询绑定到 `current_user.id`（`backend/app/api/v1/collections.py:24-32,84-110,181-209`; `backend/app/api/v1/endpoints/schedules.py:30-260`）。
- `CapabilityRegistry` 的 `ActionDescriptor` 已表达 `requires_auth`、`is_side_effect` 和输入 Schema，MCP 服务进一步做到暴露白名单、可信上下文注入、写操作策略和幂等缓存（`backend/app/capabilities/types.py:10-53`; `backend/app/mcp_server/__init__.py:296-353`; `backend/app/mcp_server/policy.py:1-40`）。这是一条可复用的边界，但当前尚未成为聊天主路径的唯一注册入口。
- SQL Memory Repository、SQL Trace Store、租约式 Proactive scheduler 已有用户范围、提交/回滚、重试分类或 lease 语义（`backend/app/memory/sql_repository.py:1-260`; `backend/app/trace/sql_store.py:1-220`; `backend/app/harness/scheduler/repository.py:162-319`; `backend/app/harness/scheduler/execution.py:83-124`）。它们可作为未来持久化 Harness 的材料。
- Trace redaction 对 secret、私有 Prompt 和 Chain-of-Thought 设置了字段级规则，且有专门测试（`backend/app/trace/redaction.py:1-180`; `backend/tests/trace/test_event_contract.py:52-130`）。

## 推荐目标

先达到可靠 **Level 2**，再演进到 Level 3；不是要求采用某个特定框架。第一阶段目标应是：唯一 Run Coordinator、统一 Decision/Invocation/Result、统一 Registry/Policy、Run 级预算和取消、qBittorrent 认证封堵、真实主路径契约测试。第二阶段再补 Run/Step/Event 持久化、断线补拉、人审和写操作幂等（参考文档:2211-2244）。

## 推荐重构批次

1. **BATCH-01：安全封堵与副作用边界**：先保护 qBittorrent 路由，并为所有写能力建立可信主体、风险和幂等入口；不改变聊天回答协议。
2. **BATCH-02：Run/Invocation/事件协议**：让现有 `AgentRuntime`、LangGraph adapter 和 SSE 使用同一个 Run ID、Invocation ID、状态机、预算和取消信号。
3. **BATCH-03：统一 Capability/Tool Registry**：把静态工具、Capability Registry、MCP Exposure 映射到一套可审计契约，保留现有业务 Service 和 LangGraph 作为实现适配层。

具体允许/禁止范围、验收测试和回滚方式见 [`09-migration-plan.md`](09-migration-plan.md) 与 [`11-task-backlog.md`](11-task-backlog.md)。

## 不建议立刻修改的区域

- 不要先重写 LangGraph 图或替换模型框架；当前最大问题是控制面和安全边界，不是图 API 选择（`backend/app/agents/graph.py:90-108`）。
- 不要先迁移全部业务 Service、收藏模型或日程模型；它们已有可复用的资源级用户约束，先通过 adapter 接入统一 Invocation。
- 不要把前端本地会话存储当作服务端 Run Store；前端 `chat-storage` 只持久化 UI 消息和配置（`frontend/src/stores/useChatStore.ts:80-86,239-246`）。

## 尚未确认的关键问题

- 部署环境是否在容器外另行挂载 `data/checkpoints.db`，以及实际发布是否运行 Alembic；仓库 compose 和 Dockerfile 没有提供该证据（`docker-compose.yml:73-125`; `backend/Dockerfile:6-20`; `backend/alembic/env.py:56-88`）。
- `X-Provider-Endpoint` 的域名解析后是否由网络层阻止私网、回环和云元数据地址；代码只检查字面 IP/主机名（`backend/app/agents/provider_endpoint.py:17-53`）。需要在实际网络策略和 DNS 路径验证。
- 前端/反向代理断开时，FastAPI generator 的取消是否一定传播到 provider、ToolNode 和 qBittorrent 等下游；当前没有端到端断线测试，只有局部 runtime 取消测试（`frontend/src/lib/fetcher.ts:154-170,277-290`; `backend/tests/trace/test_agent_instrumentation.py:196-218`）。
