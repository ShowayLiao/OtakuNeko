# Tool / Capability 清单

字段解释遵循参考文档 §20.4（参考文档:1754-1771）。`未确认`表示源码没有提供足够证据，不能据此推断存在或不存在。

## 聊天主路径静态 Tools

主聊天每个请求创建 `AgentRegistry`，注册 `RecommendationAgent`，再由 `ChatWorkflow` 使用静态 `ALL_TOOLS`（`backend/app/api/v1/agent.py:161-175`; `backend/app/agents/graph.py:44-64`）。这些工具不是 `CapabilityRegistry` 的运行时注册结果。

| 名称 | 实现/输入 Schema | 输出 Schema | 副作用/权限 | 超时/重试/幂等 | 风险 | 测试/Gaps |
|---|---|---|---|---|---|---|
| `get_anime_info` | `agents/tools/anime.py:get_anime_info_tool(anime_id: int)`；LangChain `@tool` 推导输入 | dict，Bangumi 详情或 `success=False,error` | read；无显式 auth | provider/tool 统一未设；无写幂等 | low | `tests/capabilities/test_anime.py`；G-P1-02、G-P1-07 |
| `fetch_audience_reviews` | `anime_id: int` | dict，评论/错误 | read；无显式 auth | 同上 | low | 同上；G-P1-02 |
| `get_anime_staff` | `anime_id: int` | dict | read；无显式 auth | 同上 | low | 同上；G-P1-02 |
| `get_anime_cast` | `anime_id: int` | dict | read；无显式 auth | 同上 | low | 同上；G-P1-02 |
| `search_anime_advanced` | `keyword/tags/rating_min/rating_max/air_date_start/air_date_end/limit`，由函数签名/默认值推导 | dict，搜索结果；可能执行第二次搜索兜底 | read；无显式 auth | 第二次 fallback 不是受控 retry budget（`backend/app/agents/tools/search.py:94-114`） | low/medium | `tests/agents/test_chat_schema.py`；G-P1-05 |
| `get_current_time` | 无业务输入 | dict/字符串时间 | read；无 auth | 无显式 timeout/retry | low | `tests/capabilities/test_registry.py`；G-P1-02 |
| `generate_user_profile_tool` | `collections: List[Dict]`，由模型直接提供完整列表 | `profile`/`evidence` 或 raw error dict | read/派生；没有在工具层绑定 user_id | 无显式预算；无幂等要求 | medium：模型可改写输入数据，但当前证据不足以证明跨用户读取 | `tests/services/test_user_profile_service.py`；G-P1-02、G-P1-07、G-P1-10 |

共同问题：工具 decorator 用 `str(kwargs)[:200]` 记录参数、用 `str(e)` 作为返回错误；没有按字段的 secret/redaction 或错误分类（`backend/app/agents/tools/base.py:20-58`）。Graph 输出也不调用 `AgentResult.from_raw`，而是保留原始 `output_data`（`backend/app/agents/graph.py:445-463`）。

## Capability Registry

`ActionDescriptor` 提供 `input_schema`、`requires_auth`、`is_side_effect`；`CapabilityResult` 只有 `success/data/error/error_type`，没有统一输出版本、风险、timeout、retry、幂等元数据（`backend/app/capabilities/types.py:10-53`）。

| Capability / Action | 实现与当前 Schema | 输出 | 副作用/权限 | 超时/重试/幂等 | 风险 | 测试/Gaps |
|---|---|---|---|---|---|---|
| Anime / `get_info`, `search`, `get_staff`, `get_cast`, `reviews` | `AnimeCapability.actions()` 定义原始输入 schema（`backend/app/capabilities/anime.py`） | `CapabilityResult`，部分 action 再简化数据 | read；通常无需 auth | 依赖 Bangumi Service；无统一 tool timeout/retry | low | `tests/capabilities/test_anime.py`; G-P1-02 |
| Recommendation / `generate_profile`, `match` | `RecommendationCapability` 输入含 `collections`（`backend/app/capabilities/recommendation.py`） | `CapabilityResult` 含 evidence | `requires_auth=True`，但 LangChain adapter 直接把 kwargs 传入 capability | 无统一幂等；模型调用预算只在 specialist 内局部存在 | medium | `tests/capabilities/test_recommendation.py`; G-P1-02、G-P1-07 |
| Schedule / `list`, `get`, `create`, `update`, `delete` | `ScheduleCapability.actions()`；写 action Schema 显式包含 `user_id` | `CapabilityResult` | 读写；写 action `requires_auth=True,is_side_effect=True` | `_idempotency_key` 只计算 hash/返回，不查存储；HTTP route 不接 idempotency key（`backend/app/capabilities/schedule.py:78-149`; `backend/app/api/v1/endpoints/schedules.py:30-260`） | high | `tests/capabilities/test_schedule.py`; G-P1-04、G-P1-07 |
| Media / `library_status`, `list_rss_feeds`, `add_rss_feed` | `MediaCapability` 的 action schema | 未配置时返回 `not_configured` | `add_rss_feed` 标为 side effect/auth，但实现 placeholder，不连接 qBittorrent（`backend/app/capabilities/media.py:1-120`） | 无执行重试/幂等 | medium | `tests/capabilities/test_media.py`; G-P1-02 |
| System / `current_time` | 无敏感输入 | `CapabilityResult` | read | 无 | low | `tests/capabilities/test_registry.py`; G-P1-02 |

`CapabilityLangChainAdapter` 依据 ActionDescriptor 动态建 Pydantic 参数，但 `_inner` 直接 `capability.execute(action, **kwargs)`，没有把可信身份/权限策略作为不可伪造上下文传入（`backend/app/capabilities/langchain_adapter.py:1-130`）。这是 Capability 与 MCP 边界的核心差异。

## MCP 暴露能力

`build_exposure()` 当前只暴露 Anime 读操作、Schedule list、Media `library_status/list_rss_feeds`；没有暴露 Schedule 写操作或 qBittorrent 写操作（`backend/app/mcp_server/entry.py:38-64`）。MCP 调用会先做 exposure、public schema、auth、side-effect policy、idempotency，再从 `MCPContext.user_id` 注入可信用户 ID（`backend/app/mcp_server/__init__.py:296-353`）。因此 MCP 机制本身比聊天静态 Tool 完整，但不能替代未接入 MCP 的 REST 路由。

## 外部副作用与业务写 API

| 能力 | 实现 | 输入/输出 | 当前权限 | 幂等/恢复 | 风险 | 测试/Gaps |
|---|---|---|---|---|---|---|
| qBittorrent RSS add/upsert/remove/rule | `api/v1/rss.py` → `QBService` | Pydantic request；HTTP message；底层 qBittorrent API | 仅 `check_qb_enabled`，不要求登录用户 | add/remove 无幂等；upsert 是 delete+add，无补偿；规则写无事务 | critical | 没有发现针对认证/重放的 API 集成测试；G-P0-01、G-P1-04 |
| 收藏 create/update/delete/batch/import | `api/v1/collections.py` → `collection_service.py` → Repository | Request schema；Unified/JSON | 路由把 `current_user.id` 写入查询/数据；服务按 user id | DB 操作有 rollback/缓存清理，但无请求幂等键；跨副作用缓存清除失败可能已记录错误 | high | `tests/acceptance/test_end_to_end.py` 等；G-P1-04 |
| Schedule HTTP writes | `api/v1/endpoints/schedules.py` → `ScheduleService` | Schedule schema；实体 | `get_current_user`，service 使用当前用户 | 无 HTTP 幂等键；重复请求风险未覆盖 | high | `tests/capabilities/test_schedule.py`；G-P1-04 |
| 日历导出 | `frontend/src/services/CalendarService.ts:7-155` | 本地 BangumiItem → CSV/语音指令 | 不调用后端写入；没有第三方 Calendar API 证据 | 本地纯函数，无服务端副作用 | low | 前端相关测试未确认；未列为 Agent capability |

## 多模型 Adapter

聊天图使用 `ChatOpenAI` 或 `DeepSeekChatOpenAI`；结果合成使用 `OpenAIModelGateway` 的 `AsyncOpenAI`；模型检查还支持 Ollama HTTP `/api/tags`（`backend/app/agents/graph.py:195-231`; `backend/app/harness/model_gateway.py:32-73`; `backend/app/api/v1/agent.py:412-435`）。这些是多个 provider 入口，但尚未统一 usage、cost、finish reason、错误分类和取消语义，因此记录 G-P1-09。
