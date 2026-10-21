# OtakuNeko Agent 前端功能清单

范围：聊天、状态、工具流、会话、认证与刷新、异常、响应式布局。源码以当前工作树为准。Playwright mock E2E 验证前端对 fixture/API 契约的消费，不证明真实 Agent 行为；真实 smoke 的覆盖边界见验收矩阵。

| ID | 预期功能 | 当前源码实际行为与实现位置 | 最终证据 | 严重度/判定 |
|---|---|---|---|---|
| QA-F01 | 首页可见空聊天状态；发送后用户消息只出现一次，助手流式更新；缺 provider key 时给出可理解的配置错误。 | Home 在 frontend/src/app/page.tsx；ChatPage 负责发送和状态，在 frontend/src/components/chat/index.tsx；SSE 和缺配置处理在 frontend/src/lib/fetcher.ts。 | Mock E2E 覆盖空状态、缺配置、空白输入、匿名刷新和分块响应；生产构建 E2E 33/33 通过。agent-browser 实际填写并点击 Send，缺 key 时显示配置错误；没有 API 请求。 | 高，核心流程通过。旧“页面空白”是误述，实际显示正常空聊天状态。missing-key 是预期配置错误，不是缺陷。 |
| QA-F02 | provider/model/role 选择影响后续请求；无效配置能给出恢复提示。 | 默认配置在 frontend/src/lib/chatDefaults.ts；选择器在 frontend/src/components/chat/ModelSelector.tsx、RoleSelector.tsx 和 ChatInput.tsx；请求构造在 frontend/src/lib/fetcher.ts。 | Vitest 相关测试通过；最终 agent-browser 对缺配置提示做了实际点击验证。provider/model/role 选择器的完整浏览器操作未验证。 | 中；设置选择流程仍待专门浏览器覆盖。 |
| QA-F03 | 搜索番剧、选中/移除上下文，再随消息发送和展示。 | SearchTrigger 和上下文 pill 在 frontend/src/components/chat/SearchBar.tsx、ChatInput.tsx、ContextPill.tsx；消息和请求组装在 frontend/src/components/chat/index.tsx、MessageList.tsx。 | 当前 Playwright/agent-browser 对会话搜索有覆盖，但没有完成番剧上下文搜索→选择/移除→消息发送验证。 | 中；明确未验证，不将搜索按钮可见性算作功能覆盖。 |
| QA-F04 | 展示思考、工具参数增量、工具结果，以及成功/失败/取消/超时等终态。 | SSE 解码在 frontend/src/lib/fetcher.ts；工具 Run 状态投影在 frontend/src/hooks/useChatStreaming.ts；展示组件在 frontend/src/components/chat/AgentMessageRenderer.tsx、ProcessStepItem.tsx。 | Mock E2E 覆盖工具流、失败后恢复、取消、断流游标回放和超时；Vitest 全量通过。 | 高；前端消费 mock 事件通过，真实后端工具执行未验证。 |
| QA-F05 | 创建、搜索、切换、删除会话；删除失败时保留会话并显示错误。 | SessionPanel 和会话状态在 frontend/src/components/chat/SessionPanel.tsx、frontend/src/stores/useChatStore.ts；请求及失败反馈在 frontend/src/components/chat/index.tsx、frontend/src/lib/fetcher.ts。 | Mock E2E 覆盖认证历史 reload/search/create 和删除失败保留会话；人工浏览器检查移动抽屉、搜索无结果、新建/关闭流程。 | 中；删除失败反馈已修复并通过自动化验证。 |
| QA-F06 | 匿名会话是临时数据；认证用户可重新加载服务端会话及已完成历史。 | 认证、会话列表和历史映射在 frontend/src/components/chat/index.tsx；store 位于 frontend/src/stores/useChatStore.ts。历史接口只提供 role/content，不包含 Run 元数据，backend/app/api/v1/agent.py。 | Mock E2E 覆盖匿名刷新与认证历史 reload。真实 smoke 有一项通过，但仅验证新账号认证、代理、线程列表、空历史刷新和匿名 401；不验证非空已完成历史持久化。 | 匿名刷新丢失临时消息属预期。已完成历史 reload 有 mock 证据；真实非空持久化没有 smoke 证据。 |
| QA-F07 | 给定 durable runId 时断流可按游标回放，取消与终态一致；支持的刷新恢复应恢复进行中的 Run。 | ChatPage 的恢复入口要求消息带 durable/runId，见 frontend/src/components/chat/index.tsx；回放在 frontend/src/lib/fetcher.ts；取消状态在 frontend/src/hooks/useChatStreaming.ts。服务端历史不含 runId，见 backend/app/api/v1/agent.py。 | Mock E2E 覆盖给定 Run ID 的回放、取消和超时；Vitest 同样覆盖 stream hook。没有从历史自动发现 Run 的证据。 | 能力限制：认证用户刷新后，历史缺少 run 元数据，不能从历史加载路径恢复进行中的 Run；未将预置 runId 测试当作刷新恢复。 |
| QA-F08 | 身份失效时脱离旧身份的前端流，不发送无授权的取消请求，也不显示旧用户内容。 | authRefresh 调用 stopGeneration({ cancelDurable: false })，见 frontend/src/components/chat/index.tsx；generation/queue 生命周期在 frontend/src/hooks/useChatStreaming.ts；401 token 失效保护在 frontend/src/lib/fetcher.ts。 | 新增 E2E auth invalidation detaches a live stream and removes previous-user display；Vitest 覆盖 stopped stream reject 不得复活已清理状态；33 项 E2E、103 项 Vitest 通过。 | 高；前端状态切换与旧流竞态已验证。脱离 SSE 不等于取消服务端 durable Run。 |
| QA-F09 | 编辑、重新生成、复制行为符合明确产品语义。 | 编辑/重新生成处理在 frontend/src/components/chat/index.tsx；消息操作在 frontend/src/components/chat/MessageList.tsx。 | 当前源码编辑/重新生成采用追加新 turn；本轮未验证编辑、重新生成和剪贴板完整路径。 | 产品决策/未验证；是否应替换原分支尚未确认，不据此报告缺陷。 |
| QA-F10 | MCP 状态徽标表达明确定义的连接对象。 | ConnectionStatus 在 frontend/src/components/chat/ConnectionStatus.tsx 标记 MCP；实际状态回调来自 frontend/src/lib/fetcher.ts 的聊天 SSE 生命周期。 | 无 MCP 探测或徽标状态自动测试。 | 产品决策：目前是聊天连接状态，不代表 MCP 服务健康。 |
| QA-F11 | Desktop 1440×900、Tablet 768×1024、Mobile 390×844 下 header、会话抽屉、工具栏和输入均可见可操作。 | 响应式 ChatPage 在 frontend/src/components/chat/index.tsx；ChatInput 在 frontend/src/components/chat/ChatInput.tsx；会话控件及 aria-label 在 frontend/src/components/chat/SessionPanel.tsx。ChatInput 用 ResizeObserver 测量工具栏高度并调整输入区高度，移除固定底部补偿布局。 | 生产构建 Playwright 33/33；最终 agent-browser 三视口检查及 Send 按钮可视边界通过，数值见验收矩阵。旧 390×844 clipping 已修复。 | 高；当前通过。首次 Review 后发现的 Send 裁切已用 RED 回归、修复和 production E2E 验证。 |
| QA-F12 | 保存主题刷新后保持；首屏 hydration 无异常。 | SSR/浏览器主题协调及 Emotion 延迟样式在 frontend/src/components/providers/LobeProvider.tsx。 | Mock E2E saved dark theme hydrates without losing preference 通过；最终 production agent-browser Console/errors 为空。 | 中；当前通过。 |

## 已修复缺陷与 Review finding

| ID | 级别 | 问题与修复 | 验证 |
|---|---|---|---|
| QA-B01 | 高，已修复 | Mobile 390×844 工具栏换行时 Send 按钮超出可视区，实测底边 878.39 > 844。ChatInput 增加 ResizeObserver 工具栏高度测量和高度调整，改为正常 flex 布局且不收缩；ChatPage 删除旧的固定 paddingBottom 补偿。 | 修复前 regression RED：1 项失败、exit 1；截图与 trace：[clipping 截图](../../.runtime/frontend-qa/send-clipping-red.png)、[trace](../../.runtime/frontend-qa/send-clipping-red-trace.zip)。修复后 E2E 等待 CSS 高度 36px 并断言 Send 底边不超过视口；production E2E 33/33。 |
| QA-B02 | 高，已修复 | Review 发现 reset 后旧生成拒绝仍可复活已清理状态，需用 generation guard 和 queue guard 阻止旧流更新。 | Vitest 用例 does not resurrect cleared auth state after a stopped stream rejects；全量 103 项通过。 |
| QA-B03 | 中，已修复 | Review 发现旧用户 A 的迟到 401 可能清除已切换到用户 B 的 token。fetcher 仅在当前 token 仍等于请求 token 时才执行失效处理。 | `frontend/src/lib/fetcher.test.ts` 的 `does not invalidate a new login after a stale DELETE receives 401` 与 `invalidates the same token when DELETE receives 401` 均通过；两者包含在完整 103 项 Vitest 中。认证失效 E2E 是另一条前端流脱离场景，不能替代这两项迟到响应测试。 |

## 仍待确认或未验证

| ID | 类型 | 事实 |
|---|---|---|
| QA-R01 | 能力限制 | 认证用户刷新进行中的 Run 时，历史没有 runId/事件游标，不能从历史恢复。 |
| QA-R02 | 产品决策/未验证 | 编辑与重新生成追加新 turn；预期是否应替换分支未确认；剪贴板复制也未完成端到端检查。 |
| QA-R03 | 产品决策 | MCP 标签绑定聊天 SSE 状态，而非 MCP 健康探测。 |
| QA-R04 | 未验证 | 番剧上下文搜索、选择/移除并随消息发送尚未端到端验证。 |

最终独立 Review verdict：pass，无未处理 Finding。未将未验证项目写成已通过；真实 backend smoke 的范围仅限验收矩阵所列的新账号认证与空历史场景。
