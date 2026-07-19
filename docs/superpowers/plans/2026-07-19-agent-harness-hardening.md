# Agent Harness Hardening 实施计划

> **面向 AI 代理的工作者：** 本计划已依据后端审查结果制定，先修安全和运行时边界，再扩展工具/MCP 能力。

**目标：** 将现有 LangGraph 聊天链路改造成具备用户隔离、可关闭资源、可验证工具契约和可扩展运行时上下文的 Agent harness，同时保持现有 SSE 事件兼容。

**策略：** 采用增量改造。保留现有 think/tools/speak 图；先建立边界和契约，再接入动态 MCP，避免一次性重写导致前端行为回归。

**技术栈：** FastAPI lifespan、LangGraph、LangChain tools、Pydantic v2、AsyncSqliteSaver（本地）/生产可替换的持久化 saver、pytest。

## 任务 1：建立请求上下文和线程所有权边界

**文件：**
- 修改：`backend/app/schemas/agent.py`
- 修改：`backend/app/api/v1/agent.py`
- 修改：`backend/app/agents/graph.py`
- 修改：`backend/app/memory/manager.py`
- 测试：`backend/tests/agents/test_agent_isolation.py`

- [ ] 为运行请求定义 typed context（`user_id`、`thread_id`、provider 标识），服务端生成或校验 thread id。
- [ ] 将 checkpoint 与长期记忆 namespace 变为 `(user_id, thread_id)`，拒绝匿名用户使用共享 default thread。
- [ ] history/reasoning/resume/delete/list 在读取或修改前执行 owner 校验；不存在或无权访问统一返回 404，避免泄漏资源存在性。
- [ ] 只向图传递当前新增 user turn，避免客户端完整历史与 `add_messages` 重复累加。

**验证：** 两个用户的同名 thread 互不可见；匿名请求不能访问持久线程；跨用户 history/delete/reasoning 均失败；连续两轮 checkpoint 不重复旧消息。

## 任务 2：修复 Agent/MCP 运行时生命周期

**文件：**
- 修改：`backend/app/main.py`
- 修改：`backend/app/api/v1/agent.py`
- 修改：`backend/app/agents/graph.py`
- 修改：`backend/app/agents/registry.py`
- 测试：`backend/tests/agents/test_runtime_lifecycle.py`

- [ ] 在 FastAPI lifespan 创建并关闭 saver、Store、MCP manager 和 compiled graph 所需资源。
- [ ] 为 `AsyncSqliteSaver` 增加显式 close/async context 生命周期，避免每个 endpoint 新建连接。
- [ ] 将每次运行的 provider/model/prompt 作为 request-local 数据传入，避免共享可变字段。
- [ ] 为图配置显式 `recursion_limit`、最大工具调用数和运行 deadline。

**验证：** 多次请求只复用受控资源；应用 shutdown 后所有连接和后台 task 均结束；超出预算会产生可识别错误事件。

## 任务 3：统一本地工具契约

**文件：**
- 修改：`backend/app/agents/tools/base.py`
- 修改：`backend/app/agents/tools/anime.py`
- 修改：`backend/app/agents/tools/search.py`
- 修改：`backend/app/agents/tools/profile.py`
- 修改：`backend/app/agents/tools/datetime.py`
- 修改：`backend/app/agents/graph.py`
- 新增：`backend/app/agents/tools/catalog.py`
- 测试：`backend/tests/agents/test_tool_contracts.py`

- [ ] 为每个工具定义显式 Pydantic input/output schema，补充字段说明、范围和示例。
- [ ] 统一成功、失败、错误码、可重试性和 artifact 结构；不再让 decorator 把异常降级成无状态 `{error: ...}`。
- [ ] 工具日志只记录脱敏元数据，并保留 tool call/run correlation。
- [ ] 将用户画像工具改为从运行时用户上下文读取收藏，不让模型传完整数据库对象。
- [ ] 删除 `app/agents/tools.py` 与 `app/agents/tools/` 的同名歧义，统一从 catalog 导出。

**验证：** 运行时 schema 包含真实参数和约束；参数错误在工具执行前被拒绝；失败工具在 SSE 中显示 error 状态；工具输出可被 JSON 序列化。

## 任务 4：接通并规范 MCP

**文件：**
- 修改：`backend/app/agents/mcp/adapter.py`
- 修改：`backend/app/agents/registry.py`
- 修改：`backend/app/agents/graph.py`
- 修改或替换：`backend/app/agents/mcp/connection_pool.py`
- 修改或替换：`backend/app/agents/mcp/stdio_transport.py`
- 修改或替换：`backend/app/agents/mcp/sse_transport.py`
- 测试：`backend/tests/agents/mcp/test_adapter.py`
- 测试：`backend/tests/agents/mcp/test_runtime_integration.py`

- [ ] 从 MCP `inputSchema` 构造完整 LangChain args schema，保留 nested/enum/required/default 等信息。
- [ ] 在图编译前异步解析 runtime tools，并同时用于模型绑定和 ToolNode；检测重名并保留 server 来源。
- [ ] 完成 MCP initialize/initialized、协议版本、session 和断线状态机；优先采用官方 MCP SDK transport。
- [ ] 为 MCP 工具设置超时、重试、熔断和关闭时 pending call 清理。

**验证：** 真实/协议仿真 MCP server 能被发现、绑定、调用和关闭；模型看到的 schema 与 server inputSchema 等价；断线后不会假装 healthy。

## 任务 5：安全事件流和 Provider 适配

**文件：**
- 修改：`backend/app/schemas/agent.py`
- 修改：`backend/app/api/v1/agent.py`
- 修改：`backend/app/agents/graph.py`
- 修改：`backend/app/agents/deepseek_chat_model.py`
- 测试：`backend/tests/agents/test_stream_events.py`
- 测试：`backend/tests/agents/test_provider_capabilities.py`

- [ ] 用 discriminated union 验证 SSE 事件，统一 `run_id/sequence/tool_call_id/error_code`。
- [ ] 移除完整 CoT 外发和持久化，改成简洁 reasoning/progress 摘要。
- [ ] 将 provider URL 判断替换为 capability-based ProviderAdapter，隔离 DeepSeek 特有协议。
- [ ] 对模型工具调用、reasoning、structured output、stream usage 建立 capability contract tests。

**验证：** 所有 SSE 事件都能被 schema 校验；异常、取消、超时有终态事件；新增 provider 不需要改图核心逻辑。

## 全量验证

- [ ] `uv run pytest` 通过。
- [ ] 运行 Agent/MCP/memory/API 集成测试和并发隔离测试。
- [ ] `ruff check backend/app/agents backend/app/api/v1/agent.py backend/app/memory` 无新增问题。
- [ ] 手工验证 anonymous、用户 A、用户 B、MCP tool、resume、shutdown 五条关键链路。
