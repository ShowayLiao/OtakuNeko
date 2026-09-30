# 安全边界审计

## 身份与资源归属

JWT 由 `create_access_token` 以调用方传入的 `sub` 创建，`get_current_user` 解码后把 `sub` 转为整数并查询用户；JWT secret 为空时 import-time 失败，但配置有空默认值（`backend/app/core/security.py:10-61`; `backend/app/core/config.py:5-12`）。

聊天 API 使用 optional user：认证用户得到 `make_user_thread(user.id, public_id)`，匿名用户得到 ephemeral thread；Memory 只在有 user 时注入 `default_user_id=user.id`，收藏也以 `user.id` 查询（`backend/app/api/v1/agent.py:55-73,137-160`）。聊天历史、线程列表和删除路径继续检查 owner scope（`backend/app/api/v1/agent.py:252-409`; `backend/app/agents/thread_scope.py`）。

**未发现当前源码证据表明模型可以直接伪造 JWT 或 `current_user.id`。** 但静态 Tool/Capability 不能依赖模型提供的 `user_id`：Schedule action schema 把 `user_id` 放在输入中，而 LangChain adapter 直接转发 kwargs（`backend/app/capabilities/schedule.py:20-149`; `backend/app/capabilities/langchain_adapter.py:1-130`）。MCP 路径采取了更安全的做法：从可信 `MCPContext` 删除公开的 `user_id` 并注入真实 user id（`backend/app/mcp_server/__init__.py:320-353`）。

因此身份结论分两层：

- Chat 主路径的七个静态工具目前没有用户写操作，未证实模型能越权读另一个用户的 Memory/收藏；
- 通用 Capability adapter 的身份边界不足，如果把 Schedule 或其他 user-scoped action 接入模型，则模型参数可影响主体，属于 G-P1-02/G-P1-07 的前置安全问题。

## BYOK、Provider Endpoint 与 Secret

前端从 `localStorage` 读取 provider API key，发送 `X-Api-Key`；Next route 会转发该 header；后端优先使用 header，再回退到服务端 `OPENAI_API_KEY`，并把 key 传给 `ChatWorkflow`、Memory extractor 和 Model Gateway（`frontend/src/lib/fetcher.ts:98-134`; `frontend/src/app/api/v1/chat/route.ts:9-24`; `backend/app/api/v1/agent.py:98-150,176-209`）。

正向边界：

- provider endpoint 要求 HTTP(S)、禁止 URL 内凭据，并对字面 private/loopback/link-local/reserved/multicast IP 拒绝（`backend/app/agents/provider_endpoint.py:17-53`）。
- `Trace` redaction 对 `api_key/token/password/secret` 等 key 做脱敏，且普通 Trace 不保留完整 goal/messages/raw prompt（`backend/app/trace/redaction.py:1-180`; `backend/tests/trace/test_event_contract.py:104-130`）。
- Proactive task 的 payload/policy JSON 会拒绝常见 credential 字段（`backend/app/models/agent_task.py:101-119`）。

风险/未确认：

- provider endpoint 允许任意非 IP 域名；代码没有 DNS 解析后再次检查地址的证据，因此是否能通过域名指向内网/metadata 地址必须在真实网络环境验证，不在本轮将其定为已证实 P0（`backend/app/agents/provider_endpoint.py:37-53`）。
- Tool decorator 的日志和异常返回没有统一脱敏，qBittorrent 服务也把 `str(e)` 放入 HTTP detail，并记录完整 RSS URL/rule payload（`backend/app/agents/tools/base.py:20-58`; `backend/app/services/qb_service.py:44-60,103-112,180-198`）。这是 G-P1-07 的证据。
- 不能仅凭 header 转发判断 key 是否会进入第三方 provider 的日志或 SDK debug 输出；实际 provider SDK 日志配置未确认。

## qBittorrent 高风险边界

`rss.py` 所有 route 的依赖列表只有 `check_qb_enabled`；该依赖只检查 `settings.ENABLE_QB_PROXY`（`backend/app/api/v1/rss.py:16-105`; `backend/app/api/deps.py:76-90`）。`QBService` 使用服务器配置用户名/密码登录并直接执行 RSS 添加、删除和规则修改（`backend/app/services/qb_service.py:24-43,95-217`）。

这不是“模型是否能调用”的问题，而是独立 HTTP 攻击面：只要开关打开，未登录请求可触发外部状态变更。该证据满足参考文档 P0 的“未授权外部副作用”定义（参考文档:1818-1827），对应 G-P0-01。

## 收藏、日程与日历

- 收藏写路由均依赖 `get_current_user`，并把 `current_user.id` 写入 Service 查询/写入对象；当前证据支持用户范围控制（`backend/app/api/v1/collections.py:84-138,181-239,242-280`; `backend/app/services/collection_service.py:189-302`）。
- 日程 HTTP 路由依赖认证并传入当前用户；Capability action 也标记 auth/side effect，但存在把 `user_id` 作为公开 schema 参数和缺少持久幂等执行的问题（`backend/app/api/v1/endpoints/schedules.py:30-260`; `backend/app/capabilities/schedule.py:20-149`）。
- 日历目前是前端生成 CSV/语音命令的纯函数，不是后端第三方 Calendar 写入；没有证据表明 AI Agent 能直接改外部 Calendar（`frontend/src/services/CalendarService.ts:7-155`）。

## Prompt / Tool Output Injection

用户可提交 `prompt_config.persona/tone/rules`，后端拼成 speak system prompt；这不是服务端固定 policy prompt，而是客户端可控系统提示的一部分（`backend/app/api/v1/agent.py:106-117`; `backend/app/agents/graph.py:180-193`）。

Memory context 作为 system message 插入，工具结果作为 tool message/前端输出回流；没有显式 trust label、数据/指令分隔或 Tool output 重新验证（`backend/app/agents/graph.py:233-240,445-463`; `backend/app/memory/service.py:169-235`）。因此外部数据若携带“忽略策略/泄露秘密”等内容，当前代码没有可验证的通用防注入层。真实可利用性取决于具体 Bangumi/Service 返回文本和 prompt，但设计缺口已证实，记录 G-P1-07。

## 日志、Trace 与可观测性边界

日志配置将 DEBUG 写控制台、`logs/app.log` 和 error log；`RequestContextFilter` 使用 logger filter 实例属性保存 request id，不是 async ContextVar（`backend/app/core/logging.py:13-30,33-147`）。没有证据表明 Agent route 为每个 Run 设置该 request id。

Trace store 有用户过滤和 redaction，是优点；但 `sanitize_trace` 在检测到 CoT 时会拒绝存储，且主聊天只在 stream 生命周期结束时记录完整 Trace，导致中途失败/断线不一定有可查询 Run event（`backend/app/trace/redaction.py`; `backend/app/trace/sql_store.py:1-220`; `backend/app/harness/runtime.py:321-336`）。

## 安全判断的未确认项

- 生产 CORS origin、反向代理认证、TLS、qBittorrent 是否只在内网可达：配置文件有默认项，但没有部署运行态证据（`backend/app/main.py:146-154`; `.env.example:1-31`）。
- 真实外部 MCP SSE endpoint 的 SSRF/证书/凭据校验：transport 有 timeout，但本轮没有把远端部署配置纳入证据（`backend/app/agents/mcp/sse_transport.py`）。
- provider DNS rebinding/redirect 行为：需网络集成测试，不可由 `urlparse` 静态代码推断。
