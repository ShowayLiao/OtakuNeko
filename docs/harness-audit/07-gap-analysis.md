# Gap 分析与 0–4 评分

评分采用参考文档 §20.5：0 不存在，1 零散/隐式，2 基本可用但无统一边界，3 结构完整仍有生产缺口，4 满足主要 MUST/SHOULD（参考文档:1773-1801）。

## 维度评分

| 维度 | 分数 | 证据摘要 |
|---|---:|---|
| Runtime Ownership | 1 | Runtime、routing adapter、LangGraph 分层存在，但 Graph 才拥有 Loop（`backend/app/harness/runtime.py:181-305`; `backend/app/agents/graph.py:90-108`）。 |
| Structured Contracts | 2 | `AgentTask/State/Result` 和 CapabilityResult 存在；主 Tool 输出仍是 raw dict（`backend/app/harness/result.py:1-130`; `backend/app/agents/graph.py:445-463`）。 |
| Capability Management | 2 | Capability Registry/MCP Exposure 存在，静态 Tool Registry 与之分叉（`backend/app/capabilities/registry.py:1-65`; `backend/app/agents/registry.py:1-55`）。 |
| Policy & Authorization | 1 | Proactive/MCP 有 policy；主聊天 Tool 与 RSS REST 没有统一执行前 policy（`backend/app/harness/policy.py:1-100`; `backend/app/api/v1/rss.py:16-105`）。 |
| Persistence & Recovery | 1 | Graph checkpoint 和 scheduler SQL 存在；交互 Run/Event/断线恢复不存在（`backend/app/agents/graph.py:69-78`; `backend/app/harness/scheduler/repository.py:238-319`）。 |
| Error Handling | 1 | 多处返回 raw error；Graph 捕获异常为 error chunk，错误语义未统一（`backend/app/agents/tools/base.py:20-58`; `backend/app/agents/graph.py:470-477`）。 |
| Cancellation | 1 | 前端 abort、Runtime 捕获取消，但主聊天没有可查取消状态（`frontend/src/hooks/useChatStreaming.ts:285-323`; `backend/app/harness/runtime.py:321-336`）。 |
| Streaming | 2 | SSE 事件和 sequence 存在，但没有 durable event/reconnect（`backend/app/api/v1/agent.py:220-231`; `frontend/src/lib/fetcher.ts:147-177`）。 |
| Context Management | 2 | trim 8000 token、Memory context 存在；预算/信任标签/配置快照缺失（`backend/app/agents/graph.py:135-150,233-247`）。 |
| Memory | 2 | SQL Memory 有 owner/retention；旧 Store Memory 重复且提取可污染长期事实（`backend/app/memory/service.py:68-276`; `backend/app/memory/manager.py:1-220`）。 |
| Observability | 2 | Trace/SQL/redaction/span 已有；不是实时 Run Event，日志仍 raw（`backend/app/trace/sql_store.py:1-220`; `backend/app/services/qb_service.py:180-198`）。 |
| Evaluation | 1 | Eval runner/metrics/judge 有；未接入聊天变更回归门禁（`backend/app/evaluation/runner.py`; `backend/tests/evaluation/*`）。 |
| Security | 1 | JWT/owner scope/redaction/MCP 正向存在，但 qBittorrent 路由未认证（`backend/app/api/deps.py:20-90`; `backend/app/api/v1/rss.py:28-93`）。 |
| Provider Independence | 2 | ChatOpenAI/DeepSeek/OpenAI Gateway/Ollama 检查并存；usage/error contract 未统一（`backend/app/agents/graph.py:195-231`; `backend/app/harness/model_gateway.py:32-73`）。 |
| Testability | 2 | 单元测试丰富；真实主路径、安全和恢复组合测试缺失（`backend/tests/harness/*`; `backend/tests/evaluation/*`; `backend/tests/trace/*`）。 |

## Gap 总表

| ID | 严重度 | 主题 | 置信度 |
|---|---|---|---|
| G-P0-01 | P0 | qBittorrent RSS 未认证外部副作用 | 高 |
| G-P1-01 | P1 | Agent Loop 所有权与 Runtime/LangGraph 边界分裂 | 高 |
| G-P1-02 | P1 | Registry/Schema/Policy/Result 未统一 | 高 |
| G-P1-03 | P1 | 交互 Run、SSE 断开、重启恢复缺失 | 高 |
| G-P1-04 | P1 | Tool/REST 写操作幂等和补偿不完整 | 高 |
| G-P1-05 | P1 | token/费用/步数/超时/取消预算不统一 | 高 |
| G-P1-06 | P1 | Trace/Event/SSE 不能组成可重放事实链 | 高 |
| G-P1-07 | P1 | Prompt/Tool output/日志的信任和脱敏边界 | 中高 |
| G-P1-08 | P1 | SQLite/PostgreSQL、业务 DB、checkpoint 模式不一致 | 高 |
| G-P1-09 | P1 | 多模型 adapter 没有统一 usage/error/cost contract | 高 |
| G-P1-10 | P1 | Memory 双实现和事实提取污染风险 | 中高 |
| G-P1-11 | P1 | 图错误到 Runtime 状态的分类可能丢失 | 中 |

## Gap 详细卡片

### G-P0-01：qBittorrent RSS 未认证外部副作用

- **严重度**：P0。
- **证据**：`rss.py` 的所有路由只声明 `Depends(check_qb_enabled)`（`backend/app/api/v1/rss.py:16-105`）；依赖只读配置开关（`backend/app/api/deps.py:76-90`）；`QBService` 用服务端凭据执行登录、添加、删除和规则修改（`backend/app/services/qb_service.py:24-43,95-217`）。
- **风险**：开关启用时，未认证请求可控制下载订阅和自动规则，影响外部系统状态；错误 detail 还可能把下游异常返回调用方（`backend/app/services/qb_service.py:44-60,103-112`）。
- **建议**：在唯一 side-effect gateway 加入认证、资源/能力 allowlist、审计、明确用户主体和默认拒绝；在写入口要求幂等键和二次确认；先为现有 REST route 增加 negative tests。
- **前置依赖**：确认部署认证/TLS/网络边界；确定 qBittorrent 操作是否按用户隔离或仅管理员能力；定义幂等 key 存储。
- **置信度**：高；无需运行态猜测即可由路由依赖确认。

### G-P1-01：Agent Loop 所有权分裂

- **严重度**：P1。
- **证据**：`AgentRuntime.stream` 负责外层 state、trace、结果 synthesis（`backend/app/harness/runtime.py:181-305`）；`FeatureFlagRoutingAdapter` 负责 handoff/specialist/fallback（`backend/app/harness/routing_adapter.py:19-66`）；`ChatWorkflow` 负责 think/tools/speak、model binding 和 graph recursion（`backend/app/agents/graph.py:90-108,195-298`）。
- **风险**：预算、重试、取消、审批和状态转移无法在一个 owner 内保证；graph 的 `error` chunk 可能绕过 Runtime 异常路径（`backend/app/agents/graph.py:470-477`）。
- **建议**：定义单一 Run Coordinator；LangGraph 只作为 Loop adapter；所有模型决定和 Tool invocation 先转为结构化 Decision/Invocation，再由 Runtime 执行/记录。
- **前置依赖**：先冻结当前 SSE 事件兼容表；定义 Run/Step/Invocation 状态机和错误 taxonomy；保留现有 Graph 作为 adapter。
- **置信度**：高。

### G-P1-02：Registry、Schema、Policy、Result 未统一

- **严重度**：P1。
- **证据**：静态 `ALL_TOOLS`/LangChain `ToolRegistry`（`backend/app/agents/tools.py:8-26`; `backend/app/agents/registry.py:1-55`）、`CapabilityRegistry`/`ActionDescriptor`（`backend/app/capabilities/registry.py:1-65`; `backend/app/capabilities/types.py:10-53`）和 MCP Exposure（`backend/app/mcp_server/__init__.py:296-353`）并存；Graph 直接输出 raw Tool payload（`backend/app/agents/graph.py:445-463`）。
- **风险**：同一能力在不同入口有不同权限、schema、错误和输出；未来将 Schedule/qBittorrent 接入聊天时，模型参数可能伪造主体或绕过 policy。
- **建议**：建立统一 CapabilityDefinition/Invocation/InvocationResult；由 registry 生成 LangChain/MCP/HTTP adapter；身份从 execution context 注入，不出现在公开模型 schema；保留业务 Service 不变。
- **前置依赖**：列出能力 canonical name/version；确定 output/error schema；把 `requires_auth/is_side_effect` 扩展为 risk/timeout/retry/idempotency/approval。
- **置信度**：高。

### G-P1-03：交互 Run、SSE 断开、重启恢复缺失

- **严重度**：P1。
- **证据**：主聊天构造 Runtime 时无 `checkpoint_store`、无 task_id（`backend/app/api/v1/agent.py:176-219`）；前端没有 Last-Event-ID 或 reconnect（`frontend/src/lib/fetcher.ts:147-177,277-290`）；Docker backend 无 `data/` 挂载（`docker-compose.yml:73-125`）。
- **风险**：用户无法区分“生成完成/下游仍运行/已取消/已失败”；重连可能重复提交，服务重启可能丢图状态，写能力可能重复执行。
- **建议**：先持久化 Run/Step/Invocation/Event，SSE 只做投影；支持 GET Run、按 sequence 补拉、cancel endpoint 和 lease；将 graph checkpoint 与 Run 状态关联。
- **前置依赖**：统一 ID；确定事件存储、保留期、并发 lease 和 API 兼容策略；确认实际部署卷/迁移流程。
- **置信度**：高。

### G-P1-04：写操作幂等和补偿不完整

- **严重度**：P1。
- **证据**：qBittorrent upsert 删除旧 feed 后添加新 feed，异常没有补偿（`backend/app/services/qb_service.py:115-151`）；REST RSS 没有幂等入参（`backend/app/api/v1/rss.py:28-93`）；Schedule `_idempotency_key` 只计算而不查存储（`backend/app/capabilities/schedule.py:78-149`）。
- **风险**：客户端重试、SSE 断开后的重放或服务恢复会导致重复添加/删除/规则写，upsert 失败可能留下半完成状态。
- **建议**：副作用 gateway 以 `(principal, capability, idempotency_key)` 持久化 invocation；不支持原子更新的 qBittorrent 操作要有状态机/补偿和可审计中间态。
- **前置依赖**：side-effect inventory、幂等表、错误分类、调用方重试约定。
- **置信度**：高。

### G-P1-05：预算与取消不统一

- **严重度**：P1。
- **证据**：Graph 只有 `recursion_limit=24` 和模型 90s timeout（`backend/app/agents/graph.py:20,195-231,242-247`）；Runtime `max_model_calls` 只限制 specialist 结果合成，不限制 graph LLM/tool loop（`backend/app/harness/runtime.py:227-262`）；Memory extractor 和 embedding 路径无同一 Run deadline（`backend/app/memory/extractor.py:1-160`）。
- **风险**：多次 Tool Calling、Memory extraction、provider call 叠加造成不可预测延迟/费用；取消可能只停止 UI。
- **建议**：RunBudget 统一 token/cost/model_calls/tool_calls/steps/deadline；所有 adapter 使用同一 cancellation token；超限生成结构化 `budget_exceeded`。
- **前置依赖**：各 provider usage 采集；定价配置；定义 Tool timeout/retry 分类。
- **置信度**：高。

### G-P1-06：Trace/Event/SSE 不能组成可重放事实链

- **严重度**：P1。
- **证据**：SQL Trace 虽有 `trace_event`，但主聊天只将 `SqlTraceStore` 作为 Runtime trace store，事件持久化与 stream 生命周期绑定（`backend/app/api/v1/agent.py:176-219`; `backend/app/harness/runtime.py:181-336`）；SSE sequence 只在响应包装层生成（`backend/app/api/v1/agent.py:220-231`）。
- **风险**：断线、进程崩溃或错误发生在最终 record 前时，无法解释真实步骤；前端展示顺序不等于 durable event 顺序。
- **建议**：一个 EventWriter 同时服务 SSE/Trace，服务端分配单调 sequence；把 event append 设计为幂等；Trace 作为查询投影。
- **前置依赖**：Run/Invocation schema、redaction 策略、事件保留和容量规划。
- **置信度**：高。

### G-P1-07：Prompt/Tool output/日志信任与脱敏边界

- **严重度**：P1。
- **证据**：客户端 `prompt_config` 被拼入 speak system prompt（`backend/app/api/v1/agent.py:106-117`; `backend/app/agents/graph.py:180-193`）；Memory/tool output 回流模型/前端，没有 trust label 或统一清洗（`backend/app/agents/graph.py:233-240,445-463`）；tool/qB 日志记录 raw args/error/payload（`backend/app/agents/tools/base.py:20-58`; `backend/app/services/qb_service.py:180-198`）。
- **风险**：外部文本可伪装系统指令、污染 Memory、诱导泄露内部信息；日志/前端可能暴露敏感输入和下游错误。
- **建议**：把用户偏好、外部数据、Tool result、系统 policy 分层；模型只能得到带来源/可信度的 data block；统一 response/error redaction，默认不发送 raw output 给 SSE。
- **前置依赖**：数据分类、可展示字段 schema、Memory fact provenance、注入回归集。
- **置信度**：中高；注入是否可利用取决于外部数据内容，但缺少边界是确定事实。

### G-P1-08：SQLite/PostgreSQL、业务 DB、checkpoint 模式不一致

- **严重度**：P1。
- **证据**：业务 DB 按部署模式切换（`backend/app/core/config.py:39-49`），graph checkpoint 永远是 `AsyncSqliteSaver` 文件（`backend/app/agents/graph.py:44-78`）；compose cloud 只挂载 PostgreSQL/Redis/qB volumes，不挂 backend data（`docker-compose.yml:15-125`）。
- **风险**：云模式多 worker/容器的图状态不可共享；部署重启可能丢 thread checkpoint；schema/migration 状态与启动 `create_all` 可能不一致。
- **建议**：把 checkpoint 作为明确持久化存储和部署资源，或者设计 DB-backed adapter；启动只执行可审计 migration；为 SQLite/PostgreSQL 做同一 contract/integration test。
- **前置依赖**：确认生产部署；选择 checkpoint backend；定义迁移 owner 与兼容版本。
- **置信度**：高（配置事实）；生产卷实际情况未确认。

### G-P1-09：多模型 Adapter 缺少统一 usage/error/cost contract

- **严重度**：P1。
- **证据**：Graph 使用 ChatOpenAI/DeepSeek，Gateway 使用 AsyncOpenAI，Ollama 只在 models/check 中单独 HTTP 调用（`backend/app/agents/graph.py:195-231`; `backend/app/harness/model_gateway.py:32-73`; `backend/app/api/v1/agent.py:412-435`）。代码没有统一 model response usage/cost/error type 写入 Runtime state/Trace。
- **风险**：预算、重试、评估和多 provider 行为不可比较；provider 原始异常可能直接进入 SSE/HTTP detail。
- **建议**：ModelGateway 返回版本化 `ModelCallResult`，含 usage、latency、finish reason、provider error category；Graph 通过 adapter 接入同一 gateway。
- **前置依赖**：provider usage 字段兼容性、价格配置、错误 taxonomy、假 provider 契约测试。
- **置信度**：高。

### G-P1-10：Memory 双实现和事实提取污染风险

- **严重度**：P1。
- **证据**：主路径注入 `MemoryServiceImpl`/SQL repository（`backend/app/api/v1/agent.py:137-150`），同时保留 `MemoryManager`/`StoreMemoryRepository`；事实提取把 checkpoint 最近对话直接交给 LLM 并写 semantic facts（`backend/app/memory/service.py:237-276`; `backend/app/memory/extractor.py:1-160`）。
- **风险**：调用方选择不同实现会得到不同 scope/embedding 语义；恶意/错误 Tool output 可变成长期用户事实，影响后续回答。
- **建议**：明确单一 Memory port；记录 source/provenance/confidence/expiry；提取前分离 untrusted content，必要时用户确认后晋升 semantic/profile memory。
- **前置依赖**：事实类型策略、删除/retention 合约、现有 SQL/Store 数据迁移方案（本轮不执行）。
- **置信度**：中高。

### G-P1-11：Graph 错误状态可能丢失

- **严重度**：P1。
- **证据**：Graph 最外层将异常转成 `{"type":"error"...}` chunk 并结束，不 re-raise（`backend/app/agents/graph.py:470-477`）；Runtime 只有捕获异常时才将 stream state/trace 标成 failed/cancelled（`backend/app/harness/runtime.py:321-336`）。
- **风险**：部分失败可能被前端 error 事件观察到，但后端没有统一 failed Run；后处理 Memory extraction 的触发条件也可能与回答是否成功不一致（`backend/app/api/v1/agent.py:233-243`）。
- **建议**：adapter 将 error chunk 转为结构化 terminal failure 并由 Runtime 完成一次状态转移；明确是否在 failed/cancelled 后运行 Memory extraction。
- **前置依赖**：定义 terminal event/error taxonomy；补 fake provider/tool 集成测试和数据库断言。
- **置信度**：中；“可能”需要实际 adapter 事件收集确认，代码路径缺口确定。
