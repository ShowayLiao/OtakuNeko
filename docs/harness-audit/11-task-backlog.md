# 可执行任务 Backlog

每个任务保持一个可审查目标；允许范围、禁止范围、前置、验收和回滚均列明。任务不代表本轮已执行。

## HARNESS-AUDIT-001：封堵 qBittorrent 未认证路由

- **目标**：所有 `/v1/rss` route 在业务代码执行前验证认证主体和能力权限。
- **严重度/Gap**：P0 / G-P0-01。
- **允许文件**：`backend/app/api/v1/rss.py`, `backend/app/api/deps.py`, qBittorrent API tests。
- **禁止文件**：`backend/app/agents/graph.py`、数据库迁移、依赖锁、前端。
- **前置**：确认管理员/用户权限模型；BATCH-01。
- **验收**：匿名 read/write negative tests；authenticated principal test；开关关闭时 fail closed；HTTP detail 脱敏。
- **回滚**：仅回退 route wiring feature flag；不恢复匿名写入默认值。

## HARNESS-AUDIT-002：为 qBittorrent 写操作建立幂等和补偿边界

- **目标**：add/remove/upsert/rule write 使用持久化幂等键并暴露明确失败状态。
- **严重度/Gap**：P1 / G-P1-04。
- **允许文件**：`backend/app/services/qb_service.py`, `backend/app/schemas/rss.py`, side-effect adapter tests。
- **禁止文件**：不修改 qBittorrent 外部数据、不删除 service、不改 Graph Loop。
- **前置**：HARNESS-AUDIT-001；定义 resource key 和 idempotency store。
- **验收**：same key replay no duplicate；payload conflict；delete/add failure compensation/attention；日志无 raw payload。
- **回滚**：关闭新写 adapter；已有外部状态由人工核对，不自动重复写。

## HARNESS-AUDIT-003：冻结交互 Run/Event 契约

- **目标**：定义 `run_id/step_id/invocation_id/event sequence/terminal status` 及版本。
- **严重度/Gap**：P1 / G-P1-01、03、06、11。
- **允许文件**：`backend/app/harness/`, 新增契约测试；不接业务写能力。
- **禁止文件**：不替换模型框架、不修改业务 Service、不开新的副作用。
- **前置**：确认前端现有 SSE event 兼容表。
- **验收**：fixture 能覆盖 normal/tool failure/timeout/cancel/denied；状态转移非法组合被拒绝；事件 schema deterministic。
- **回滚**：schema adapter 只在测试/feature flag 下启用，保留 legacy event projection。

## HARNESS-AUDIT-004：让 Runtime 成为唯一 Run Coordinator

- **目标**：Runtime 统一拥有状态、预算、取消、重试决策；LangGraph adapter 只报告决策和结果。
- **严重度/Gap**：P1 / G-P1-01、05、11。
- **允许文件**：`backend/app/harness/runtime.py`, `state.py`, `result.py`, `backend/app/agents/langgraph_adapter.py`。
- **禁止文件**：不同时迁移所有 tools、memory、provider；不修改外部写 API。
- **前置**：HARNESS-AUDIT-003；fake model/tool harness。
- **验收**：Runtime 只产生一个 terminal state；Graph error chunk 变成 failure；cancel/deadline 可观测。
- **回滚**：保留 adapter 旧执行路径为 read-only fallback；不能绕过 qB policy。

## HARNESS-AUDIT-005：实现交互 Run 持久化和 SSE 补拉

- **目标**：Run/Invocation/Event 持久化，支持 GET、cancel、Last-Event-ID 补拉。
- **严重度/Gap**：P1 / G-P1-03、06、08。
- **允许文件**：`backend/app/api/v1/agent.py`, `backend/app/harness/persistence/`, `frontend/src/lib/fetcher.ts`、对应 tests。
- **禁止文件**：不假设 localStorage 是服务端事实源；不删除 LangGraph checkpoint。
- **前置**：HARNESS-AUDIT-003/004；确认数据库/部署持久卷。
- **验收**：断线重连不重跑完成 invocation；重启后 run 查询状态正确；sequence 单调且可补拉。
- **回滚**：保留 SSE 旧模式开关；不删除已写 Run/Event。

## HARNESS-AUDIT-006：统一 Capability Definition 与 Dispatcher

- **目标**：静态 7 tools、Capability Registry、MCP Exposure 使用同一 schema/result/policy 元数据。
- **严重度/Gap**：P1 / G-P1-02。
- **允许文件**：`backend/app/capabilities/`, `backend/app/agents/tools.py`, `backend/app/mcp_server/` adapter、contract tests。
- **禁止文件**：不删除旧 registry；不改变 domain service 行为；不接入 qB 写操作。
- **前置**：HARNESS-AUDIT-003/004；能力 inventory 已完成。
- **验收**：schema parity；身份参数从公开 schema 移除；MCP/LangGraph 输出统一；默认 side effect deny。
- **回滚**：逐能力 feature flag，legacy static tool 仅用于 read-only fallback。

## HARNESS-AUDIT-007：统一 ModelCallResult 与预算采集

- **目标**：OpenAI-compatible、DeepSeek、Ollama/其他 provider 返回统一 usage、latency、finish/error/cost envelope。
- **严重度/Gap**：P1 / G-P1-05、09。
- **允许文件**：`backend/app/harness/model_gateway.py`, provider adapters, `backend/tests/agents/`, `backend/tests/evaluation/`。
- **禁止文件**：不更换 provider、不升级依赖、不改变用户 BYOK 存储策略。
- **前置**：HARNESS-AUDIT-003；取得各 provider mock response 样本和价格配置。
- **验收**：usage unknown 不伪造为 0；Run budget 能拒绝超限；错误可区分 transient/permanent/cancelled。
- **回滚**：保留旧 gateway adapter；cost 未知时只降级为不可计费状态，不继续无限调用。

## HARNESS-AUDIT-008：统一 Tool Result/日志脱敏与信任标签

- **目标**：模型和前端只收到版本化安全结果；日志/Trace 默认脱敏；外部 Tool output 标注 untrusted。
- **严重度/Gap**：P1 / G-P1-07、10。
- **允许文件**：`backend/app/agents/tools/base.py`, `backend/app/agents/graph.py`, `backend/app/trace/`, `backend/app/memory/extractor.py`。
- **禁止文件**：不静默删除事实数据、不改数据库 migration、不以字符串替换伪造安全过滤。
- **前置**：HARNESS-AUDIT-006；定义输出字段和 provenance schema。
- **验收**：secret/error/prompt injection corpus；raw Tool output 不进入 system prompt；Memory 不晋升未验证指令；前端只展示 safe output。
- **回滚**：保留 raw output 仅在受控 debug fixture，生产默认关闭；不回退敏感日志。

## HARNESS-AUDIT-009：收敛 Memory 实现

- **目标**：确定 SQL Memory 为唯一主路径，隔离或适配旧 LangGraph Store，并为 facts 添加 provenance/expiry/confidence。
- **严重度/Gap**：P1 / G-P1-10。
- **允许文件**：`backend/app/memory/`, memory contract tests；不执行数据迁移。
- **禁止文件**：不删除旧表/旧 Store、不改变用户删除语义、不升级 embedding 依赖。
- **前置**：HARNESS-AUDIT-008；数据 owner 批准 retention/deletion policy。
- **验收**：同一 user/thread scope parity；poisoning test；删除/retention/rollback test；旧调用方有明确 deprecation。
- **回滚**：adapter 回退旧读取实现，保留写 provenance 兼容字段；不丢用户 memory。

## HARNESS-AUDIT-010：SQLite/PostgreSQL/部署恢复验收

- **目标**：证明实际部署的业务 DB、checkpoint、migration、worker/cache 恢复语义。
- **严重度/Gap**：P1 / G-P1-08。
- **允许文件**：部署测试、CI 配置、只读审计脚本；如需生产代码需另开 migration task。
- **禁止文件**：本任务不修改迁移、不修改数据库数据、不自动加卷。
- **前置**：获取 compose overlay、Kubernetes/CI manifest、migration logs。
- **验收**：fresh SQLite/PostgreSQL schema parity；Alembic upgrade；backend restart checkpoint/run recovery；multi-worker concurrency。
- **回滚**：只回滚测试/CI 变更；环境变更由发布系统单独审批。

## HARNESS-AUDIT-011：聊天主路径组合回归与 Eval 门禁

- **目标**：将真实 API + fake provider + fake Tool + SSE + persistence 纳入 regression，覆盖安全和恢复。
- **严重度/Gap**：P1 / G-P1-03、06、07、09。
- **允许文件**：`backend/tests/acceptance/`, `backend/tests/evaluation/`, `frontend/src/lib/*.test.ts`、测试 fixtures。
- **禁止文件**：不为通过测试修改生产行为、不把真实 secrets 写入 fixtures。
- **前置**：HARNESS-AUDIT-003 至 010 的相应契约。
- **验收**：normal/multi-tool/tool failure/timeout/cancel/reconnect/restart/identity/SSRF/prompt injection/cost latency 维度有可重复结果。
- **回滚**：只移除门禁接入，不删除测试和已记录 baseline。
