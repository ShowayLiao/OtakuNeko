# TASK-HARNESS-003

## 目标

将现有静态聊天 Tools、Capability Actions 和 MCP Exposure 映射到一个版本化的只读 Capability Registry，并生成一致的公开输入/输出 Schema；不改变 Tool 内部业务实现。

## 背景

对应 `G-P1-02`、`G-P1-07`。当前存在静态 `ALL_TOOLS`/`ToolRegistry`、`CapabilityRegistry` 和 MCP `ExposureMap` 三套注册协议；现有 parity 测试只证明名称覆盖，不能证明权限、风险、输出和重试元数据一致（`backend/app/agents/tools.py:8-26`; `backend/app/agents/registry.py:1-55`; `backend/app/capabilities/types.py:10-53`; `backend/tests/capabilities/test_tool_parity.py`）。参考文档 Batch 2 要求集中 Tool 元数据、风险标记、Schema 和 Agent allowlist（参考文档:1940-1946）。

## 允许修改

- `backend/app/capabilities/types.py`
- `backend/app/capabilities/registry.py`
- `backend/app/capabilities/langchain_adapter.py`
- `backend/app/agents/registry.py`
- `backend/app/agents/tools.py`
- `backend/app/mcp_server/entry.py`
- `backend/tests/capabilities/test_action_contract.py`
- `backend/tests/capabilities/test_registry.py`
- `backend/tests/capabilities/test_tool_parity.py`
- `backend/tests/agents/test_registry.py`
- `backend/tests/mcp/test_entry.py`

## 禁止修改

- `backend/app/services/`、qBittorrent、收藏、日程实际业务行为
- `backend/app/agents/graph.py` 的 ToolNode/模型循环
- Runtime、数据库迁移、前端协议、Memory
- 在 Registry 中启用任何新的写能力

## 实施要求

1. 将 `ActionDescriptor` 扩展为兼容字段：`version`、`output_schema`、`risk_level`、`timeout_seconds`、`retry_class`、`idempotency_mode`、`approval_required`、`requires_auth`、`is_side_effect`；现有构造调用保持默认值兼容。
2. `CapabilityRegistry` 提供 `get_public_definition(name, version)` 和 `allowed_public_definitions(allowlist)`；返回值不得包含内部 dependency provider、数据库对象或 `user_id` authority 参数。
3. `derive_tools()`/legacy `ALL_TOOLS` 只从 registry 生成或通过 parity adapter 读取定义；首批仅激活现有七个只读 Tool 和已确认的 Anime/System/Recommendation read actions。
4. 对 `Schedule` 写动作、`Media.add_rss_feed`、qBittorrent 写 API 设置 `approval_required=True` 且 registry 默认不暴露；不要在本任务实际执行写入。
5. LangChain/MCP adapter 必须把公开 arguments 与可信 `ExecutionContext` 分开；公开 schema 传入 `user_id` 时拒绝或剥离，不能覆盖 context principal。
6. `CapabilityResult` 和 `AgentResult` 输出通过同一 safe envelope；保留旧字段但新增 output schema 校验和最大 payload 大小。

## 兼容要求

- 现有七个聊天工具名称保持不变，LangChain tool schema 的必需参数保持兼容。
- `tests/capabilities/test_tool_parity.py` 的 legacy name parity 继续通过。
- MCP 当前只读 Exposure 不减少；Schedule/Media 写操作继续默认拒绝。
- 未配置/不支持的能力返回结构化 `not_configured`/`policy_denied`，不抛出 raw dependency error。

## 测试

- 单元测试：Action metadata defaults、版本冲突、public schema 去除 authority 字段、output schema/大小限制。
- 集成测试：legacy 7 Tools 与 registry definitions parity；MCP exposure 与 registry 只读集合一致；传入伪造 `user_id` 不改变 `ExecutionContext.principal_id`。
- 回归测试：`cd backend && uv run pytest tests/capabilities tests/agents/test_registry.py tests/mcp/test_entry.py tests/mcp/test_policy.py -q`。
- 手工验证：启动应用执行动漫搜索、详情和时间查询；确认现有 SSE Tool 名称不变，Schedule/qB 写能力仍不可由 Registry 直接调用。

## 验收标准

- [ ] 只读 Tool/Capability/MCP 定义可通过同一 Registry 查询。
- [ ] 每个定义有 version/input/output/risk/side-effect/auth/timeout/retry/idempotency 元数据。
- [ ] public schema 不把 `user_id` 当作可信身份，写能力默认 deny/approval required。
- [ ] legacy parity、MCP policy、现有聊天 schema 测试通过。
- [ ] 业务 Service、Graph Loop、DB、前端均未被本 PR 改写。

## 回滚

以 feature flag 保留旧 `ALL_TOOLS`/Capability adapter 只读路径；若新 schema 失败，关闭 registry-derived tool exposure，但不恢复任何写能力默认暴露。保留新增 metadata 和 parity tests。

## 输出

- 修改文件列表：记录 registry、descriptor、adapter 和测试。
- 测试结果：报告 legacy/MCP parity、authority spoofing 和 write deny 结果。
- 未解决问题：列出 BATCH-05 Runtime policy 和 BATCH-10 Schedule approval 的接入点。
- 风险说明：说明本任务只统一元数据/公开 schema，尚未持久化 Run，也未实现实际写幂等。
