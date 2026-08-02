# TASK-POST-AUDIT-003：Capability、Tool、MCP 与副作用收口

## 目标

将 Legacy Tool、Capability、MCP、Schedule 和其他后端写入口收敛到统一的：

```text
Registry → Schema → Policy → Dispatcher → Adapter → Domain Service
```

本任务不改变 Domain Service 的业务规则，只改变它们被 Harness 调用的边界。

## 依赖

- `TASK-POST-AUDIT-001` 的 Dispatcher 和 Result contract。
- `TASK-POST-AUDIT-002` 的 Run/Invocation/Cancel contract。

## 允许修改的文件

- `backend/app/capabilities/registry.py`
- `backend/app/capabilities/types.py`
- `backend/app/capabilities/factory.py`
- `backend/app/capabilities/langchain_adapter.py`
- `backend/app/harness/capability_adapter.py`
- `backend/app/harness/result.py`
- `backend/app/agents/registry.py`
- `backend/app/agents/tools.py`
- `backend/app/agents/tools/`
- `backend/app/agents/mcp/`
- `backend/app/mcp_server/entry.py`
- `backend/app/mcp_server/__init__.py`
- `backend/app/api/v1/endpoints/schedules.py`
- `backend/app/api/v1/rss.py`
- `backend/app/api/deps.py`，仅限 capability/owner dependency wiring
- 对应 `backend/tests/capabilities/`、`backend/tests/harness/`、`backend/tests/mcp/`、`backend/tests/services/`
- 新增 `backend/tests/acceptance/test_capability_boundary.py`

## 禁止修改

- 不改变 Anime、Schedule、Collection、qBittorrent 等 Domain Service 的业务含义。
- 不将 qBittorrent 写能力直接开放给主 LLM。
- 不删除 Legacy Tool 直到 Registry parity 和主路径 acceptance 通过。
- 不把 `user_id` 添加回 public schema。
- 不把 MCP server 环境变量身份当作任意用户身份接受。

## 实施步骤

### 步骤 1：建立 Capability inventory 和 parity tests

为每个当前可用 action 固定：

```text
canonical name
version
public name
input schema
output schema
risk / side_effect
requires_auth
timeout
retry policy
idempotency mode
approval mode
```

测试必须确认：

- Capability Registry、LangChain adapter、MCP exposure 的 public schema 一致。
- `user_id`、`principal_id`、`db`、token 不出现在 public schema。
- 未注册 action fail closed。
- 默认只派生 read-only action。
- side effect action 默认不向主聊天暴露。

### 步骤 2：统一 ExecutionContext 注入

所有受保护 Capability 只能从可信 `ExecutionContext` 获得：

```text
principal_id
tenant_id
run_id
trace_id
capability_allowlist
deadline
approval_context
```

模型参数只能包含 public business arguments，例如 `schedule_id`、`day_of_week`，不能包含 `user_id`。

### 步骤 3：封锁直接 Capability 调用旁路

处理以下路径：

- `CapabilityAgent.execute()` 不能直接绕过 `CapabilityAdapter`。
- `langchain_adapter` 在没有可信 context 时不得生成可写工具。
- `ToolRegistry` 不得成为第二个未经 Policy 的执行注册表。
- MCP 与主聊天必须使用同一 action metadata 和错误分类。

如果保留 direct execute，仅允许：

- 在 Domain Service 内部调用；或
- 在已经完成 Policy/Context 注入的 adapter 内部调用；或
- 在明确标记为 read-only、无跨用户资源的单元测试 fixture 中调用。

### 步骤 4：补齐 Schedule HTTP 幂等边界

当前 Schedule HTTP route 直接调用 `ScheduleService`，需要增加：

- 用户范围校验；
- `Idempotency-Key` 或等价 request model 字段；
- principal + operation + resource scope；
- payload hash；
- same key/same payload replay；
- same key/different payload conflict；
- unknown operation state 返回 `attention_required`，不得自动重复写入。

Schedule capability 和 Schedule HTTP API 必须使用相同的幂等语义，避免两个入口行为不一致。

### 步骤 5：复核 qB 管理模型

当前 qB 路由已有认证和 allowlist，但仍需在任务中明确：

- qB 是管理员能力，还是每个用户拥有独立资源；
- allowlist 用户能否管理全部 qB 资源；
- resource key 是否足以隔离用户和资源；
- qB operation 未知状态如何人工核对和补偿。

在上述模型未确认前，不允许通过主 LLM 开启 qB side effect。

### 步骤 6：统一 Result 和安全视图

同一个 InvocationResult 需要提供三种明确视图：

```text
model_view：模型可用的安全结构化字段
ui_view：前端展示字段
audit_view：Event/Trace 字段和摘要
```

三者不能通过直接传递 raw dict 互相替代。Tool/MCP/RSS/网页数据必须携带 untrusted/provenance 标记。

## 测试要求

`test_capability_boundary.py` 至少覆盖：

- owner A 不能读取或修改 owner B 的 schedule；
- 模型参数伪造 `user_id` 被拒绝；
- schedule 重复请求不会重复写入；
- idempotency payload conflict 被拒绝；
- policy deny 不到达 Domain Service；
- MCP 未授权 exposure 不可调用；
- tool output 的 prompt injection 不改变 Policy；
- raw output 不进入 Trace/SSE 的敏感字段。

## 验收条件

- 主聊天、MCP、Schedule capability 和 Schedule HTTP 使用可审计的 canonical metadata。
- 所有 side effect 都有 auth、policy、approval、idempotency、timeout、error 和 audit 语义。
- `Capability.execute()` 不再成为未经保护的公共执行入口。
- qB 未确认的管理员/用户资源模型被记录为前置条件，不被代码默认假设。
- 相关 capability/MCP/security/acceptance tests 通过。

## 回滚

- 未迁移的 side effect 默认 deny，而不是回退到 direct service call。
- Legacy read-only tool 可以保留；Legacy write path 不得恢复。
- 幂等记录只追加，不删除历史执行结果。
