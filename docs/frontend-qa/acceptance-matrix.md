# OtakuNeko Agent 前端验收矩阵

本矩阵记录最终工作树的测试和浏览器证据。生产构建 Playwright 主套件使用 mock API；真实 smoke 与人工 agent-browser 结果分列。Mock 通过不等于真实 Agent 后端或工具能力通过。

## 状态

| 状态 | 含义 |
|---|---|
| PASS | 有明确命令退出码或完成的 agent-browser 步骤。 |
| PENDING | 尚未完成，或没有最终退出码。 |
| LIMITATION | 当前源码/契约不提供该能力路径。 |
| DECISION | 产品预期尚未确认。 |
| FIXED | 有失败复现、修复及后续通过证据。 |

## 功能验收

| ID | 场景与标准 | 最终证据 | 状态 | 剩余范围 |
|---|---|---|---|---|
| QA-F01 | 首页显示聊天空状态；缺 key 时可见错误；mock SSE 分块及终态正常。 | 生产 build Playwright mock 33/33；agent-browser 实际填入并点击 Send，缺配置提示可见；因无 provider key，未发 API 请求。 | PASS | 真实 provider/backend 对话未验证。空聊天状态不是白屏；missing-key 是预期错误。 |
| QA-F02 | provider/model/role 选择影响请求；错误配置可恢复。 | chatDefaults/fetcher Vitest 通过；agent-browser 验证缺配置提示。 | PASS（单测/缺配置浏览器步骤） | 选择器操作及字段变化未完整浏览器验证。 |
| QA-F03 | 番剧上下文搜索、选择/移除、消息发送与展示。 | 当前 E2E/最终 agent-browser 未执行该完整流程。 | PENDING | 会话列表搜索无结果不等于番剧上下文搜索已验证。 |
| QA-F04 | 工具参数增量、调用结果与 Run 终态关联正确；失败/取消/超时不误报成功。 | Mock E2E 覆盖工具细节、错误恢复、取消、断流 replay、timeout；Vitest 全量通过。 | PASS（Mock E2E + Vitest） | 真实 backend Agent/tool runtime 未验证。 |
| QA-F05 | 历史 reload/search/create；删除失败时保留会话并显示错误。 | Mock E2E 覆盖已认证历史 reload/search/create 和 failed delete；agent-browser 检查移动抽屉打开、搜索无结果、新建后关闭。 | PASS（Mock E2E + 浏览器） | smoke 只验证空历史，非空已完成历史的真实持久化未验证。 |
| QA-F06 | 匿名临时会话刷新后清空；认证历史可从服务端加载。 | Mock E2E 覆盖 guest refresh 和认证历史 reload。真实 smoke 最近完成的 1 项仅验证新账号认证、API 代理、线程列表、空历史刷新和匿名 401。 | PASS（Mock）；LIMITED PASS（真实 smoke） | smoke 没有写入并 reload 非空已完成历史；不能声称真实历史持久化已验收。 |
| QA-F07 | 给定 Run ID 时 durable 取消、断流回放、timeout 呈现正确。 | Mock E2E 覆盖给定 Run 的取消、游标回放和 timeout；Vitest 通过。 | PASS（Mock） | 刷新后从 history 自动发现并恢复 in-flight Run 仍是 LIMITATION，history 不含 run metadata。 |
| QA-F08 | 认证失效脱离旧 SSE，不恢复已清理状态、不清除新用户 token。 | 新 E2E auth invalidation detaches a live stream and removes previous-user display；Vitest 覆盖 stopped stream reject；fetcher 使用 token 相等检查避免 stale A 401 清除 B。 | PASS | 只验证前端脱流和 token 状态，不代表 durable backend Run 被取消。 |
| QA-F09 | 编辑/重新生成/剪贴板复制符合产品定义。 | 当前行为追加新 turn；本轮未跑完整交互测试。 | DECISION / PENDING | 等产品语义确认后再验收；无证据判为 bug。 |
| QA-F10 | MCP 状态徽标对应已定义连接状态。 | 徽标名为 MCP，数据实际来自聊天 SSE；无 MCP 探测。 | DECISION | 确认语义后再验收。 |
| QA-F11 | Desktop 1440×900、Tablet 768×1024、Mobile 390×844 下工具栏与 Send 均在视口内，抽屉可用。 | 生产 build Playwright 33/33；最终 agent-browser 三视口截图目视检查通过，抽屉打开、搜索无结果、新建后关闭。Send 底边分别为 863/900、991.16/1024、807.45/844。 | PASS（Mock E2E + 浏览器） | final screenshots: [Desktop](../../.runtime/frontend-qa/final-desktop.png), [Tablet](../../.runtime/frontend-qa/final-tablet.png), [Mobile](../../.runtime/frontend-qa/final-mobile.png)。 |
| QA-F12 | 保存主题刷新后保持，hydration 无错误。 | Mock E2E saved dark theme hydrates without losing preference；最终 agent-browser Console/errors 为空。 | PASS（Mock E2E + 浏览器） | Console 未见新增错误。 |

## 已修复的回归

| ID | 失败证据 | 修复 | 回归结果 |
|---|---|---|---|
| QA-B01 Send 裁切 | 首次 post-review production 手测发现工具栏换行后 Send 底边 878.39 > 844。Red regression 1 failed，exit 1；证据：[截图](../../.runtime/frontend-qa/send-clipping-red.png)、[trace](../../.runtime/frontend-qa/send-clipping-red-trace.zip)。 | ChatInput 用 ResizeObserver 跟踪 toolbarHeight 并增加输入区高度，工具栏采用正常 flex flow 且不收缩；ChatPage 删除旧的固定 paddingBottom 补偿。E2E 等待按钮 CSS 高度 36px 后测量底边。 | production build Mock 33 passed，exit 0；最终人工三视口 Send 均在可视范围。 |
| QA-B02 reset 后旧流拒绝 | Source Review 发现 reset 后已停止的旧生成 Promise reject 可能复活清理状态。 | 增加 generation identity rejection 与 queue guard。 | Vitest 103 passed，含 does not resurrect cleared auth state after a stopped stream rejects。 |
| QA-B03 迟到 401 | Source Review 发现用户 A 旧请求的 401 可能使当前用户 B 的 token 失效。 | 仅当 localStorage 中 token 仍等于发起请求时 token 才 invalidateAuth。 | `frontend/src/lib/fetcher.test.ts`：`does not invalidate a new login after a stale DELETE receives 401`、`invalidates the same token when DELETE receives 401`；包含在 103 项 Vitest PASS 中。 |

## 最终命令结果

| 检查 | 命令与结果 | 状态 |
|---|---|---|
| 前端包管理器 | pnpm 10.15.1。 | 记录 |
| ESLint | pnpm --dir frontend lint；exit 0，0 errors，94 warnings。 | PASS（有 warning） |
| Format check | pnpm --dir frontend format:check；exit 0，0 项失败。 | PASS |
| TypeScript | pnpm --dir frontend typecheck；exit 0。 | PASS |
| Vitest | pnpm --dir frontend test；exit 0，14 files / 103 passed / 0 failed。 | PASS |
| Production build | pnpm --dir frontend build；exit 0。 | PASS |
| Production-build Mock E2E | $env:E2E_EXTERNAL_SERVER='1'; $env:E2E_CHROMIUM_EXECUTABLE_PATH='C:/Users/HACCI/.agent-browser/browsers/chrome-152.0.7977.54/chrome.exe'; pnpm --dir frontend test:e2e；exit 0，33 passed（11 场景 × desktop/tablet/mobile）。 | PASS |
| Mock E2E 场景 | empty/missing configuration/whitespace/guest refresh；incremental stream/tool details/terminal success；backend error recovery；authenticated history reload/search/create；failed delete；responsive composer and mobile drawer；durable cancel；durable cursor replay；timeout terminal；saved dark theme hydration；auth invalidation removes previous-user display。 | 11/11 × 3 viewports |
| Real backend smoke | 前一轮命令 pnpm --dir frontend test:e2e:smoke：1 passed / exit 0，覆盖新鲜测试账号认证、proxy、thread list、空历史刷新、匿名 401。最终视觉修复后 managed-dev 33 Mock + 1 Smoke 重新通过，整体 exit 0。Smoke 不覆盖非空已完成历史持久化。 | LIMITED PASS（最终 rerun exit 0） |
| agent-browser 最终复核 | Production Desktop/Tablet/Mobile 三视口截图目视通过；Mobile drawer open/search no results/create/close；填写并点击 Send 后缺配置错误可见。Console/errors 空；没有 4xx/5xx，缺配置流程未发 API 请求。 | PASS |

Production E2E 的本地 Chromium 为 152.0.7977.54。截图：[Desktop](../../.runtime/frontend-qa/final-desktop.png)、[Tablet](../../.runtime/frontend-qa/final-tablet.png)、[Mobile](../../.runtime/frontend-qa/final-mobile.png)、[Mobile missing-key error](../../.runtime/frontend-qa/final-mobile-error.png)。最终 Send 按钮底边：Desktop 863/900、Tablet 991.16/1024、Mobile 807.45/844。

## Review 状态与边界

- Source Review 第 1 轮的两个 finding（reset 后旧流 reject/queue race；旧用户 A 的迟到 401 保留新用户 B token）均已修复；Source Reviewer 第 2 轮通过。
- 首次 post-review production 浏览器发现 QA-B01；红测、修复、production-build 33 项 E2E 与最终 agent-browser 三视口复核均已完成。视觉修复 Review 未发现新增问题。
- 最终独立 Review verdict：pass，无未处理 Finding。
- 匿名 session 刷新丢失是预期行为。认证 in-flight Run 刷新后缺少 history run 元数据，恢复路径仍未实现。
- Mock E2E 不证明真实 Agent/tool 能力；real smoke 的单项通过只证明上述认证/API proxy/线程列表/空历史/匿名拒绝范围。非空已完成历史持久化、真实模型调用、真实工具执行均未由本轮 smoke 验证。
- QA-F03 上下文搜索选择/发送、QA-F09 编辑/重新生成/复制仍未验证；QA-F10 MCP 标签语义待产品确认。

