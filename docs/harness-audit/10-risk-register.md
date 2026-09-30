# 风险登记表

概率/影响采用 `低/中/高/严重`，状态只表示审计时源码证据，不表示线上已发生事故。

| ID | 风险 | 概率 | 影响 | 状态 | 证据 | 缓解与触发器 |
|---|---|---|---|---|---|---|
| R-01 | 未认证 qBittorrent RSS 写入 | 高 | 严重 | 已证实 | `backend/app/api/v1/rss.py:28-93`; `backend/app/api/deps.py:76-90` | 立即执行 BATCH-01；任何启用 `ENABLE_QB_PROXY` 的部署都触发封堵。 |
| R-02 | SSE 断开后重复提交或未知运行状态 | 高 | 高 | 已证实缺口 | `frontend/src/lib/fetcher.ts:147-177,277-290`; `backend/app/api/v1/agent.py:176-231` | BATCH-02 的 Run/Event/Idempotency；断线/超时必须进入测试门禁。 |
| R-03 | Docker backend 丢失 graph checkpoint | 中高 | 高 | 配置显示风险，运行态未确认 | `docker-compose.yml:73-125`; `backend/app/agents/graph.py:44-78` | 发布前确认卷；没有确认前不承诺可重启恢复。 |
| R-04 | Graph 错误不进入 Runtime failed 状态 | 中 | 高 | 代码路径风险 | `backend/app/agents/graph.py:470-477`; `backend/app/harness/runtime.py:321-336` | BATCH-02 terminal error contract；fake provider/tool integration。 |
| R-05 | 模型/用户提供的 user_id 影响资源访问 | 中 | 严重 | 主聊天未证实，Capability adapter 有风险 | `backend/app/capabilities/schedule.py:20-149`; `backend/app/mcp_server/__init__.py:320-353` | 统一 ExecutionContext；在接入写 Capability 前必须通过 identity negative test。 |
| R-06 | Tool output/prompt 注入污染回答或 Memory | 中高 | 高 | 设计缺口 | `backend/app/agents/graph.py:233-240,445-463`; `backend/app/memory/extractor.py:1-160` | BATCH-03/04 trust labels、provenance、security eval。 |
| R-07 | raw tool/qB 错误或参数进入日志/SSE | 中 | 高 | 已证实路径 | `backend/app/agents/tools/base.py:20-58`; `backend/app/services/qb_service.py:180-198` | 统一 redaction/error envelope；日志字段采样和禁 raw 默认。 |
| R-08 | 多 provider 费用/usage 无法归因 | 高 | 中高 | 已证实缺口 | `backend/app/agents/graph.py:195-231`; `backend/app/harness/model_gateway.py:32-73` | BATCH-05 ModelCallResult/price registry；无 usage 时标记 unknown 而非 0。 |
| R-09 | SQLite checkpoint 与 PostgreSQL 多 worker 不一致 | 高 | 高 | 配置事实 | `backend/app/core/config.py:39-49`; `backend/app/agents/graph.py:69-78` | 选择共享 checkpoint 或限制单 worker；部署/重启集成测试。 |
| R-10 | Cache 生产仍为进程内，状态跨 worker 不一致 | 中高 | 中 | 已证实 | `backend/app/main.py:91-119` | 明确 cache 非 Run source of truth；后续单独决定 Redis backend。 |
| R-11 | qBittorrent upsert 半完成 | 中 | 高 | 已证实代码路径 | `backend/app/services/qb_service.py:115-151` | BATCH-01 compensation/attention state；禁止无幂等重试。 |
| R-12 | Alembic 与启动 create_all 产生 schema 漂移 | 中 | 高 | 需要部署验证 | `backend/app/db/database.py:37-48`; `backend/alembic/env.py:56-88` | 明确 migration owner；在 cloud CI 跑 fresh DB + upgrade + app startup。 |
| R-13 | 前端把取消中的 pending Tool 标成 success | 中 | 中高 | 已证实 UI 行为 | `frontend/src/hooks/useChatStreaming.ts:285-323` | BATCH-02 以服务端 terminal state 驱动 UI；区分 stopped/cancelled/succeeded。 |
| R-14 | Trace 最终落库前崩溃导致审计证据缺失 | 中 | 中高 | 结构性风险 | `backend/app/harness/runtime.py:181-336`; `backend/app/trace/sql_store.py` | EventWriter append-first；Trace 做投影；redaction 失败要有安全降级。 |

## 关键未知量

1. 生产部署是否实际挂载 checkpoint 目录、是否多 backend worker、是否跑 Alembic；查 compose overlay、CI/CD manifest、运行容器挂载和 migration logs。
2. 真实 qBittorrent endpoint 是否被 ingress/auth/network policy 保护；查网关配置并对 `/v1/rss/*` 做匿名请求测试。
3. provider endpoint 的 DNS、redirect、IPv6 与 metadata 防护；查 egress proxy/网络 ACL，并运行 DNS rebinding/redirect 测试。
4. FastAPI disconnect 是否能取消下游 async LLM 和同步 qBittorrent；查 ASGI server logs、provider mock cancel hooks 和 slow external fake。
5. 实际生产是否启用 MCP remote transport；查 MCP 配置来源、headers、TLS 校验和 allowlist。
