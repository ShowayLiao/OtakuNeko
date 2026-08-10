# 登录绑定聊天记录修复计划

> **面向实现代理的工作者：** 必须使用 `superpowers:verification-before-completion` 在提交前执行完整验证；实现阶段可使用 `superpowers:executing-plans` 按任务逐项执行。

**目标：** 登录用户的聊天记录只保存到其自己名下并可在不同设备恢复；未登录用户可以临时聊天，但聊天内容不写入后端数据库，也不写入浏览器持久化存储。

**当前事实：**

- 后端已经使用 `user:{user_id}:thread:{public_thread_id}` 作为内部线程边界。
- 登录请求会创建 `agent_run` 和 `agent_run_event`，历史接口按 `user_id` 查询。
- 匿名请求使用临时 `anon:{uuid}` 线程，`durable_run` 为 `false`，不会创建 Run/Event Store。
- `get_optional_user()` 会把缺少 Token 和无效 Token 都静默转换成匿名用户。
- 前端 Zustand 使用固定的 `chat-storage` 保存完整消息，登出时只删除 Token，不清除聊天状态。
- 前端只有在本地消息为空时才读取服务端历史，登录回调只追加当前活动会话，存在重复和跨用户复用风险。

**设计决策：**

1. 后端 Run/Event Store 是已登录聊天的唯一事实来源；前端状态只负责当前页面展示。
2. 未登录聊天只存在内存，刷新、关闭页面或登出后丢弃，不自动迁移到登录用户。
3. 不信任客户端传入的 `user_id`；用户身份始终从认证依赖注入，thread 只作为用户命名空间内的 public id。
4. 缺少 Authorization 头允许匿名临时聊天；提供了但已失效的 Authorization 头返回 401，避免用户无感知地进入不落库模式。
5. 登录后的历史采用服务端替换/刷新，不将服务端消息追加到已有本地消息。

## 任务 1：锁定后端认证与落库契约

**文件：**

- 修改：`backend/app/api/deps.py:130-154`
- 修改：`backend/app/api/v1/agent.py:323-446`
- 测试：`backend/tests/api/test_chat_persistence.py`

- [ ] **步骤 1：补充认证状态测试**

为聊天依赖覆盖三种输入：没有 Authorization、有效 Token、携带但无效/过期 Token。断言缺少头返回 `None`，无效 Token 不再与匿名请求等价，而是返回可被 API 转换为 401 的认证错误。

- [ ] **步骤 2：定义聊天接口的持久化响应契约**

保留匿名聊天能力，但让 SSE 的每个投影明确包含 `durable: false`；已登录请求包含 `durable: true`、`run_id` 和 `thread_id`。认证失败时不启动 Runtime，不生成匿名 Run。

- [ ] **步骤 3：验证用户绑定**

使用两个不同用户和相同 public `thread_id` 调用聊天入口，断言落库的 `agent_run.user_id` 不同、内部 thread 分别为 `user:1:thread:<id>` 和 `user:2:thread:<id>`，且任一用户无法通过历史接口读取另一用户的 Run/Event。

- [ ] **步骤 4：验证匿名不落库**

调用匿名聊天并消费完整 SSE，断言响应为非 durable，`agent_run` 和 `agent_run_event` 没有新增记录，且匿名 thread 不进入 `/chat/threads`。

## 任务 2：补齐后端历史读取和失效 Token 行为

**文件：**

- 修改：`backend/app/api/v1/agent.py:600-846`
- 修改：必要时 `backend/app/api/deps.py`
- 测试：`backend/tests/api/test_chat_persistence.py`

- [ ] **步骤 1：保持历史和线程列表的用户范围过滤**

继续使用 `RunStore.list_for_thread(..., user_id=user.id)` 和 `RunStore.list_threads(user_id=user.id)`；禁止通过请求参数指定用户身份。增加跨用户、未知 thread 和无权限 run 的 401/404 断言。

- [ ] **步骤 2：明确空历史和认证失败**

让历史接口的认证失败保持 401；不要把 401/403 在后端转换为空数组。保留空 thread 返回空消息列表的行为，区分“没有记录”和“没有权限”。

- [ ] **步骤 3：确认数据文件与迁移边界**

验证本地模式使用配置的 `SQLITE_FILE`（当前为 `backend/test.db` 的相对路径），不把 `data/checkpoints.db` 当成聊天历史库；不新增不必要的聊天表，继续以 Run/Event 为事实来源。

## 任务 3：将前端改为认证状态驱动的加载模型

**文件：**

- 修改：`frontend/src/stores/useChatStore.ts`
- 修改：`frontend/src/components/chat/index.tsx`
- 修改：`frontend/src/components/header/User.tsx`
- 修改：`frontend/src/lib/fetcher.ts`
- 视需要修改：`frontend/src/hooks/useChatStreaming.ts`
- 测试：`frontend/src/components/chat/SessionPanel.test.tsx`、新增聊天加载测试或相邻测试文件

- [ ] **步骤 1：移除完整消息的全局持久化**

停止将 `chatMessages` 写入固定的 `chat-storage`。未登录状态的消息只留在 Zustand 内存中；如果确实需要缓存，只允许保存非敏感的 UI 配置和 public thread id，不能保存消息正文、推理内容或工具输出。

- [ ] **步骤 2：引入明确的认证加载状态**

在 `/users/me` 完成前不初始化服务端会话；区分 `authLoading`、`authenticated` 和 `anonymous`。匿名状态不请求 `/chat/threads` 或 `/chat/history`。

- [ ] **步骤 3：登录后服务端优先加载**

登录成功后调用 `listThreads()`，按返回的 public thread id 创建会话，再调用 `fetchChatHistory()` 加载活动会话。历史结果使用 `setSessionMessages()` 替换当前消息，不使用 `sendMessage()` 逐条追加，避免重复。

- [ ] **步骤 4：防止本地匿名会话污染用户会话**

登录前创建的匿名 session 不自动绑定到用户，也不上传其内容。登录成功后进入新的用户会话；如果产品未来需要迁移，必须设计成用户主动确认的单独动作。

- [ ] **步骤 5：退出登录时清理内存状态**

登出时删除 Token、清空当前消息和会话状态、取消进行中的请求，并回到匿名空状态。下一位用户不能看到前一位用户的消息。

- [ ] **步骤 6：显示 durable 状态和认证失败**

聊天请求收到 `401` 时清理失效认证状态并提示重新登录；收到 `durable: false` 时显示“当前为临时会话，未登录不会保存”，不得把临时 Run 当作可恢复历史。

## 任务 4：补齐前端行为测试

**文件：**

- 修改/新增：`frontend/src/lib/fetcher.test.ts`
- 修改/新增：`frontend/src/__tests__/components/chat/*.test.tsx`
- 修改/新增：`frontend/src/stores/useChatStore.test.ts`（若当前测试基础允许）

- [ ] **步骤 1：验证请求身份**

断言有 Token 时 `/api/v1/chat`、`/chat/threads` 和 `/chat/history` 发送 Bearer Token；无 Token 时聊天仍可发送，但不请求服务端历史。

- [ ] **步骤 2：验证登录加载**

模拟服务端线程和历史，断言登录后会话由服务端结果创建，消息被替换而不是追加；重复进入同一会话不会产生重复消息。

- [ ] **步骤 3：验证登出隔离**

断言登出后 Token、消息和会话状态均被清理，随后另一个用户登录不会看到前一个用户的数据。

- [ ] **步骤 4：验证匿名不持久化**

断言匿名发送消息不会调用历史接口，也不会在浏览器持久化存储中留下完整消息正文。

- [ ] **步骤 5：保留既有 Durable Replay 行为**

继续验证 `durable: true` 时断线重放使用 `run_id` 和事件序列；`durable: false` 时不请求 `/runs/{run_id}/events`。

## 任务 5：端到端验证与数据审计

- [ ] **步骤 1：运行后端定向测试**

```powershell
uv run --directory backend pytest tests/api/test_chat_persistence.py tests/agents/test_thread_scope.py tests/acceptance/test_primary_runtime_canonical_persistence.py tests/acceptance/test_sse_replay.py
```

预期：登录落库、跨用户隔离、匿名不落库、SSE durable 标记和历史读取全部通过。

- [ ] **步骤 2：运行前端定向测试**

```powershell
pnpm --dir frontend test -- src/lib/fetcher.test.ts src/components/chat/SessionPanel.test.tsx
```

预期：认证加载、登出清理、历史替换和 Durable Replay 全部通过。

- [ ] **步骤 3：运行完整项目检查**

```powershell
uv run --directory backend pytest
uv run --directory backend ruff check app tests
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend test
pnpm --dir frontend build
```

- [ ] **步骤 4：手工验证数据库落盘**

使用测试用户 A 登录发送一条消息，确认 `backend/test.db` 新增一条 `agent_run` 和对应 `agent_run_event`；退出后使用用户 B 登录，确认 `/chat/threads` 和 `/chat/history` 看不到 A 的 thread；匿名发送后确认数据库没有新增 Run/Event。

- [ ] **步骤 5：审查未提交 diff**

```powershell
git status --short
git diff --check
git diff --stat
git diff
```

确认没有写入 Token、完整用户数据、provider payload 或生成文件；确认改动只涉及认证、聊天加载、测试和必要文档。

## 提交门槛

- 已登录聊天可跨刷新恢复，并且只属于对应用户。
- 未登录聊天不会写后端数据库，也不会写浏览器持久化消息缓存。
- 无效 Token 不会静默降级为匿名会话。
- 用户切换和登出不存在消息泄露或重复追加。
- 相关测试、lint、typecheck、build 全部通过。
- Review verdict 为 `pass`，无 blocker、critical、high 或未处理 medium Finding。

建议拆分提交：

1. `test(chat): cover user-bound persistence and anonymous isolation`
2. `fix(auth): reject invalid chat credentials`
3. `fix(chat): load history from authenticated server state`
4. `fix(chat): clear transient state on logout`

每个提交都必须显式暂存文件，禁止使用 `git add .`、`git add -A` 或 `--no-verify`。
