# TASK-HARNESS-010

## 目标

让 Schedule Capability 的模型调用只能使用可信 Principal、显式 side-effect policy、approval 和持久化幂等键；不把 `user_id` 暴露为可伪造 authority。

## 背景

对应 `G-P1-02`、`G-P1-04`、`G-P1-07`。Schedule action descriptor 把 `user_id` 放入输入 schema，`CapabilityLangChainAdapter` 直接把模型 kwargs 传入 `capability.execute`；`_idempotency_key` 只计算 hash，不读取幂等存储（`backend/app/capabilities/schedule.py:20-149`; `backend/app/capabilities/langchain_adapter.py`; `backend/tests/capabilities/test_schedule.py`）。MCP 已经演示了从可信 context 注入用户 ID 的模式（`backend/app/mcp_server/__init__.py:320-353`）。

## 允许修改

- `backend/app/capabilities/schedule.py`
- `backend/app/capabilities/langchain_adapter.py`
- `backend/app/harness/policy.py`
- `backend/app/harness/capability_adapter.py`
- `backend/tests/capabilities/test_schedule.py`
- `backend/tests/capabilities/test_langchain_adapter.py`
- `backend/tests/harness/test_capability_adapter.py`
- `backend/tests/mcp/test_policy.py`（仅共享 policy contract 断言）

## 禁止修改

- `backend/app/services/schedule_service.py` 的业务规则
- `backend/app/api/v1/endpoints/schedules.py` 的用户登录行为
- qBittorrent、收藏、前端、数据库迁移
- 在模型输出中接受 `user_id`、admin flag 或 approval token

## 实施要求

1. 公开 Schedule schema 删除 `user_id`；`CapabilityAdapter.execute(context, action, public_args)` 从 `ExecutionContext.principal_id` 生成内部 service args。
2. 写 action 只能在 `PolicyEngine.authorize(principal, descriptor, approval, idempotency_key)` 返回 allow 后执行；默认 deny，approval 只来自服务端状态，不能从模型 arguments 读取。
3. `create/update/delete` 必须要求 BATCH-06 idempotency port；key scope 为 `principal_id + capability + resource_key + key`，同 payload replay，异 payload conflict。
4. `list/get` 可在 authenticated principal 下执行；跨用户 resource 查询统一返回 not_found/denied，不通过异常字符串泄露资源是否存在。
5. 继续复用 `ScheduleService` 的事务和资源级检查；Capability 只负责 Harness policy/context，不复制 Domain Service 规则。

## 兼容要求

- 现有 HTTP Schedule API 仍使用 `get_current_user` 和 service current user；本任务只保护模型/Capability adapter。
- 读 action 的公开工具名和返回 `CapabilityResult` 兼容。
- 未提供 approval/idempotency 的写 action 明确 `policy_denied`/`idempotency_required`，不执行 service。
- 收藏和 qB 写能力不在本 PR 接入 Schedule registry。

## 测试

- 单元测试：公开 schema 无 `user_id`、伪造 user_id 被忽略/拒绝、principal 注入、approval default deny、idempotency replay/conflict。
- 集成测试：fake ScheduleService 记录收到的 user id；两个不同 principal 不能共用资源；policy deny 时 service call count 为 0。
- 回归测试：`cd backend && uv run pytest tests/capabilities/test_schedule.py tests/capabilities/test_langchain_adapter.py tests/harness/test_capability_adapter.py tests/mcp/test_policy.py -q`。
- 手工验证：不启动真实模型，调用 adapter fake action；确认模型 arguments 不能改变 authenticated principal。

## 验收标准

- [ ] 模型不能设置或覆盖 Schedule `user_id`。
- [ ] 所有 Schedule 写 action 有 policy/approval/idempotency 三道前置检查。
- [ ] Domain Service 仍是最终资源级授权和事务 owner。
- [ ] 读能力兼容，写能力未授权/无 key 时不触发 service。

## 回滚

关闭模型写 Schedule exposure，保留 HTTP API 和读 Capability；不把旧的公开 `user_id` schema 重新暴露给模型。保留 policy/idempotency 记录。

## 输出

- 修改文件列表：记录 Schedule descriptor、adapter、policy 和测试。
- 测试结果：报告 identity spoofing、policy、approval、replay/conflict。
- 未解决问题：记录实际产品是否允许用户自动化写日程及审批交互设计。
- 风险说明：说明本任务不覆盖 Collection HTTP 写入，后者由 TASK-HARNESS-011 单独处理。
