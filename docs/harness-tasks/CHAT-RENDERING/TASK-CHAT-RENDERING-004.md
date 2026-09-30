# TASK-CHAT-RENDERING-004：主路径 Chat Contract 回归与发布门禁

## 目标

用真实 chat 主路径的可重复 fixture 验证前端协议归一化、过程渲染、终态显示和 replay 行为，形成 Chat projection 的最终 release gate。

## 依赖

- `TASK-CHAT-RENDERING-001`～`003` 已通过各自 Review。

## 允许修改

- `frontend/src/lib/fetcher.test.ts`
- `frontend/src/__tests__/components/chat/`
- `frontend/src/components/chat/`，仅限修复由契约测试证明的渲染问题
- `backend/tests/acceptance/`，仅限锁定 `/chat` primary SSE Event 字段和 replay fixture
- `docs/harness-audit/15-chat-rendering-audit.md`
- `docs/harness-tasks/CHAT-RENDERING/`
- 对应 execution record

## 禁止修改

- 不通过删除旧测试、降低断言或关闭 primary path 使测试通过。
- 不把 Runtime 直接单测通过写成 chat API 和前端 projection 已通过。
- 不写入真实 Secret、BYOK、完整用户数据、raw provider payload 或完整 CoT fixture。
- 不扩大到 Provider、Memory、MCP、qBittorrent、Schedule 或其他页面。

## TDD / 场景矩阵

必须有确定性 fixture 覆盖：

| 场景 | 必须验证 |
|---|---|
| ordinary response | `thinking_start` → `model_decision(respond)` → `message_*` → `run_completed` |
| single/multi-tool | `tool_call_start/end` 按 Invocation ID 关联，过程不重复 |
| denied/failed/timeout tool | 工具节点和 Run terminal 状态准确，错误 code 安全 |
| provider failure | partial answer 保留，Run 显示 failed，不伪造 completed |
| canonical timeout replay | `run.failed(status=timeout)` 显示 timeout，不降级为普通 failed |
| cancellation | cancel request、cancelled terminal 和 UI presentation 分离 |
| SSE disconnect | 不重新 POST，按 sequence replay 并恢复唯一终态 |
| duplicate/reordered event | reducer 幂等，不能重复追加内容或工具节点 |
| anonymous/durable boundary | 匿名不请求 durable endpoint；持久化 Run 按 owner scope 查询 |
| unsafe output | bounded safe output 展示，不显示 raw secret/prompt/provider payload |

## 验收

- 前端 `pnpm --dir frontend lint`、`pnpm --dir frontend typecheck`、`pnpm --dir frontend test`、`pnpm --dir frontend build` 全部有真实退出码。
- 后端适用 `/chat` primary contract/replay 测试有真实退出码。
- `git diff --check` 通过；完整未提交 diff 对照 `docs/code-review.md` 审查。
- 审计文档逐项更新为源码可证明的状态；未实施内容保持 planned/deferred，不写成 completed。
- Review verdict 为 `pass`，无 blocker、critical、high 或未处理 medium finding。

## 回滚

保留 primary contract fixture 和旧兼容 parser；发布门禁失败时只回滚 chat projection 变更，不关闭 Runtime policy、canonical persistence、redaction 或取消语义。
