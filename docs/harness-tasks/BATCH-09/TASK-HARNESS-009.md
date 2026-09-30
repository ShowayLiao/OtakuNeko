# TASK-HARNESS-009

## 目标

为 qBittorrent RSS 写操作增加持久化幂等键、payload conflict 检查和 upsert 失败补偿/attention 状态。

## 背景

对应 `G-P1-04`，并依赖 BATCH-01 的认证、BATCH-02 的 Invocation、BATCH-06 的持久化。当前 `add/remove/rule` 没有幂等入口，`upsert_rss_feed` 在 URL 改变时先删除再添加，中途失败没有补偿；日志和 HTTP detail 还可能暴露 raw error/payload（`backend/app/api/v1/rss.py:28-93`; `backend/app/services/qb_service.py:95-217`）。

## 允许修改

- `backend/app/schemas/rss.py`
- `backend/app/api/v1/rss.py`
- `backend/app/services/qb_service.py`
- `backend/app/harness/persistence/` 中 BATCH-06 提供的 idempotency port adapter
- `backend/tests/api/test_rss_idempotency.py`
- `backend/tests/services/test_qb_service.py`

## 禁止修改

- qBittorrent 外部实例的现有资源
- `backend/app/agents/graph.py`、前端聊天协议、全部 Capability
- 数据库迁移；幂等存储只使用 BATCH-06 已提供的表/port
- 把失败的 delete+add 伪装成成功，或自动无限重试

## 实施要求

1. 写请求 schema 增加 `idempotency_key: str`，长度 1–128、只允许安全 ASCII；路由把 authenticated principal、operation、resource key、payload hash 交给 `IdempotencyStore.execute_once`。
2. `execute_once(scope, key, payload_hash, operation)` 的结果为 `replayed/conflict/executed`；同 scope+key+hash 重放之前的 safe result，不再调用 qB；同 key 不同 hash 返回 `idempotency_conflict`。
3. qB service 不再把 URL、rule payload、password 或下游异常原文写入普通日志/HTTP detail；对用户返回固定 error code 和安全 message。
4. Upsert 状态按 `read → no-op/plan → remove_old → add_new → verify` 执行；remove 成功/add 失败时记录 `attention_required` 与旧资源标识，能尝试一次受控补偿，补偿失败必须可查询。
5. 只对可安全重试的连接错误标记 `retryable=True`；不对未知 qB 状态自动重试写操作。

## 兼容要求

- 读接口不增加幂等要求。
- 写接口缺少 key 时返回明确 422/400，不自动生成不可追踪 key。
- 同 URL/name 的现有 upsert no-op 行为保留。
- 外部 qB API 调用方法和请求参数保持不变；只包裹状态、审计和错误。

## 测试

- 单元测试：同 key replay、payload conflict、invalid key、qB call count、safe error/log capture。
- 集成测试：fake qB 的 delete/add/verify 成功、add 失败、补偿失败、连接 transient；断开后重复请求不重复写。
- 回归测试：`cd backend && uv run pytest tests/api/test_rss_idempotency.py tests/services/test_qb_service.py tests/mcp/test_policy.py -q`。
- 手工验证：在 qB feature enabled + allowlisted user 下提交同一 key 两次，第二次不产生新订阅；使用 fake client 验证真实 API 未被重复调用。

## 验收标准

- [ ] 所有 qB 写 route 必须有 idempotency key 和 authenticated scope。
- [ ] replay/conflict/failed/attention_required 状态可区分，重试不会重复 delete/add。
- [ ] 失败响应和日志不含 secret、完整 URL/rule payload 或 raw provider exception。
- [ ] 认证、旧 no-op upsert、只读 route 兼容；qB 外部 API 行为未被业务重写。

## 回滚

关闭 qB 写 feature flag，保留只读；保留幂等记录和 attention 状态，不删除外部资源。不得回滚到没有认证或没有幂等 key 的开放写入口。

## 输出

- 修改文件列表：记录 RSS schema/route、QBService、idempotency adapter 和测试。
- 测试结果：报告 replay/conflict/compensation/secret redaction。
- 未解决问题：记录 qB 资源是否应按用户隔离；若仍是全局资源，必须报告 allowlist 限制。
- 风险说明：说明 qB API 本身不支持原子 upsert，attention 状态需要运维处理。
