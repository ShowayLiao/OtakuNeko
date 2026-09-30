# TASK-HARNESS-000

## 目标

建立当前聊天、Tool、SSE、取消、qB 认证拒绝、Memory 和前端日历纯函数的可重复基线，不改变生产行为。

## 背景

对应 `G-P0-01`、`G-P1-03`、`G-P1-06`、`G-P1-07`、`G-P1-10`；参考文档 Batch 0 要求先记录当前 Agent 行为和补齐测试，不改变业务行为（参考文档:1920-1926）。当前 Runtime/Graph、MCP、Trace、Eval 测试分散，未形成真实聊天主路径组合基线（`docs/harness-audit/06-observability-and-evals.md`；`backend/tests/harness/test_runtime.py`；`backend/tests/agents/test_langgraph_adapter.py`）。日历源码目前是 `BangumiItem → CSV/语音命令` 纯函数，没有第三方 Calendar 写入证据（`frontend/src/services/CalendarService.ts:7-155`）。

## 允许修改

- `backend/tests/acceptance/test_harness_baseline.py`
- `backend/tests/harness/test_runtime.py`
- `backend/tests/agents/test_langgraph_adapter.py`
- `backend/tests/agents/test_provider_endpoint.py`
- `backend/tests/mcp/test_policy.py`
- `backend/tests/memory/test_service_typed.py`
- `backend/tests/trace/test_event_contract.py`
- `backend/tests/evaluation/` 下新增基线 fixture/断言
- `frontend/src/services/CalendarService.test.ts`
- `frontend/src/lib/fetcher.test.ts`

## 禁止修改

- `backend/app/`、`frontend/src/` 中除明确列出的纯测试 fixture 外的生产代码
- `backend/alembic/`、`pyproject.toml`、`requirements.txt`、`uv.lock`
- 真实 API key、qBittorrent 实例、外部 Calendar 或真实 LLM
- 任何现有测试的断言语义，只能为固定当前行为新增覆盖

## 实施要求

1. 使用 fake adapter/fake model/fake tool，不发真实网络请求；为 normal、single-tool、multi-tool、tool-error、provider-timeout、cancel 六条路径分别固定输入、事件序列和 terminal 状态。
2. 基线事件至少记录 `type`、`stream_sequence`、`tool name`、`status`；不要记录真实 Prompt、BYOK 或完整 Tool payload。
3. 增加 qB 路由的匿名请求基线：在当前实现下记录它实际返回的状态，并断言 fake `QBService` 是否被调用；该测试在 BATCH-01 后应反转为“未调用”。
4. 增加 Memory extractor 的 untrusted 文本 fixture，但只断言当前结果，禁止在本任务加入过滤逻辑。
5. `CalendarService.test.ts` 只验证 CSV 转义、事件数量和语音命令生成，不创建网络请求。

## 兼容要求

- 不改变任何 API 响应、SSE event name、前端消息状态或 qB 行为。
- fake fixture 的数据字段使用现有 `AgentTask`、`AgentResult`、`ChatRequest` 结构；不要提前引入 BATCH-02 的新字段。
- 测试可单独运行，不要求 PostgreSQL、Redis、qBittorrent 或外部 provider。

## 测试

- 单元测试：`cd backend && uv run pytest tests/harness tests/agents/test_langgraph_adapter.py tests/agents/test_provider_endpoint.py tests/mcp/test_policy.py tests/memory/test_service_typed.py tests/trace/test_event_contract.py -q`
- 集成测试：`cd backend && uv run pytest tests/acceptance/test_harness_baseline.py -q`
- 回归测试：`cd backend && uv run pytest tests/evaluation -q`
- 前端测试：`cd frontend && pnpm vitest run src/services/CalendarService.test.ts src/lib/fetcher.test.ts`
- 手工验证：启动后端和前端，完成一次只读动漫查询；确认没有真实 provider/qB 请求。

## 验收标准

- [ ] 六条 Agent 路径都有稳定 fake fixture 和明确的终态断言。
- [ ] 基线测试不会读取或输出任何真实 secret/完整 Prompt/完整 Tool output。
- [ ] 匿名 qB 请求的当前行为被测试固定，BATCH-01 有明确反向断言位置。
- [ ] 日历测试证明当前能力是本地纯函数，不把它注册为 Agent Tool。
- [ ] 上述命令全部通过，应用仍能启动，至少一个只读用户流程可用。

## 回滚

删除本任务新增的测试文件和 Eval fixture 即可；不得回退或修改生产代码。若某个基线断言与并行开发冲突，保留 fake fixture，重新记录实际事件，不放宽安全断言。

## 输出

- 修改文件列表：只包含本任务允许范围内的测试/fixture。
- 测试结果：记录每条命令、通过数量和运行环境。
- 未解决问题：记录无法在无外部服务环境确认的 provider/qB 行为。
- 风险说明：说明基线只描述当前行为，不代表当前行为安全。
