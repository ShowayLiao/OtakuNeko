# TASK-HARNESS-011

## 目标

为 Collection HTTP create/update/delete/import 写操作增加请求幂等、用户范围一致性和事务/缓存失败可观测性；不把 Collection 写入 Agent Tool。

## 背景

对应 `G-P1-04`。当前 Collection 路由有 `get_current_user` 并把 `current_user.id` 写入查询/数据，这是应保留的安全边界；但写请求没有 HTTP idempotency key，Service 会执行 batch upsert 和全局 cache clear，重试/断线结果没有统一状态（`backend/app/api/v1/collections.py:84-138,181-280`; `backend/app/services/collection_service.py:189-340`）。审计未发现 Agent 可直接修改 Collection，因此本任务不扩大 Agent 能力。

## 允许修改

- `backend/app/api/v1/collections.py`
- `backend/app/services/collection_service.py`
- `backend/app/schemas/collection.py`
- `backend/app/harness/persistence/` 中 BATCH-06 idempotency port 的 HTTP adapter
- `backend/tests/api/test_collections_idempotency.py`
- `backend/tests/services/test_collection_service.py`
- `backend/tests/acceptance/test_end_to_end.py` 的 Collection 回归部分

## 禁止修改

- `backend/app/agents/graph.py`、静态 Tool、Capability Registry、MCP exposure
- Collection/Subject 数据库迁移和历史数据
- 前端 Collection UI 协议，除非仅更新现有 header 的测试 fixture
- 取消现有 `current_user.id` owner scope 或把 body `user_id` 当 authority

## 实施要求

1. create/update/delete/sync/import 写请求支持 `Idempotency-Key` header；长度 1–128，缺少 key 的写请求返回 428/422，不自动从 body 生成。
2. scope 使用 authenticated `current_user.id + HTTP method + canonical resource key`；body 内的 `user_id` 必须被覆盖为 current user 或直接拒绝。
3. 在调用 `CollectionRepo.batch_upsert` 前通过 idempotency store 原子 claim；重复同 payload 返回原结果/已存在资源，payload conflict 返回 409；claim 失败不调用 Repository。
4. 数据库写事务成功后再清理用户相关 cache；cache clear 失败写入结构化 warning/metric，不把已提交的 Collection 回滚成假失败。
5. sync/import 的批量操作记录 payload hash、item count、principal、status；限制单请求 item 数量，避免重放造成无限批量写。
6. Collection 继续保持 HTTP-only write capability；不要把它添加到 `ALL_TOOLS`、Capability exposure 或 MCP。

## 兼容要求

- 现有 GET Collection 和用户范围查询不变。
- 旧前端若未发送 `Idempotency-Key`，写请求会得到可解释错误；前端迁移另开任务，不在本 PR 隐式放宽。
- Repository 的业务 upsert/rollback 语义保持，新增的是调用前幂等和结果记录。
- CalendarService 仍是前端纯函数，不调用 Collection write 或第三方 Calendar。

## 测试

- 单元测试：header 校验、principal override、canonical key、same payload replay、different payload conflict、body user_id 越权。
- 集成测试：fake Repository 调用计数；DB rollback/commit 与 cache clear failure；批量 item limit；不同用户相同 key 隔离。
- 回归测试：`cd backend && uv run pytest tests/api/test_collections_idempotency.py tests/services/test_collection_service.py tests/acceptance/test_end_to_end.py -q`。
- 手工验证：登录用户重复提交同一 Collection update，第二次不产生第二个 Repository write；匿名请求仍被认证依赖拒绝。

## 验收标准

- [ ] 所有 Collection 写 route 都要求 idempotency key 和 current user scope。
- [ ] 重放/冲突/事务失败/cache warning 状态可区分。
- [ ] body `user_id` 不能修改资源 owner；Agent Tool catalog 没有新增 Collection write。
- [ ] 现有 GET/Collection UI API 兼容，数据库 schema 未修改。

## 回滚

关闭 Collection write idempotency adapter 时仍保留认证和 owner scope；不删除幂等记录、不恢复 body user_id authority。若旧客户端受影响，提供明确兼容 header 注入，而不是取消安全校验。

## 输出

- 修改文件列表：记录 route/schema/service/idempotency adapter 和测试。
- 测试结果：报告 owner scope、replay/conflict、transaction/cache 结果。
- 未解决问题：记录批量导入的业务级幂等语义和 cache backend 是否跨进程。
- 风险说明：说明 Collection 写入仍是 HTTP side effect，不属于 Agent Harness 自动能力。
