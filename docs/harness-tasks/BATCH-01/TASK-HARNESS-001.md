# TASK-HARNESS-001

## 目标

让 qBittorrent RSS 路由在进入 `QBService` 前通过认证和服务端 allowlist；未认证或未授权请求 fail closed。

## 背景

对应 `G-P0-01`。当前 `/v1/rss` 的所有路由只依赖 `check_qb_enabled`，该依赖只检查配置开关；路由没有 `get_current_user`（`backend/app/api/v1/rss.py:1-105`; `backend/app/api/deps.py:76-90`）。参考文档将未授权外部副作用列为 P0（参考文档:1818-1827）。

## 允许修改

- `backend/app/api/v1/rss.py`
- `backend/app/api/deps.py`
- `backend/app/core/config.py`
- `.env.example`（只增加无 secret 的 allowlist 配置说明）
- `backend/tests/api/` 下新增 RSS 认证测试，或现有 `backend/tests/acceptance/`

## 禁止修改

- `backend/app/services/qb_service.py` 的 qB API 操作语义
- `backend/app/agents/graph.py`、`backend/app/harness/`、MCP server
- 数据库模型/迁移、依赖版本、前端代码
- 任何真实 qBittorrent 配置或凭据

## 实施要求

1. 新增 `check_qb_access(user=Depends(get_current_user))`，先复用 `check_qb_enabled`，再检查服务端配置的用户 ID allowlist；allowlist 为空时返回 403，不能默认放行所有已登录用户。
2. 配置字段使用 `QB_ALLOWED_USER_IDS: str = ""`，只解析逗号分隔的正整数；非法配置在启动/依赖调用时 fail closed，不把请求参数作为 allowlist。
3. `/rss/list`、`/rss/rules` 和五个写路由统一使用 `dependencies=[Depends(check_qb_access)]`；路由函数不接受或信任 body 中的 `user_id`。
4. 认证失败、allowlist 失败和 qB 配置关闭分别保持 401/403/配置关闭的可区分响应；不得把 qB 登录异常原文直接返回给客户端。
5. 只包装现有 `QBService`，不把 qB 操作迁移到 Agent Loop，也不引入新的框架。

## 兼容要求

- `ENABLE_QB_PROXY=false` 时保持当前关闭语义。
- 认证后的允许用户仍使用现有 request schema 和响应结构。
- 未授权请求必须在实例化 `QBService` 前终止，避免登录/外部调用。
- 不要求在本任务实现幂等；幂等由 BATCH-09 处理。

## 测试

- 单元测试：测试 `QB_ALLOWED_USER_IDS` 的空值、空格、重复 ID、非法 token 和 allow/deny。
- 集成测试：fake `get_current_user`/fake `QBService` 调用每个 `/rss` route；匿名和登录但不在 allowlist 的请求断言 qB fake 调用次数为 0。
- 回归测试：`cd backend && uv run pytest tests/agents/test_thread_scope.py tests/agents/test_provider_endpoint.py tests/acceptance/test_harness_baseline.py -q`。
- 手工验证：启用配置但不给 allowlist，使用匿名请求访问 `/api/v1/rss/add`，应得到 401/403 且 qB 无新增订阅。

## 验收标准

- [ ] 七个 RSS endpoint 都有认证/allowlist 依赖。
- [ ] 匿名、已认证未授权、已认证授权三类请求的状态和外部调用次数正确。
- [ ] qB password、登录异常和下游 URL 不进入 HTTP detail。
- [ ] 无数据库迁移、依赖、Agent Loop 或前端协议变更。
- [ ] 应用启动和现有只读动漫聊天流程仍可用。

## 回滚

保留 `check_qb_access` 和测试，使用显式 feature flag 回到“所有 qB 路由拒绝”安全状态；禁止回滚到匿名写入。若 allowlist 配置有误，先关闭 qB proxy，不删除 qB 外部资源。

## 输出

- 修改文件列表：记录 route、dependency、config、tests。
- 测试结果：记录匿名/未授权/授权和 qB fake 调用断言。
- 未解决问题：记录实际部署是否另有 ingress 认证；代码不得以此作为放行理由。
- 风险说明：说明 allowlist 是全局 qB 资源访问控制，尚未提供用户级 qB 资源隔离。
