# TASK-CHAT-RENDERING-002：Capability Invocation 过程投影与安全展示

## 目标

将 Runtime 的 `model_decision`、`tool_call_start`、`tool_call_end` 归约为稳定的 `ProcessNode`，让 chat 页面正确显示 Capability 名称、执行状态、错误和 bounded safe output。

## 依赖

- `TASK-CHAT-RENDERING-001` 已通过测试和 Review。
- 前端已能识别 primary/live/replay 的 terminal event。

## 允许修改

- `frontend/src/lib/fetcher.ts`
- `frontend/src/hooks/useChatStreaming.ts`
- `frontend/src/stores/useChatStore.ts`
- `frontend/src/components/chat/AgentMessageRenderer.tsx`
- `frontend/src/components/chat/MessageList.tsx`
- `frontend/src/components/chat/ProcessContainer.tsx`
- `frontend/src/components/chat/ProcessStepItem.tsx`
- `frontend/src/__tests__/components/chat/`
- `frontend/src/lib/*.test.ts`
- 对应 execution record 和审计链接

## 禁止修改

- 不把完整 Decision arguments、数据库字段、用户身份或 provider payload 放进 UI。
- 不把 `capability` 直接当作可执行的前端动作或重试 API 参数。
- 不将 `succeeded` 直接强制转换成 `success` 而不经过明确映射。
- 不展示 Chain-of-Thought；thinking 节点只显示安全阶段提示或经批准的摘要。

## TDD 契约

实现前先增加失败测试，至少覆盖：

1. `tool_call_start` 使用 `invocation_id` 创建节点，`capability` 成为安全标题。
2. `argument_keys` 只作为有限参数键摘要显示，不要求后端提供完整输入。
3. `tool_call_end` 使用同一个 `invocation_id` 更新节点，不创建重复工具节点。
4. `succeeded`、`failed`、`denied`、`cancelled`、`timeout` 都映射到明确的 UI 状态。
5. tool event 重放或乱序到达时不会覆盖已确认的终态，也不会重复追加 output。
6. safe output、超长字符串、循环对象和未知 output 类型不会让组件崩溃或无限扩张。

## 实现要求

- 以 `invocation_id` 为唯一关联键；不能依赖 capability 名称匹配 pending node。
- `model_decision` 只更新 phase/intent；真正的过程节点由 `tool_call_start` 创建。
- 后端当前 primary `tool_call_end` 不保证 `duration_ms`，前端必须把 duration 视为可选，不能伪造耗时。
- details 使用 `argument_keys` 或安全摘要；output 仅使用后端 safe output，并执行字段/长度上限。
- UI 对外部数据增加 untrusted 或来源提示；不得把 output 作为系统指令或可信事实。

## 验收

- ordinary response、单工具、多工具、工具 denied、工具 timeout 和工具失败均能显示正确过程。
- ProcessNode 顺序与 Runtime sequence/Invocation 关联一致。
- 工具完成后不会继续显示 pending；回答开始后仍能查看已完成过程。
- 无原始 provider payload、Secret、完整 prompt 或 CoT 进入可见 UI、日志或测试 fixture。
- 相关组件测试、前端 lint/typecheck/test/build 和 `git diff --check` 有真实退出码。
- 完整 diff Review verdict 为 `pass`。

## 回滚

按组件级 projection flag 回滚到旧 ProcessNode renderer；保留 primary event normalizer 和已持久化 Invocation，不恢复直接执行能力。
