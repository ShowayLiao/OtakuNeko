# 重构迁移计划

迁移采用小批次、adapter-first。当前轮不实施任何批次，不修改生产代码、迁移或依赖。

## BATCH-01：Side-effect Security Boundary

**目标**：封堵 qBittorrent 未认证写入口，并让所有高风险 REST 写能力具备统一认证/审计前置条件。

**允许修改范围**：

- `backend/app/api/v1/rss.py`
- `backend/app/api/deps.py`（仅新增/复用认证依赖，不改 JWT 格式）
- `backend/app/services/qb_service.py`（错误/日志脱敏、幂等 gateway adapter）
- `backend/app/schemas/rss.py`
- `backend/tests/` 中 qBittorrent/RSS API 测试与安全回归测试
- 仅为测试需要的文档/配置样例，不改生产部署秘密

**禁止修改**：

- `backend/app/agents/graph.py` 的 Loop 行为
- 数据库迁移、依赖版本、前端事件协议
- 删除旧 qBittorrent service 或改变 qBittorrent 业务语义而未有兼容测试

**前置任务**：确认 qBittorrent 是单管理员能力还是用户资源；确认生产反向代理是否已有认证；定义 idempotency key 的来源和重复请求响应。

**验收测试**：

- 未带 JWT 调用所有 `/v1/rss` 写 route 返回 401/403，不触发 qBittorrent fake client。
- 认证用户调用 read/write 的主体经过服务端依赖，不能由 body 伪造。
- 同一 idempotency key + payload 不重复执行；不同 payload 返回 conflict。
- `upsert` 在 delete 成功/add 失败时有明确 `failed_attention`/补偿结果，且不声称成功。
- 日志/HTTP detail 不包含 qBittorrent password、完整 credential、未脱敏下游异常。

**回滚**：保留旧 endpoint 代码路径但默认 feature flag 关闭；回滚只恢复 route wiring，不回退认证测试或清空任何外部 qBittorrent 状态。回滚前需人工核对已写入的外部资源。

## BATCH-02：Run / Invocation / Event 与取消

**目标**：让交互聊天有唯一 Run Coordinator 的状态、预算、取消和可重放事件；LangGraph 继续作为 adapter。

**允许修改范围**：

- `backend/app/harness/runtime.py`, `task.py`, `state.py`, `result.py`
- 新增/扩展 `backend/app/harness/contracts/`、`persistence/`、`budget/`（若团队选择这些目录）
- `backend/app/agents/langgraph_adapter.py`、`backend/app/agents/graph.py` 仅增加 adapter event/error/cancel bridge
- `backend/app/api/v1/agent.py` 的 Run/SSE/cancel/reconnect wiring
- `frontend/src/lib/fetcher.ts`、`frontend/src/hooks/useChatStreaming.ts` 的协议兼容层
- 对应 tests/evaluation fixtures

**禁止修改**：

- 不在此批次重写全部 Capability/Domain Service
- 不切换 LangGraph 或新增模型框架
- 不修改 DB migrations，除非事先单独批准并拆成独立 batch
- 不同时解决全部 Memory/Prompt injection

**前置任务**：BATCH-01；冻结现有 SSE event 名称和前端兼容行为；确定 Run/Event 存储位置、租约、保留策略；明确 Docker checkpoint 运行态。

**验收测试**：

- 一个聊天请求产生可查询 Run ID、Trace ID 和每次 Invocation ID。
- fake model/tool 能验证 normal、multi-tool、tool failure、timeout、cancel、provider error 的唯一 terminal state。
- SSE 在 sequence N 断开后用 `Last-Event-ID=N` 补拉，不重复执行已完成 Invocation。
- backend 重启/lease 过期能恢复或明确标记 abandoned，不生成第二个副作用 Invocation。
- token/model/tool/elapsed budget 超限时状态为 `budget_exceeded`，而不是等待前端 timeout。

**回滚**：保留旧 `/chat` 事件投影开关；Coordinator 失败时只允许回退到 read-only legacy Graph，禁止把写能力绕过新 Dispatcher；回滚不删除已持久化 Run/Event。

## BATCH-03：Unified Capability / Tool Registry

**目标**：把静态 Tools、Capability Registry、MCP Exposure 和未来 HTTP adapter 映射到一套版本化能力契约。

**允许修改范围**：

- `backend/app/capabilities/types.py`, `registry.py`, `langchain_adapter.py`
- `backend/app/agents/tools.py` 和静态 Tool adapter
- `backend/app/mcp_server/entry.py`, `__init__.py` 的映射层
- `backend/app/harness/capability_adapter.py`, `result.py`
- 对应 registry/schema/result/policy tests

**禁止修改**：

- 不改变 `backend/app/services/` 的业务规则和外部 API 连接
- 不在这一批接入所有 qBittorrent 写操作
- 不删除 legacy registry，直到 parity/contract tests 通过并另有退役任务

**前置任务**：BATCH-02 的 Invocation/Event contract；完成能力 inventory；决定 canonical name/version、safe output 字段、错误 taxonomy。

**验收测试**：

- 七个聊天工具和 Capability action 都能由 registry 导出 deterministic input/output schema。
- `user_id` 不再出现在公开模型 schema；调用上下文注入的主体来自 fake authenticated context。
- 同一能力通过 LangGraph adapter/MCP adapter 返回相同 InvocationResult 错误分类和 redacted output。
- side effect 元数据、timeout/retry/idempotency/approval 缺一不可；默认 policy deny。

**回滚**：保留 `ALL_TOOLS`/旧 Capability adapter 作为只读 fallback；按能力开关切换，失败时不改变业务 Service 和已有 REST route。

## 后续 BATCH-04：Memory / Context Trust

统一 `MemoryService` port，退役/隔离 `MemoryManager` 重复路径；引入 provenance、confidence、expiry、untrusted Tool output 分层，并加入 poisoning/injection eval。前置是 BATCH-02 的 Run/Event 与 BATCH-03 的 Result provenance；禁止在未定义数据迁移和删除策略前直接删除旧 Memory 表（`backend/app/memory/service.py:237-276`; `backend/app/memory/manager.py:1-220`）。

## 后续 BATCH-05：Provider / Eval / Operations

统一 ModelGateway usage/error/cost，接入真实聊天 Eval 门禁，补 PostgreSQL/shared checkpoint/部署重启测试。前置是 BATCH-02 的 budget 和 Event；不在此批次更换模型或依赖（`backend/app/harness/model_gateway.py:32-73`; `backend/app/evaluation/runner.py`; `docker-compose.yml:73-125`）。
