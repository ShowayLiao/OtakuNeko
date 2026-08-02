# TASK-POST-AUDIT-009：Shared Checkpoint、Durable Cancellation 与 Worker Recovery

## 目标

让 Run 在断线、进程重启、worker 切换和取消请求后具有确定性的恢复语义：

```text
Run/Event store + shared checkpoint + lease
        ↓
worker claims one Run
        ↓
Runtime resume / cancel / abandon
        ↓
canonical terminal Event
```

SQLite 单 worker 只能作为明确的本地开发适配器；多 worker 部署必须使用具有条件写入、租约和一致性语义的共享存储。

## 依赖

- TASK-POST-AUDIT-007 已统一 Run/Event/Invocation persistence。
- TASK-POST-AUDIT-008 已完成 Context snapshot 和可信恢复输入。

## 允许修改

- `backend/app/harness/checkpoint.py`
- `backend/app/harness/cancellation_store.py`
- `backend/app/harness/runtime.py`
- `backend/app/harness/coordinator.py`
- `backend/app/api/v1/agent.py`
- `backend/app/core/config.py`
- `docker-compose.yml`、部署配置和健康检查（仅验证配置契约）
- `backend/tests/acceptance/`
- `backend/tests/harness/`
- 本任务对应的 execution record

## 禁止修改

- 不在本地执行生产迁移、部署或真实外部副作用恢复。
- 不把进程内 `asyncio.Event` 伪装成跨 worker durable cancellation。
- 不在无法确定副作用结果时自动重试写操作。
- 不覆盖现有 checkpoint、Run/Event 或用户修改。
- 不通过扩大 lease 或关闭状态校验制造“恢复成功”。

## TDD 契约

实现前先增加失败测试，至少覆盖：

1. 同一 Run 只能被一个 worker lease 持有；过期 lease 可被安全接管，旧 worker 的写入被拒绝。
2. cancel API 写入 durable cancellation fact，运行中的 Runtime 在 provider/tool 边界前后都能观察到取消。
3. client disconnect、worker crash、provider timeout、tool unknown outcome 分别映射到确定状态，不能伪造 succeeded。
4. 从 checkpoint 恢复时不会重复已完成的 idempotent invocation；未完成 invocation 必须进入 resume/compensation/unknown 状态之一。
5. recovery、cancel、abandon 和 terminal transition 的 Event 序列可重放且 owner-scoped。
6. 多 worker 配置在启动检查中拒绝 SQLite single-worker 适配器，除非明确是 local mode。

## 实现要求

- Runtime 负责 lease、checkpoint version、cancellation observation 和恢复决策；worker 只是执行载体。
- checkpoint 必须保存安全的 Decision/Invocation 状态摘要和版本，不保存 Secret/raw provider payload。
- 取消只能在授权 owner/scope 下请求；取消与未知外部副作用必须进入补偿或人工核查路径。
- 恢复必须使用 canonical Event/Invocation 状态，而不是只看内存或最后一条 SSE。

## 验收

- fake multi-worker harness 覆盖 claim、lease expiry、cancel、crash、resume 和 duplicate side effect。
- 本地 SQLite、共享 PostgreSQL/Redis 适配器的配置契约分别有测试；不执行生产迁移。
- 后端测试、Ruff、前端协议测试、typecheck、build、Eval 和 `git diff --check` 均有真实退出码。
- Review verdict 为 `pass`，无 blocker/critical/high 或未处理 medium finding。

## 回滚

只切换回已验证的单 worker/local adapter；保留 durable cancellation、checkpoint 和 recovery Event，不删除或重放未知副作用。共享部署恢复前必须暂停新 Run，完成状态对账后再开放。
