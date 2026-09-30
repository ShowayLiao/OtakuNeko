# Chat Agent 交互修复实施计划

> 面向 AI 代理的工作者：使用 `executing-plans` 或 `subagent-driven-development` 执行本计划。每完成一个阶段，先运行该阶段验证命令，再审查完整 diff。

## 目标

将当前前端从“流式消息 + 过程列表”升级为可控、可恢复、可解释但不暴露原始 CoT 的 Agent Chat：

- live SSE 和 EventStore replay 进入同一个 Runtime Event normalizer/reducer；
- 用户可以看到并处理 queued、running、paused、recovering、completed、failed、cancelled、timeout；
- 审批、取消、断线恢复和拒绝结果都有明确的 UI 操作；
- Capability、Route、Subagent、Artifact 和 provenance 有不同的展示语义；
- 默认不展示 `thinking_chunk` 原始推理内容、raw provider payload 或未界定大小的工具结果；
- 兼容旧事件别名，避免已有会话和历史数据无法重放。

## 当前事实与边界

- 当前工作区为 `feature-harness`，HEAD 为 `bb8df1b`；已有用户未跟踪文件 `docs/superpowers/plans/2026-08-08-remove-langgraph-compatibility.md`，本计划不修改该文件。
- 当前没有明确批准的活动 Harness Batch；本计划不创建 `docs/harness-execution/BATCH-XX-execution.md`，实施时需要先获得 Batch 或普通前端任务归属。
- 前端已有终态归一化、sequence 去重、SSE replay、取消请求和 bounded tool output；不要重复实现这些能力。
- 后端已经存在 `approval_required`、`run.paused`、`/chat/resume`、`route_decision`、`agent_result`、`RunResult.artifacts` 和 `InvocationResult.provenance` 契约，但前端尚未形成完整展示路径。
- 后端 `GET /chat/history` 当前只返回 `role/content`，会丢失 `run_id`、sequence、过程和审批状态。跨刷新完整恢复必须先扩展服务端 projection，不能由前端从普通消息文本猜测。

## 设计决策

### 1. 单一事件管线

```text
SSE live / EventStore replay
        → RuntimeEventNormalizer
        → reduceRunView(event)
        → Message / Invocation / Artifact projection
        → Chat renderer
```

`fetcher.ts` 只负责传输、解析和恢复游标；`useChatStreaming.ts` 负责订阅和生命周期；纯 reducer 负责状态归约；组件只消费已安全化的 view model。

### 2. 运行状态与展示状态分离

扩展 `RunView`，但保留现有 `phase`、`terminalStatus` 和兼容字段：

```ts
type RunLifecycle =
  | 'queued' | 'running' | 'paused' | 'recovering'
  | 'completed' | 'failed' | 'cancelled' | 'timeout'
  | 'attention_required';

interface ApprovalView {
  approvalId: string;
  invocationId: string;
  capability: string;
  capabilityVersion?: string;
  argumentKeys: string[];
  state: 'pending' | 'approving' | 'rejecting' | 'resolved' | 'failed';
}
```

前端只保存可重建的 projection；`run_id`、terminal event 和 owner scope 仍由后端事实源决定。

### 3. 默认展示安全进度，不展示原始 CoT

`thinking_chunk` 不再进入普通 `ProcessNode.details`。默认只显示“正在分析需求”“正在调用搜索能力”“正在整理结果”等阶段摘要；如果未来保留 reasoning trace，必须作为明确的、受策略控制的独立入口，不能混入普通聊天时间线。

### 4. Tool 重试不直接从浏览器执行

当前 `ProcessStepItem` 有重试入口，但没有安全的重试 API、幂等键和 `retryable` 契约。第一阶段先移除或隐藏不可执行的 Tool Retry；只有后端明确返回 `retryable`、幂等语义和新的 invocation 关联后，才增加受控的“重试此调用”。普通用户操作使用“重新生成整轮”。

## 文件边界

### 允许新建

- `frontend/src/lib/chatRuntimeEvents.ts`
- `frontend/src/lib/chatRuntimeEvents.test.ts`
- `frontend/src/components/chat/RunStatusBar.tsx`
- `frontend/src/components/chat/ApprovalRequestCard.tsx`
- `frontend/src/components/chat/RecoveryCard.tsx`
- `frontend/src/components/chat/RouteDecisionCard.tsx`
- `frontend/src/components/chat/ArtifactCard.tsx`
- 对应的 `frontend/src/__tests__/components/chat/*.test.tsx`

### 允许修改

- `frontend/src/lib/fetcher.ts`
- `frontend/src/lib/fetcher.test.ts`
- `frontend/src/hooks/useChatStreaming.ts`
- `frontend/src/stores/useChatStore.ts`
- `frontend/src/components/chat/AgentMessageRenderer.tsx`
- `frontend/src/components/chat/ProcessContainer.tsx`
- `frontend/src/components/chat/ProcessStepItem.tsx`
- `frontend/src/components/chat/MessageList.tsx`
- `frontend/src/components/chat/ChatInput.tsx`
- `frontend/src/components/chat/ConnectionStatus.tsx`
- `frontend/src/components/chat/index.tsx`

### 本计划禁止修改

- Runtime、Dispatcher、Capability、MCP、Memory 和数据库实现；
- Provider、Secret、JWT、BYOK 和 raw provider payload；
- 与 Chat Runtime 契约无关的业务页面和依赖；
- 现有失败测试、兼容事件解析和已持久化 Run/Event 数据。

## 阶段 0：基线与契约确认

### 目标

锁定当前源码事实和事件 fixture，避免把旧的 `15-chat-rendering-audit.md` 结论当作当前实现。

### 任务

- [ ] 记录 `git status --short`、分支、HEAD 和已有用户修改。
- [ ] 从 `backend/app/harness/runtime.py`、`backend/app/api/v1/agent.py` 和 `backend/app/harness/contracts.py` 导出实际事件字段：终态、审批、路由、Subagent、Invocation、artifact、provenance、usage。
- [ ] 为 primary 事件建立安全 fixture，禁止写入 Secret、完整 Prompt、原始 provider payload 和完整 CoT。
- [ ] 明确历史恢复契约：如果 `/chat/history` 仍只有 `role/content`，创建独立后端前置任务，要求返回 `run_id`、`last_sequence`、生命周期状态和可恢复标识。

### 验收

- 事件表能逐项映射到 normalizer 类型；未知事件有保留但不改变核心状态的行为。
- 明确 live、replay、refresh 三条路径的输入差异。
- 未把目标架构或计划状态写成已实现状态。

## 阶段 1：Runtime Event normalizer 与 RunView reducer

### 目标

让 live 和 replay 共享同一个归约逻辑，并补齐 paused、approval、route、agent_result 和 artifact 的类型边界。

### 文件

- 新建 `frontend/src/lib/chatRuntimeEvents.ts` 和测试。
- 修改 `frontend/src/lib/fetcher.ts`、`frontend/src/lib/fetcher.test.ts`。
- 修改 `frontend/src/stores/useChatStore.ts`，仅扩展安全 projection 类型，不改变 localStorage 为事实源。

### 实施步骤

- [ ] 定义 `RuntimeEvent` discriminated union，覆盖 `thinking_start/end`、`model_call`、`model_decision`、`tool_call_start/end`、`message_*`、`approval_required`、`route_decision`、`agent_result`、所有终态和 canonical replay 别名。
- [ ] 将事件名、终态、Invocation status、timeout marker 和 approval 状态归一化为单一函数。
- [ ] 以 `sequence` 做单调游标和去重；重复、倒序和无效序列不能重复追加内容或 Invocation。
- [ ] 将 `model_call` 的 usage、provider、raw payload 保留在内部诊断 projection 或丢弃，不进入普通消息内容。
- [ ] 将 tool output 转成 bounded safe output，并携带 `provenance/trust/redacted` 标记。
- [ ] 让 `fetcher.ts` 对 live 和 replay 都调用同一个 normalizer/reducer，不再分别维护两套字段兼容逻辑。

### 测试

- [ ] 正常回答、单 Tool、多 Tool。
- [ ] denied、failed、cancelled、timeout、budget_exceeded。
- [ ] `approval_required` / `run.paused` 和 canonical replay。
- [ ] `route_decision`、`agent_result`、artifact 和 provenance。
- [ ] 重复 sequence、倒序 sequence、未知事件、没有终态的 EOF。
- [ ] live/replay 相同事件序列产生相同 `RunView` 和 message projection。

## 阶段 2：运行控制与审批交互

### 目标

把 Agent 的生命周期变成用户可理解、可操作的状态机。

### 文件

- 新建 `RunStatusBar.tsx`、`ApprovalRequestCard.tsx`、`RecoveryCard.tsx` 及测试。
- 修改 `useChatStreaming.ts`、`fetcher.ts`、`AgentMessageRenderer.tsx`、`FinalAnswerBlock.tsx`、`MessageList.tsx`、`index.tsx`。

### 实施步骤

- [ ] `RunStatusBar` 显示当前阶段、连接状态、耗时和“取消中”状态；取消请求后只显示等待，直到收到最终 `run_cancelled`。
- [ ] `ApprovalRequestCard` 仅展示后端提供的 capability、version、argument keys、风险和 approval id，不接受模型传入的 user/tenant/scope。
- [ ] 增加 `approveRun` / `rejectRun` 请求，调用现有 `/api/v1/chat/resume`，携带当前 thread、provider endpoint 和认证上下文。
- [ ] 审批成功后继续 replay；拒绝后等待 Runtime 的终态，不在浏览器本地伪造 completed/failed。
- [ ] `RecoveryCard` 提供继续 replay、查看 Run 状态和放弃/关闭展示的明确动作；unknown EOF 不自动标记成功。
- [ ] `FinalAnswerBlock` 保留 partial answer，并根据 terminal code 显示安全、可行动的错误摘要。
- [ ] 将当前 `ConnectionStatus` 的 “MCP” 改为“运行流连接”或更准确的传输状态。

### 测试

- [ ] Approval approve、reject、重复点击、请求失败。
- [ ] cancel request 与最终 cancelled event 的时序。
- [ ] durable disconnect、replay 成功、replay 失败、Run abandoned。
- [ ] partial answer 在 failed/cancelled/timeout/recovering 下均保留。
- [ ] 键盘操作、焦点、`aria-live` 和 `aria-busy` 状态。

## 阶段 3：Invocation、Route、Artifact 和证据展示

### 目标

让用户看到 Agent 做了什么、结果来自哪里、哪些内容仍不可信，而不是把所有事件都塞进一个 Process 列表。

### 文件

- 新建 `RouteDecisionCard.tsx`、`ArtifactCard.tsx` 及测试。
- 修改 `ProcessContainer.tsx`、`ProcessStepItem.tsx`、`AgentMessageRenderer.tsx`、`MessageList.tsx`、`useChatStore.ts`。

### 实施步骤

- [ ] 保留 `ProcessStepItem` 作为 Invocation 的兼容渲染器，明确显示 capability、版本、status、duration、safe output 和 error code。
- [ ] Route/Agent Result 单独渲染，显示 selected agent、阶段结果和有限 provenance；不把 Subagent 当作普通 Tool。
- [ ] Artifact 使用引用、类型、标题、大小、来源和安全预览；大结果不直接塞入聊天气泡。
- [ ] 增加 `Evidence/Citation` 展示入口；来源链接必须经过后端允许的安全 projection，不直接拼接不可信 URL。
- [ ] 处理 `onRetryTool`：在没有 retryable/idempotency 契约前隐藏该按钮，避免浏览器直接重放副作用。
- [ ] 删除或整合当前未接入主路径的 `ProgressPanel`、`TypingIndicator` 和重复 `ToolCall` 类型。

### 测试

- [ ] Invocation 各状态、错误码、耗时和 bounded output。
- [ ] Route、Subagent、Artifact、provenance 的展开/折叠。
- [ ] 不渲染 raw provider payload、Secret、完整 Prompt、原始 CoT。
- [ ] 大结果、循环引用、恶意 HTML/URL 和未知 artifact 类型。

## 阶段 4：持久化恢复、会话和体验收口

### 目标

让刷新、切换会话和长对话不会破坏 Agent Run 语义，并清理现有交互债务。

### 文件

- 前端仍限于本计划文件边界；历史 projection 若需后端修改，另立契约任务。
- 重点修改 `index.tsx`、`useChatStore.ts`、`SessionPanel.tsx`、`MessageList.tsx`、`ChatInput.tsx` 和相关测试。

### 实施步骤

- [ ] 页面刷新时先读取 Run projection，再从 `last_sequence` replay；不要仅凭 localStorage 的 message status 判断完成。
- [ ] 若服务端历史仍只返回 role/content，暂时保留明确的“无法恢复过程”状态，并阻止前端伪造 Run 状态；服务端扩展完成后再接入完整历史 projection。
- [ ] 会话列表显示 active run、等待审批、失败待处理和最近更新时间。
- [ ] `ContextPill` 改为可访问按钮，支持键盘聚焦、删除和来源说明；上下文发送使用结构化字段，避免直接拼接未经转义的 XML 文本。
- [ ] 将重新生成、编辑、复制、反馈和分支操作统一成 `MessageActions`，避免每个消息组件自行维护动作语义。
- [ ] 长会话增加消息窗口化或分页策略；流式更新继续使用 RAF batching，但不得绕过 reducer。

### 测试

- [ ] 刷新恢复、切换会话、匿名 Run、owner scope 错误。
- [ ] 长列表滚动、流式自动滚动和用户主动上滑后的行为。
- [ ] context item 去重、删除、键盘操作和不可信字段显示。
- [ ] 移动端布局、暗色模式、减少动画和屏幕阅读器。

## 验收命令

从仓库根目录运行：

```powershell
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend test
pnpm --dir frontend build
git diff --check
```

每条命令必须记录真实退出码、通过/失败数量和未运行原因。当前环境曾因 PowerShell/pnpm 对 `E:\HACCI\Documents` 返回 `EPERM`，若仍存在，必须记录为环境阻塞，不能写成测试失败或测试通过。

## 完成标准

- [ ] 所有 primary terminal event 和 canonical replay alias 都能产生唯一稳定状态。
- [ ] Approval、cancel、timeout、disconnect/replay 和 unknown EOF 均有确定 UI 行为。
- [ ] live/replay/refresh 不会重复追加消息、Invocation 或副作用。
- [ ] 默认 UI 不展示原始 CoT、Secret、raw provider payload 和无界工具输出。
- [ ] Artifact、Route、Subagent、Invocation 和普通回答具有不同展示语义。
- [ ] Tool Retry 只有在 retryable + idempotency 契约存在时才可用。
- [ ] 相关组件、reducer、协议和真实入口测试均通过；完整 diff Review verdict 为 `pass`。
- [ ] 回滚时可保留旧 alias 和旧 renderer，且不删除 Run/Event/Invocation 数据。

## 建议提交拆分

未经用户明确授权不执行 commit。获得授权后建议按以下粒度提交：

1. `test(chat): add runtime event reducer fixtures`
2. `feat(chat): normalize run lifecycle and approval projection`
3. `feat(chat): add invocation route and artifact views`
4. `feat(chat): restore durable runs and polish chat controls`

每个提交都必须只包含对应阶段的文件，并在提交前运行 `git status --short`、`git diff --check`、`git diff --stat` 和完整 diff 审查。
