# TASK-POST-AUDIT-004：Model、Memory、Checkpoint 与部署一致性

## 目标

把模型 usage、预算、Memory namespace、checkpoint、migration 和 Provider 网络边界纳入同一个可验证的运行契约。

## 依赖

- `TASK-POST-AUDIT-001` 的主 ModelGateway/Decision contract。
- `TASK-POST-AUDIT-002` 的 Run、Budget、Cancellation、Recovery contract。
- `TASK-POST-AUDIT-003` 的 Result/provenance boundary。

## 允许修改的文件

- `backend/app/harness/model_gateway.py`
- `backend/app/harness/model_types.py`
- `backend/app/harness/budget.py`
- `backend/app/harness/runtime.py`
- `backend/app/harness/coordinator.py`
- `backend/app/agents/graph.py`，仅限 model adapter、namespace 和 cancellation wiring
- `backend/app/agents/provider_endpoint.py`
- `backend/app/api/v1/agent.py`
- `backend/app/memory/service.py`
- `backend/app/memory/manager.py`
- `backend/app/memory/interfaces.py`
- `backend/app/memory/extractor.py`
- `backend/app/harness/checkpoint.py`
- `backend/app/core/config.py`
- `backend/app/main.py`
- `backend/Dockerfile`
- `docker-compose.yml`
- `backend/alembic/env.py`
- `backend/alembic/versions/`，仅限经独立批准的 schema migration
- 对应 memory、provider、budget、deployment、acceptance tests

## 禁止修改

- 不把真实 Provider Secret 写入测试、日志、Eval 或文档。
- 不把未知 usage 当作 0 token/0 cost。
- 不在本任务中升级模型、替换 Provider 或修改 BYOK 存储策略。
- 不在未确认部署环境的情况下宣称支持多 Worker recovery。
- 不删除旧 Memory 表或旧 checkpoint 数据。

## 实施步骤

### 步骤 1：主模型 usage 失败测试

覆盖：

- provider 返回 token usage 时，RunBudget 使用真实 usage；
- provider 未返回 usage 时，记录 unknown usage；
- unknown usage 不产生虚假 cost=0；
- provider timeout、cancelled、transient、permanent 映射一致；
- synthesis 和 primary inference 的 usage 都有调用 ID 和 trace correlation；
- 达到 model/token/cost budget 后不再发起新模型调用。

### 步骤 2：完善 ModelGateway

主推理和 synthesis 都必须经过 provider-neutral interface：

```text
ModelGateway.infer(context, decisions_schema) → ModelCallResult
ModelGateway.synthesize(context, results) → ModelCallResult
```

业务层不得直接依赖 LangChain message/provider response。Provider adapter 负责：

- timeout；
- cancellation；
- error classification；
- usage normalization；
- latency；
- model/provider metadata；
- safe error detail。

### 步骤 3：修正 Memory Run namespace

统一以下约束：

```text
thread_id = user-scoped conversation thread
checkpoint_ns = run_id 或明确的 stable execution namespace
```

Memory retrieve、fact extraction、Graph checkpoint 和 resume 必须使用同一映射函数，不能在多个文件中硬编码 `checkpoint_ns=""`。

补充测试：

- Run A 不读取 Run B 的短期上下文；
- 同 thread 新 Run 能按定义读取允许的历史上下文；
- Memory extraction 只读取当前 Run 范围；
- user scope 和 thread scope 同时生效。

### 步骤 4：把事实提取纳入运行契约

二选一，并在实现记录中明确：

#### 方案 A：Run child invocation

事实提取属于当前 Run 的 child invocation，使用同一 budget/cancellation/trace。

#### 方案 B：独立异步任务

事实提取不再隐藏在 `/chat` finally path，而是创建独立任务、独立 Run/Trace、独立 budget，并向用户请求成功与否明确解耦。

不得让一次隐藏模型调用既不计入主 Run，也不产生可查询状态。

### 步骤 5：Provider endpoint 网络边界

在 `provider_endpoint.py` 增加或明确：

- DNS 解析后检查所有 A/AAAA 地址；
- 重定向目标重新校验；
- 禁止 loopback、private、link-local、metadata、reserved 地址；
- 允许的 scheme、port 和 host allowlist；
- 生产环境通过 egress policy 二次限制；
- 测试覆盖 DNS rebinding、IPv6、redirect 和 userinfo。

如果部署层已经保证这些规则，必须把配置和验证命令记录到执行记录，而不是只依赖代码判断。

### 步骤 6：Checkpoint、Alembic 和启动责任

明确并验证：

- 谁负责执行 Alembic upgrade；
- 应用启动是否允许 `create_all`；
- fresh PostgreSQL upgrade 后 Run/Event/Invocation 表是否一致；
- checkpoint 是否共享、是否支持多 Worker；
- 容器重启后 `RunStore` 和 checkpoint 是否仍可用；
- rollback 如何处理已存在的 Run/Event 数据。

Docker compose 不得把本地 SQLite checkpoint 误标为可恢复的生产持久化。

## 验收条件

- 主模型和 synthesis 都经过 ModelGateway。
- RunBudget 能看到实际模型调用的 usage/latency/cost 或明确 unknown。
- Memory 和 Graph 使用一致的 Run namespace。
- 事实提取是可追踪、可预算、可取消的 invocation 或独立任务。
- Provider endpoint 有代码和部署层双重 SSRF 防护证据。
- fresh DB、Alembic upgrade、应用启动、checkpoint recovery 和多 Worker/单 Worker限制有测试或明确文档结论。

## 回滚

- Provider usage 无法解析时，降级为 unknown，不无限重试。
- Memory namespace 迁移保留旧 namespace 兼容读取，禁止静默删除旧数据。
- checkpoint backend 切换失败时，只允许单 Worker fail-closed，不自动退回未持久化运行。
