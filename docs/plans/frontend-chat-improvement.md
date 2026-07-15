# 前端 Chat 架构改进计划

> 日期：2026-05-20（初版） / 2026-05-21（二期附录）
> 前置：Agent 架构 M1-M4 Tool Step 3 已全部交付，后端 38/38 测试通过
> 基于 `agent-architecture-roadmap.md` 对照前端现状的差距分析

---

## 1. 当前后端能力全景 vs 前端利用度

| 后端能力 | 里程碑 | 前端利用 | 状态 |
|---------|--------|---------|------|
| `CodingAgentState` 五字段 | M1 | 仅隐式消费 `messages` | ❌ 未利用 |
| `AsyncSqliteSaver` checkpoint 跨连接持久化 | M1 | local-only localStorage | ❌ 数据孤岛 |
| `GET /chat/history` 从 checkpoint 读 | M2a | `fetchChatHistory` 已定义但**未调用** | ⚠️ 接口闲置 |
| `DELETE /chat/history/{thread_id}` | M2a | 无调用 | ❌ 缺失 |
| LangGraph `Store` 长记忆 | M2a | 无感知 | ❌ 纯服务端 |
| `ToolRegistry` 统一注册 | M2b | 无感知 | ❌ 纯服务端 |
| `ToolResult` schema (success/error_type) | M2b | 原始 JSON 渲染 | ⚠️ 未结构化 |
| `trim_messages` / `filter_messages` 上下文压缩 | M3 | 无感知 | ❌ 纯服务端 |
| `MCPTransport` + `MCPToolAdapter` | M3 | 无感知 | ❌ 纯服务端 |
| `MCPConnectionPool` 健康检查 | M4 | 无感知 | ❌ 缺状态指示 |
| `MCPHeartbeat` 心跳 | M4 | 无感知 | ❌ 缺状态指示 |
| `completed_steps` / `last_terminal_output` 注入 context | M3 | 无渲染 | ❌ 缺可视化 |
| `fact_model` 参数化 | M3 | 无控制入口 | ❌ 纯服务端 |

---

## 2. 问题分析

### 2.1 致命级：数据孤岛

前端 Zustand store 用 `persist` 存 `localStorage`，后端用 SQLite checkpoint。两端完全隔裂：

```
前端 sessions Map  ←── localStorage ──×── SQLite checkpoint ──→ 后端 threads
     (local only)                              (server side)
```

**后果**：
- 换浏览器/设备后历史丢失
- 前端 session 与后端 thread_id 没有映射
- `fetchChatHistory` 函数存在但从未接入 UI（在 `fetcher.ts:L148`，但 `index.tsx` 无调用点）
- 打开历史会话时只显示 `localStorage` 缓存的消息，不能从服务器恢复完整对话

### 2.2 严重级：会话生命周期断裂

| 操作 | 后端 | 前端 |
|------|------|------|
| 创建会话 | LangGraph checkpoint (thread_id) | localStorage Session 对象 |
| 删除会话 | `DELETE /chat/history/{thread_id}` | 仅删 localStorage，**未调后端** |
| 切换会话 | `graph.aget_state(config)` | 仅切换 local state |
| 列表会话 | `checkpointer.alist(None)` | localStorage sessions 数组 |

前端 `deleteSession()` 删 localStorage 但不调 `DELETE`，服务端 checkpoint 成为永不清理的孤儿数据。

### 2.3 严重级：CodingAgentState 五字段信息丢失

```python
class CodingAgentState(TypedDict):
    messages: ...                  # → 前端消费 ✓
    current_dir: str               # → 前端无感知 ✗
    plan: str                      # → 前端无感知 ✗  ← Planner 执行计划
    completed_steps: List[str]     # → 前端无感知 ✗  ← 执行进度
    last_terminal_output: str      # → 前端无感知 ✗  ← 终端/bash 输出
```

后端 `_call_model` 的日志中记录了 `plan`、`completed_steps`，`load_context()` 注入了 `[执行进度]` 和 `[终端输出]` 到 system prompt。但前端：
- 不知道 Planner 产出了什么计划
- 不知道任务执行到第几步
- 看不到终端输出，只能看到 LLM 转述

### 2.4 改善级：工具调用 UI 体验粗糙

当前工具调用渲染（`index.tsx:L340-L370`）：
```tsx
<details> → <summary> 显示 spinner/✓/✗ + 工具名</summary>
  <pre>JSON.stringify(inputs)</pre>
  <pre>JSON.stringify(output)</pre>
</details>
```

**缺陷**：
- 所有工具统一原始 JSON，无视 `ToolResult` 的 `success` / `error_type` 字段
- 无工具执行耗时显示（`duration_ms` 在 `tool_end` 事件中但未提取）
- 无工具级错误恢复/重试按钮
- 搜索结果类工具的直接渲染能力缺失（如动画卡片预览）

### 2.5 改善级：连接层无可见性

后端 M4 已实现完整的连接管理体系：
- `MCPConnectionPool` — 断线重连、健康检查、审计日志
- `MCPHeartbeat` — 15s 心跳、死亡回调

前端对这些完全无感知——用户不知道：
- 工具调用是否因为连接池健康检查而延迟
- MCP Server 是否宕机
- 当前可用的工具列表是否正常

### 2.6 改善级：流式传输可中断性缺失

当前 `chatWithBackend` 使用 `fetch + ReadableStream`，`while(true)` 循环读流，但没有：
- `AbortController` 取消机制
- 用户点击"停止生成"按钮的能力
- 超时处理

---

## 3. 改进方案

### Phase 1: 会话生命周期统一（优先度：🔴 最高）

**目标**：消除前后端会话数据隔离。

| # | 改动 | 文件 | 说明 |
|---|------|------|------|
| F1.1 | `handleSend` 发 `thread_id` | `index.tsx` | 将 frontend `sessionId` 映射为后端 `thread_id`，在 `chatWithBackend` 中传入 `thread_id` 参数 |
| F1.2 | 初始化时从后端拉历史 | `index.tsx` | 切换会话时调用 `fetchChatHistory(sessionId)`，将返回的 `messages` 填充到 `useChatStore` |
| F1.3 | 删除会话同步后端 | `index.tsx` | `deleteSession()` 增加 `DELETE /chat/history/{thread_id}` 调用 |
| F1.4 | 新增 `listThreads` API | `fetcher.ts` + `agent.py` | 前端调用 `/chat/threads` 列出所有 checkpoint threads，同步到 sessions 列表 |

**验收**：切换到旧会话时能恢复完整对话历史；删除会话后不会产生孤儿 checkpoint。

---

### Phase 2: CodingAgentState 可视化（优先度：🟡 高）

**目标**：暴露 Planner + Executor 进度到前端。

| # | 改动 | 文件 | 说明 |
|---|------|------|------|
| F2.1 | 新增 SSE 事件 `plan_update` | `graph.py` | 在 `_call_model` 或 Planner 节点产出 plan 时，通过 stream 输出 `{"type": "plan_update", "data": {"plan": "...", "steps": [...]}}` |
| F2.2 | 新增 SSE 事件 `progress` | `graph.py` | 在 `completed_steps` 更新时推送 `{"type": "progress", "data": {"completed": [...], "current_step": 3, "total_steps": 5}}` |
| F2.3 | 前端渲染执行进度条 | `index.tsx` | 在 AI 消息上方展示步骤进度面板：带 ✓ 的完成步骤 + 当前执行中的步骤（spinner） |
| F2.4 | 工具用时显示 | `index.tsx` | `tool_end` 事件中提取 `duration_ms`，在工具调用面板显示耗时 |

**验收**：用户能清楚看到 AI 正在执行第 2/5 步、工具调用了多久、哪些已完成。

---

### Phase 3: 工具调用 UI 升级（优先度：🟡 高）

**目标**：按工具类型提供差异化渲染。

| # | 改动 | 文件 | 说明 |
|---|------|------|------|
| F3.1 | 工具结果结构化渲染 | `components/chat/ToolResult.tsx` (新增) | 根据 `tool_name` 分发不同渲染器：`search_anime_advanced` → 动画卡片网格，`get_anime_info` → 详情面板，`get_current_time` → 时间组件 |
| F3.2 | 错误态 UI | `ToolResult.tsx` | 解析 `ToolResult.error_type`，network 显示"网络异常"图标，not_found 显示"未找到"，加"重试"按钮 |
| F3.3 | 搜索动画卡片预览 | `ToolResult.tsx` | `search_anime_advanced` 返回的 `results[]` 数组渲染为 `MediaCard` 缩略图网格（复用 `MediaCard` 组件） |
| F3.4 | 工具详情可折叠 | `index.tsx` | 默认折叠工具输入参数，仅显示工具名 + 状态 + 耗时摘要，展开后显示完整 JSON |

**验收**：搜番结果直接展示卡片而非 JSON blob；工具失败时显示"重试"按钮。

---

### Phase 4: 连接与传输层（优先度：🔵 中）

**目标**：前端感知 MCP 连接状态 + 传输可控。

| # | 改动 | 文件 | 说明 |
|---|------|------|------|
| F4.1 | 新增 SSE 事件 `connection_status` | `agent.py` | 在 `MCPConnectionPool` 或 `MCPHeartbeat` 状态变更时广播 `{"type": "connection", "data": {"server": "...", "status": "connected"}}` |
| F4.2 | 前端连接状态指示器 | `components/chat/ConnectionStatus.tsx` (新增) | 在 ChatInput 工具栏显示 MCP 连接状态小灯（绿/黄/红） |
| F4.3 | 流式生成中止 | `fetcher.ts` + `index.tsx` | `chatWithBackend` 接收 `AbortController`；"停止生成"按钮在 loading 时显示 |
| F4.4 | 网络超时自动重连 | `fetcher.ts` | `fetch` 加 timeout，超时时自动调用 `fetchChatHistory` 获取已完成部分 |

**验收**：用户可以中止生成、看到 MCP 服务状态、网络闪断后自动恢复。

---

### Phase 5: 高级特性（优先度：🟢 低）

| # | 改动 | 文件 | 说明 |
|---|------|------|------|
| F5.1 | 长记忆事实面板 | `index.tsx` | 会话旁显示 `MemoryManager` 提取的长期事实列表（用户偏好标签云） |
| F5.2 | `fact_model` 前端配置 | `ChatInput.tsx` + `ApiKeyModal.tsx` | 在设置面板中允许选择 fact_extraction 模型 |
| F5.3 | 会话搜索 | `index.tsx` | 搜索历史会话标题/内容 |
| F5.4 | Markdown 代码块复制 | `index.tsx` | AI 回复的代码块加"一键复制"按钮（LobeHub 已有部分支持） |
| F5.5 | 消息重新生成 | `index.tsx` | 对已有 AI 回复提供"重新生成"按钮，复用同一 thread_id |

---

## 4. 文件变更总表

### 新增

```
frontend/src/
├── components/chat/
│   ├── ToolResult.tsx                    # Phase 3 — 工具结果差异化渲染
│   ├── ConnectionStatus.tsx             # Phase 4 — MCP 连接状态指示器
│   ├── ProgressPanel.tsx                # Phase 2 — 执行步骤进度面板
│   └── SessionSync.ts                   # Phase 1 — 会话同步逻辑（可内联到 index.tsx）
└── services/
    └── threadService.ts                 # Phase 1 — 线程 CRUD API 封装
```

### 修改

| 文件 | Phase | 变更 |
|------|-------|------|
| `components/chat/index.tsx` | 1-5 | +sessionId→thread_id 映射, +fetchChatHistory 接入, +DELETE 同步, +ProgressPanel, +AbortController |
| `lib/fetcher.ts` | 1,4 | +`fetchChatHistory` 接入 UI, +`deleteChatHistory`, +`listThreads`, +`AbortController` 支持, +timeout |
| `stores/useChatStore.ts` | 1 | +thread_id 字段, +`syncFromServer()` action |
| `services/client.ts` | 1 | +`DELETE /chat/history/{thread_id}` 方法 |

---

## 5. 执行顺序

```
Phase 1 (会话统一) ──→ Phase 2 (进度可视化) ──→ Phase 3 (工具 UI)
                                                    │
Phase 4 (连接层) ←───────────────────────────────────┘
                                                    │
Phase 5 (高级特性) ←─────────────────────────────────┘
```

**理由**：Phase 1 是任何其他改进的基础——没有 thread 同步，历史加载、进度恢复全无从谈起。Phase 2-3 可并行，Phase 4 依赖 MCP 抽象层（后端 M3/M4 已就绪）。

---

## 6. 风险

| 风险 | 缓解 |
|------|------|
| Session ↔ thread_id 映射出错导致对话混淆 | `session.id` 直接作为 `thread_id` 使用，不引入额外映射层 |
| 后端 thread 列表 API 不存在 | Phase 1 需先在 `agent.py` 新增 `GET /chat/threads` 端点 |
| 前端状态树复杂度增加 | 渐进式添加，每次只引入一个概念（thread→progress→tool-ui），不做大爆炸式重构 |
| `plan` / `completed_steps` 事件在纯 chat 场景不产生 | 前端对缺失事件做降级处理——不显示进度面板即为正常 |

---

## 7. 测试策略

| Phase | 测试类型 | 覆盖 |
|-------|---------|------|
| 1 | 手动 E2E | 创建→发消息→切出→切回→验证历史恢复；删除→验证 checkpoint 清理 |
| 2 | 手动 E2E | 触发多工具调用任务 → 验证进度条步骤数正确、工具耗时显示 |
| 3 | 组件测试 | `ToolResult` 各类型渲染 snapshot |
| 4 | 手动 E2E | 中止生成 → 验证 UI 恢复；断开 MCP → 验证红灯指示 |
| 5 | 组件测试 | Fact 面板渲染 |

> 前端测试不依赖 Python 环境，可直接用 `npm run test`（如项目配置了 jest/vitest）。

---

## 8. 交付检查清单

### Phase 1 — 会话生命周期统一

- [x] F1.1: `handleSend` 将 `sessionId` 作为 `thread_id` 传入后端 — 2026-05-20
- [x] F1.2: 切换会话时调用 `fetchChatHistory(thread_id)` 从服务器恢复消息 — 2026-05-20
- [x] F1.3: `deleteSession` 调用 `DELETE /chat/history/{thread_id}` 清理后端 checkpoint — 2026-05-20
- [x] F1.4: 后端新增 `GET /chat/threads` 端点，前端接入会话列表同步 — 2026-05-20

### Phase 2 — CodingAgentState 可视化

- [x] F2.1: 后端 `graph.py` 新增 `plan_update` SSE 事件 — 2026-05-20
- [x] F2.2: 后端 `graph.py` 新增 `progress` SSE 事件（`completed_steps` 变更推送） — 2026-05-20
- [x] F2.3: 前端 `ProgressPanel` 渲染步骤进度条（✓ 完成 / spinner 执行中） — 2026-05-20
- [x] F2.4: `tool_end` 事件提取 `duration_ms`，工具面板显示耗时 — 2026-05-20

### Phase 3 — 工具调用 UI 升级

- [x] F3.1: 新增 `ToolResult.tsx`，按 `tool_name` 分发渲染器 — 2026-05-20
- [x] F3.2: `ToolResult` 错误态 UI（network/not_found 区分 + 重试按钮） — 2026-05-20
- [x] F3.3: `search_anime_advanced` 结果渲染为 `MediaCard` 缩略图网格 — 2026-05-20
- [x] F3.4: 工具详情默认折叠，仅显示工具名 + 状态 + 耗时摘要 — 2026-05-20

### Phase 4 — 连接与传输层

- [x] F4.1: 后端 `agent.py` 新增 `connection_status` SSE 事件 — 2026-05-20
- [x] F4.2: 前端 `ConnectionStatus` 组件（绿/黄/红 状态灯） — 2026-05-20
- [x] F4.3: `chatWithBackend` 支持 `AbortController`；"停止生成"按钮 — 2026-05-20
- [x] F4.4: `fetch` 加 timeout（120s）+ 超时后自动取消 — 2026-05-20

### Phase 5 — 高级特性

- [x] F5.1: 长记忆事实面板（用户偏好标签云） — 2026-05-20
- [x] F5.2: `fact_model` 前端设置入口 — 2026-05-20
- [x] F5.3: 历史会话搜索 — 2026-05-20
- [x] F5.4: AI 回复代码块一键复制 — 2026-05-20
- [x] F5.5: 消息重新生成按钮（复用同一 `thread_id`） — 2026-05-20

### 全量回归

- [ ] Phase 1 完成: 创建→发送→切换→恢复 全流程无丢失
- [ ] Phase 2 完成: 多工具任务进度条正确、耗时显示准确
- [ ] Phase 3 完成: 搜番卡片正常渲染、工具失败可重试
- [ ] Phase 4 完成: 中止生成正常、MCP 状态灯正确
- [ ] Phase 5 完成: 事实面板 + 搜索 + 重新生成功能正常

---

## 9. 附录：Phase 1-5 交付后深度代码审查（2026-05-21）

> 前述 5 个 Phase 的功能层面均已完成交付，但一次全面的代码审查发现了一批 Plan 覆盖范围之外的结构性问题。
> 以下按严重程度分级，作为后续迭代的候选任务池。

---

### 9.1 🔴 P0 — 致命级回归缺陷

| # | 问题 | 文件 | 根因 |
|---|------|------|------|
| F6.1 | API 调用全部硬编码 `localhost:8000`，绕过 Next.js 代理 | `fetcher.ts:L87`, `L217`, `L226`, `L239`; `client.ts:L1` | `next.config.ts` 已配置 `rewrites` 将 `/api/*` 动态代理，但 `fetcher.ts` 和 `client.ts` 仍直连 `http://localhost:8000`。Docker/生产环境 API 请求全部走不通 |
| F6.2 | SearchBar 完全无视暗色模式 | `SearchBar.tsx:L131` | `border: '1px solid #e5e7eb'`, `backgroundColor: '#ffffff'` 硬编码白色，暗色主题下显示白底黑字 |
| F6.3 | 零自动化测试覆盖 | 全局 | `package.json` 无 `test` 命令，`**/*.test.*` / `**/*.spec.*` 文件数为 0，所有 Chat 正确性依赖人工回归 |

**修复方案：**

- **F6.1**：统一使用 `/api/v1/...` 相对路径，由 Next.js `rewrites` 代理。`fetcher.ts` 4 处 URL、`client.ts` 1 处 `BASE_URL` 全部替换
- **F6.2**：SearchBar 组件接入 `useAppTheme().isDarkMode`，面板背景/边框/文字色动态化
- **F6.3**：引入 vitest + @testing-library/react，先覆盖 `ToolResult.tsx` 的四类 renderer 和状态切换

---

### 9.2 🟡 P1 — 高危 Bug 与代码质量

| # | 问题 | 文件 | 根因 |
|---|------|------|------|
| F7.1 | `fetchChatHistory` 存在竞态条件 | `index.tsx:L68-82` | useEffect 缺少 `AbortController` cleanup。用户快速连切 5 个会话时，旧请求可能后到达并覆盖当前会话消息 |
| F7.2 | `handleSend` 与 `handleRegen` ~130 行重复代码 | `index.tsx:L127-247` vs `L332-467` | 两函数镜像复制了 AbortController、toolCallMap、chatWithBackend 全量回调，违背 DRY |
| F7.3 | Zustand Map 序列化脆弱，7 处防御性检查 | `index.tsx:L55-57` + `useChatStore.ts` 内部 | `typeof .get === 'function'` 防御性检查散布 7 处，localStorage 数据损坏即全崩 |
| F7.4 | 流式滚动抢占用户阅读上下文 | `index.tsx:L113-115` | 每个 `currentMessages` 引用变化（每个 stream chunk）都 scrollIntoView，用户向上翻阅历史时被强制拉回底部 |
| F7.5 | 缺少 typing indicator（首包延迟无反馈） | `index.tsx:L220-230` | 从 AI 消息插入（空 content）到首个 `message_chunk` 到达之间（3-10s），UI 显示空白 ChatItem |

**修复方案：**

- **F7.1**：useEffect 内创建 `AbortController`，cleanup 时调用 `abort()`，`fetchChatHistory` 接受 `signal` 参数
- **F7.2**：抽取 `useChatStreaming` hook，封装 `abortRef` / `toolCallMap` / `accumulatedContent` 及 `chatWithBackend` 所有回调，`handleSend` 和 `handleRegen` 均调用该 hook 的 `start()` 方法
- **F7.3**：将 `chatMessages` 从 `Map<string, Message[]>` 改为 plain `Record<string, Message[]>` + immer 不可变更新，消除序列化不确定性
- **F7.4**：在 `scrollIntoView` 前检测 `scrollTop + clientHeight >= scrollHeight - 150`，仅当用户在底部附近时自动滚动
- **F7.5**：AI 消息 `content` 为空时静默跳过渲染，改用独立的 `TypingIndicator` 组件（三点跳动的 `<Loader2>` 动画）

---

### 9.3 🟠 P2 — 中等级架构改进

| # | 问题 | 文件 | 根因 |
|---|------|------|------|
| F7.6 | ChatPage 单体组件 542 行，6 种职责混装 | `index.tsx` | 违反 SRP：会话管理 + 消息发送 + 流式处理 + 工具调用 + 重生成 + 中止全部耦合在一个文件 |
| F7.7 | 流式状态使用闭包变量，React DevTools 不可见 | `index.tsx:L211-212` | `toolCallMap` 和 `accumulatedContent` 定义为函数内 `let` 变量，无法在 DevTools 中检查，调试成本高 |
| F7.8 | `selectedModel` / `selectedProvider` / `selectedRole` 未持久化 | `index.tsx:L27-29` | 每次页面刷新回退到默认值 `gpt-3.5-turbo` / `preset-1`，应入 `useChatStore` 按会话存储 |
| F7.9 | 会话标题永远为"新会话"，无自动生成 | `useChatStore.ts:L61` | `updateSessionTitle` 存在但从未调用。缺少基于 LLM 首轮回复自动提取标题的机制 |
| F7.10 | 缺少 Error Boundary | 全局 | 任何子组件（ToolResult、ChatItem）throw 即导致整个 Chat 白屏 |

**修复方案：**

- **F7.6**：拆分为 `SessionPanel`（左栏）+ `MessageList`（消息列表 + 滚动）+ `useChatStreaming`（流式 hook）+ `ChatPage`（编排层 < 150 行）
- **F7.7**：将 `toolCallMap` 改为 React `useRef<Map<string, string>>`，`accumulatedContent` 改为 `useRef<string>`，可通过 DevTools 查看
- **F7.8**：在 `useChatStore` 中新增 `sessionConfigs: Record<string, { model, provider, role }>`
- **F7.9**：在 `handleSend` 的第一个 `message_chunk` 到达后，调用 LLM（轻量请求）生成 8 字以内标题，写入 `updateSessionTitle`
- **F7.10**：新增 `ChatErrorBoundary.tsx`，包裹 ChatPage，白屏时显示"会话出错，重新加载"fallback

---

### 9.4 🟢 P3 — 改善级 UX 打磨

| # | 问题 | 文件 |
|---|------|------|
| F7.11 | `TokenTag` 写死 `maxValue={5000} value={1000}` 假数据 | `ChatInput.tsx:L146` |
| F7.12 | Context 引用物品 pill 样式在两处重复实现 | `ChatInput.tsx:L101-120` + `index.tsx:L498-515` |
| F7.13 | 无消息时间分组分隔线（"今天"/"昨天"/"5月20日"） | `index.tsx` message list |
| F7.14 | 用户消息无法编辑和重发 | `index.tsx` |
| F7.15 | 大量 inline style `{{}}` 对象每帧重建，触发第三方组件不必要 re-render | 全局（`@lobehub/ui` / `antd` 子组件） |
| F7.16 | 停止生成按钮放在 ChatInput 下方中央，与正在生成的消息无视觉关联 | [ChatInput.tsx:L176-L185](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/components/chat/ChatInput.tsx#L176-L185) + [index.tsx:L443-L462](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/components/chat/index.tsx#L443-L462) |

**F7.16 修复方案：** 将 Stop 按钮从 ChatInput 下方移到**最后一条正在生成的 AI 消息的 action row**，与 Regen/Copy 共享同一位置，按状态切换：

```
streaming:  AI 消息 card → [Square ■ 停止]        ← loading && 是最后一条 AI 消息
done:       AI 消息 card → [RotateCcw 重新生成] [Copy]  ← 当前逻辑不变
```

具体改动：
- `ChatInput.tsx`：删除 `{loading && onStop && (...)}` 整个区块（L176-185），`onStop` prop 不再需要
- `index.tsx`：消息渲染中新增判断——`loading && msg.role === 'assistant' && msg === lastAssistantMessage` 时，在 `showRegen` 位置渲染 `<ActionIcon icon={Square} onClick={stopGeneration} />` 替代 Regen+Copy
- 从 `ChatInput` 移除 `onStop` prop，`stopGeneration` 改为直接在 `index.tsx` 内部消费

---

### 9.5 新增文件清单

```
frontend/src/
├── components/chat/
│   ├── SessionPanel.tsx               # F7.6 — 左栏会话列表面板
│   ├── MessageList.tsx                # F7.6 — 消息列表 + 智能滚动
│   ├── TypingIndicator.tsx            # F7.5 — 等待首包动画
│   ├── ChatErrorBoundary.tsx          # F7.10 — 全局容错边界
│   └── ContextPill.tsx                # F7.12 — Context 引用 pill 统一组件
├── hooks/
│   └── useChatStreaming.ts            # F7.2 — 流式发送 hook (合并 handleSend/handleRegen)
└── __tests__/
    └── components/chat/
        └── ToolResult.test.tsx         # F6.3 — 工具结果渲染测试
```

### 新增依赖

```json
{
  "devDependencies": {
    "vitest": "^3.x",
    "@testing-library/react": "^16.x",
    "@testing-library/jest-dom": "^6.x",
    "jsdom": "^25.x"
  }
}
```

---

### 9.6 执行顺序建议

```
F6.1 (API 代理修复, 5min)  ←── P0，阻塞生产部署
    │
    ├→ F6.2 (暗色模式, 15min)
    │
    └→ F6.3 (vitest 骨架, 30min)  ←── 为后续变更提供安全网
            │
            └→ F7.1 + F7.2 + F7.4 + F7.5 (流式体验一揽子, 3h)
                    │
                    └→ F7.6 (ChatPage 拆分, 2h)
                            │
                            └→ F7.3 + F7.7 + F7.8 + F7.10 (状态 & 容错, 2h)
                                    │
                                    └→ F7.9 + P3 各项 (UX 打磨, 1.5h)
```

**总预估改动量：~10h，零破坏性变更。**

---

### 9.7 交付检查清单（二期）

#### Round 2.1 — 基础设施修复

- [x] F6.1: `fetcher.ts` / `client.ts` 全部改用相对路径 `/api/v1/...`
- [x] F6.2: `SearchBar` 接入 `isDarkMode`，面板/边框/文字色动态化
- [x] F6.3: 引入 vitest，`ToolResult.test.tsx` 覆盖 4 类 renderer + 3 种状态

#### Round 2.2 — 流式体验重构

- [x] F7.1: `fetchChatHistory` useEffect 加 AbortController cleanup
- [x] F7.2: 抽取 `useChatStreaming` hook，消除 handleSend/handleRegen 重复
- [x] F7.4: 消息列表仅当用户在底部时自动 scroll
- [x] F7.5: 新增 `TypingIndicator`，首包等待时显示三点跳动动画
- [x] F7.7: `toolCallMap` / `accumulatedContent` 改用 `useRef`

#### Round 2.3 — 架构收敛

- [x] F7.3: `chatMessages` 从 `Map` 改为 plain `Record`，消除 7 处防御性检查
- [x] F7.6: ChatPage 拆分为 SessionPanel + MessageList + ChatPage
- [x] F7.8: `selectedModel/Provider/Role` 入 `useChatStore`，按会话持久化
- [x] F7.10: 新增 `ChatErrorBoundary` 包裹 ChatPage

#### Round 2.4 — UX 打磨

- [x] F7.9: 首轮回复后自动生成会话标题（取前 16 字）
- [x] F7.11: TokenTag 移除假数据
- [x] F7.12: 抽取 `ContextPill` 组件，ChatInput + message extra 共用
- [x] F7.13: 消息时间分组分隔线（今天/昨天/日期）
- [x] F7.14: 用户消息编辑/重发按钮
- [x] F7.16: 停止按钮移入最后一条 AI 消息 action row，替代 ChatInput 下方独立停止按钮

---

## 10. 附录：Round 3 — 思考过程可视化 + Bug 修复（2026-05-21）

### 10.1 🐛 Bug 修复

| # | 问题 | 根因 | 修复 |
|---|------|------|------|
| F8.1 | 首个会话删除按钮渲染失败 | `session.updatedAt` 经 localStorage 序列化后变为字符串，直接 `new Date().toLocaleString()` 在某些浏览器抛异常；ActionIcon 无 `flexShrink: 0` 包裹被容器挤压 | `SessionPanel.tsx` 日期防御性解析 + 删除按钮外层 `div` 确保不被裁剪 |

### 10.2 🧠 思考过程可视化

| # | 改动 | 文件 | 说明 |
|---|------|------|------|
| F8.2 | ToolCall 类型新增 `reason` 字段 | `useChatStore.ts` | `reason?: string` 记录工具调用目的 |
| F8.3 | `useChatStreaming` 生成工具理由 | `useChatStreaming.ts` | `TOOL_REASONS` 映射表，`onToolStart` 自动注入中文理由 |
| F8.4 | 新增 `ThinkingPanel` 思考面板 | `ThinkingPanel.tsx` | 可折叠面板：🧠 思考过程 标题 + 计划摘要 + 每个工具的"为什么"理由 + ToolResult 组件；生成中显示旋转动画 |
| F8.5 | MessageList 集成 ThinkingPanel | `MessageList.tsx` | 替换原来平铺的 toolCalls 列表为 ThinkingPanel 包裹 |

**ThinkingPanel 结构：**
```
┌─────────────────────────────────────┐
│ 🧠 正在思考... / 思考过程（3个调用） ▾ │  ← 可折叠
├─────────────────────────────────────┤
│ 计划：根据用户查询搜索匹配的动画...    │  ← plan 显示
│                                     │
│ 为什么：根据用户查询搜索匹配的动画作品  │  ← 工具理由
│ ┌─────────────────────────────────┐ │
│ │ ✓ 搜索动画  → [卡片网格]    1.5s│ │  ← ToolResult
│ └─────────────────────────────────┘ │
│                                     │
│ 为什么：获取动画详细信息...           │
│ ┌─────────────────────────────────┐ │
│ │ ✓ 动画详情  → [信息面板]   0.3s │ │
│ └─────────────────────────────────┘ │
└─────────────────────────────────────┘
```

### 10.3 新增文件

```
frontend/src/components/chat/
└── ThinkingPanel.tsx               # F8.4 — 思考过程可折叠面板
```

### 10.4 修改文件

| 文件 | 变更 |
|------|------|
| `stores/useChatStore.ts` | `ToolCall` 类型 + `reason?: string` |
| `hooks/useChatStreaming.ts` | 新增 `TOOL_REASONS` 映射 + `onToolStart` 注入 reason |
| `components/chat/MessageList.tsx` | toolCalls 列表 → ThinkingPanel 集成 |
| `components/chat/SessionPanel.tsx` | 日期防御性解析 + 删除按钮 anti-clip 修复 |

### 10.5 交付检查清单（Round 3）

- [x] F8.1: SessionPanel 删除按钮 + 日期渲染修复
- [x] F8.2: ToolCall `reason` 字段
- [x] F8.3: `useChatStreaming` 工具理由映射
- [x] F8.4: `ThinkingPanel` 思考过程面板
- [x] F8.5: MessageList 集成 ThinkingPanel

---

## 11. 附录：Round 4 — 思考与工具调用过程深度渲染（2026-05-21）

> 基于需求文档「包含"思考与工具调用过程"的 Chat 流式渲染前端组件」与现状的差距分析。
> G1 依赖后端新增 `reasoning_chunk` SSE 事件；G2-G6 纯前端可独立交付。

---

### 11.1 差距总表

| # | 需求 | 现状 | 严重度 |
|---|------|------|--------|
| G1 | 纯思考推理文本打字机流式渲染 | 后端无 `reasoning_chunk` 事件，前端无 `Message.reasoningText` 字段 | 🔴 致命 |
| G2 | 最终回答开始时 ThinkingPanel 自动折叠 | `useState(true)` 永为展开 | 🟡 高 |
| G3 | "思考"与"工具调用"两套视觉样式（图标+底色） | 统一 indigo 色，无分类 | 🟡 高 |
| G4 | 过程节点编号 "Step 1/3" | 无 | 🟠 中 |
| G5 | 折叠摘要 "✅ 已思考完毕 (2 Reasoning, 3 Tools)" | 只显示工具数 | 🟠 中 |
| G6 | ProgressPanel 的 plan 与 ThinkingPanel 重复 | plan 在两处渲染 | 🟠 中 |

---

### 11.2 改进方案

#### Round 4.1 — 推理文本引擎（G1）🔴 需后端配合

| # | 改动 | 文件 | 说明 |
|---|------|------|------|
| F9.1 | 后端新增 `reasoning_chunk` SSE 事件 | `agent.py` / `graph.py` | 模型在调用工具前/后的"内心独白"以 `event: reasoning_chunk\ndata: {"content": "..."}\n\n` 推送 |
| F9.2 | `fetcher.ts` 处理 `reasoning_chunk` | `fetcher.ts` | switch-case 新增 `reasoning_chunk` → `onReasoningChunk` |
| F9.3 | `Message` 模型新增字段 | `useChatStore.ts` | `reasoningText?: string` |
| F9.4 | `useChatStreaming` 推理回调 | `useChatStreaming.ts` | `onReasoningChunk` 追加到 `reasoningText`，通过 `updateMessage` 写入 store |
| F9.5 | ThinkingPanel 渲染推理文本 | `ThinkingPanel.tsx` | 以打字机风格行显示 `msg.reasoningText`（🟣 紫色系） |

#### Round 4.2 — 自动折叠 + 视觉区分（G2+G3）🟡 纯前端

| # | 改动 | 文件 | 说明 |
|---|------|------|------|
| F10.1 | finalAnswerStarted → auto-collapse | `ThinkingPanel.tsx` | 新增 `finalAnswerStarted` prop，`useEffect` 检测 true→false 转换时 `setExpanded(false)` |
| F10.2 | MessageList 传递 finalAnswerStarted | `MessageList.tsx` | 向 ThinkingPanel 传 `finalAnswerStarted={!!msg.content}` |
| F10.3 | 两套视觉样式 | `ThinkingPanel.tsx` | 将 toolCalls 列表改为 `processNodes[]` 混合列表；Thinking 节点 → 🧠 紫底紫边；Tool 节点 → 🔧 蓝底蓝边 |
| F10.4 | processNodes 数据转换 | `ThinkingPanel.tsx` | 内部 `useMemo`：`reasoningText` 有值时生成推理节点，`toolCalls` 每条生成工具节点 |

#### Round 4.3 — 细节打磨（G4+G5+G6）🟠 纯前端

| # | 改动 | 文件 | 说明 |
|---|------|------|------|
| F11.1 | 步骤编号 "Step 1/3" | `ThinkingPanel.tsx` | 每个 processNode 左侧 `{index + 1}` 灰色圆形序号 |
| F11.2 | 折叠摘要文案 | `ThinkingPanel.tsx` | "✅ 思考完毕 · {N} 步推理 · {M} 次工具调用" |
| F11.3 | plan 去重 | `MessageList.tsx` | 移除独立 `<ProgressPanel>`，plan 仅由 ThinkingPanel 内部渲染 |
| F11.4 | ProgressPanel 逐步废弃 | `ProgressPanel.tsx` | 保留组件但不再从 MessageList 调用，由 ThinkingPanel 内嵌进度 |

---

### 11.3 文件变更总表

| 操作 | 文件 | Round |
|------|------|-------|
| 修改 | `stores/useChatStore.ts` | 4.1: `Message.reasoningText` |
| 修改 | `lib/fetcher.ts` | 4.1: `reasoning_chunk` SSE case |
| 修改 | `hooks/useChatStreaming.ts` | 4.1: `onReasoningChunk` 回调 |
| **重写** | `components/chat/ThinkingPanel.tsx` | 4.1+4.2+4.3: 推理文本 + 自动折叠 + 两套样式 + 步骤编号 + 摘要 |
| 修改 | `components/chat/MessageList.tsx` | 4.2: `finalAnswerStarted` prop; 4.3: 移除独立 ProgressPanel |

---

### 11.4 执行顺序

```
Round 4.2（纯前端 — visual区分 + auto-collapse）
    │
    ├→ Round 4.3（纯前端 — polish）
    │
    └→ Round 4.1（需后端 reason_chunk 事件 — 先写前端代码，SSE 端点后端开发后即可启用）
```

---

### 11.5 交付检查清单（Round 4）

#### Round 4.1 — 推理文本引擎（待后端）

- [x] F9.1: 后端 `reasoning_chunk` SSE 事件（后端文档 — 前端代码已预埋，后端发送即启用）
- [x] F9.2: `fetcher.ts` 新增 `reasoning_chunk` case
- [x] F9.3: `Message` 模型 `reasoningText?: string`
- [x] F9.4: `useChatStreaming` 推理回调（reasoningTextRef + onReasoningChunk）
- [x] F9.5: ThinkingPanel 推理文本打字机渲染

#### Round 4.2 — 自动折叠 + 视觉区分

- [x] F10.1: `ThinkingPanel` 新增 `finalAnswerStarted` prop + useEffect auto-collapse
- [x] F10.2: `MessageList` 传递 `finalAnswerStarted={!!msg.content}`
- [x] F10.3: `processNodes[]` 混合列表 + BrainCircuit/🔧 两套样式
- [x] F10.4: `useMemo` 实现 reasoning→thinking node, toolCalls→tool node 转换

#### Round 4.3 — 细节打磨

- [x] F11.1: 每个 processNode 左侧步骤编号
- [x] F11.2: 折叠摘要 "✅ 思考完毕 · X 步推理 · Y 次工具"
- [x] F11.3: `MessageList` 移除独立 `<ProgressPanel>`
- [x] F11.4: plan 仅由 ThinkingPanel 渲染（内嵌进度线）

---

## 12. Round 5 — 流式渲染断裂根因分析（2026-05-21）

> 现象：发送消息后出现不可展开的"正在思考"转圈，思考结束后所有内容一口气展示。
> 根因：`isStreaming` / `isDone` / `isThinking` 三个布尔标志在 reasoning→tool→answer 三段式流中全部存在逻辑漏洞。

---

### 12.1 完整渲染链路追踪

```
后端 graph.py                         前端 MessageList / ThinkingPanel
─────────────────                     ─────────────────────────────
on_chat_model_stream                  ChatItem renders
  → reasoning_chunk ────────────────→ msg.reasoningText 追加 ✗ bug: isStreaming=false
  → reasoning_chunk ────────────────→ msg.reasoningText 追加
  ...
on_chat_model_end
  → plan_update ────────────────────→ plan 更新
on_tool_start
  → tool_start ─────────────────────→ toolCall {status:'running'}
on_tool_end
  → tool_end ───────────────────────→ toolCall {status:'success'}
  → progress ───────────────────────→ progressSteps
on_chat_model_stream
  → message_chunk ──────────────────→ msg.content 追加 ✓ isStreaming=true 但 auto-collapse 触发
  ...
```

### 12.2 三个致命 Bug

#### Bug A：`isStreaming` 要求 `!!msg.content` → reasoning 阶段永远为 false

**文件**：[MessageList.tsx:L56](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/components/chat/MessageList.tsx#L56)

```typescript
// 当前（错误）
const isStreaming = loading && isLast && msg.role === 'assistant' && !!msg.content;

// 正确：移除 !!msg.content
const isStreaming = loading && isLast && msg.role === 'assistant';
```

**影响链**：
```
isStreaming=false → ThinkingPanel.isThinking = hasRunning && false = false
                 → 工具执行期间无 "🔄 正在思考" 状态
                 → 无法区分"正在工作"和"已完成"
```

#### Bug B：`isDone` 在纯 reasoning 阶段误报完成

**文件**：[ThinkingPanel.tsx:L77](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/components/chat/ThinkingPanel.tsx#L77)

```typescript
// 当前（错误）
const isDone = !hasRunning && processNodes.length > 0;

// 正确：reasoning 还在进行时不应当作 done
const isReasoningActive = !!reasoningText && !finalAnswerStarted && (hasRunning || isStreaming);
const isDone = !hasRunning && processNodes.length > 0 && !isReasoningActive;
```

**时序演示**：
```
reasoning_chunk #1 到达:
  hasRunning = false (无 tool)
  processNodes.length = 1 (reasoning node)
  isDone = true  ← 误报！UI 显示 "✅ 思考完毕"
  实际：推理还在流式到达中
```

#### Bug C：`isThinking` 在工具执行阶段为 false

**文件**：[ThinkingPanel.tsx:L72](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/components/chat/ThinkingPanel.tsx#L72)

```typescript
// 当前（错误）
const isThinking = hasRunning && isStreaming;

// 正确：过程未完成就是 thinking 状态
const isThinking = (hasRunning || !!reasoningText) && !finalAnswerStarted && isStreaming;
```

**Bug A 导致 isStreaming=false 时，Bug C 的 hasRunning 也无法挽救**。两 bug 叠加后效果：永远看不到 "🔄 正在思考"。

#### Bug D（连锁）：auto-collapse 在用户手动打开时强制关闭

推理结束后 `finalAnswerStarted` 首次变为 true → `useEffect` 强制 `setExpanded(false)`。如果用户在工具执行期间手动展开了面板，会被立即关闭。

---

### 12.3 修复方案

| # | 文件 | 改动 |
|---|------|------|
| F12.1 | `MessageList.tsx:L56` | `isStreaming` 移除 `!!msg.content` 条件 |
| F12.2 | `ThinkingPanel.tsx:L72` | `isThinking` 改为 `(hasRunning \|\| !!reasoningText) && !finalAnswerStarted && isStreaming` |
| F12.3 | `ThinkingPanel.tsx:L77` | `isDone` 改为 `!hasRunning && processNodes.length > 0 && (finalAnswerStarted \|\| !isStreaming)` |
| F12.4 | `ThinkingPanel.tsx:L44-48` | auto-collapse 仅在 `expanded=true` 且用户未手动取消时触发（新增 `userCollapsed` ref） |

### 12.4 交付检查清单（Round 5）

- [x] F12.1: `isStreaming` 移除 `!!msg.content`
- [x] F12.2: `isThinking` 覆盖 reasoning 阶段
- [x] F12.3: `isDone` 在 reasoning active 时不误报
- [x] F12.4: auto-collapse 不抢占用户手动展开
