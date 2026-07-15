# Chat 流式渲染阻塞诊断报告：「正在思考」遮蔽输出内容

> **日期**: 2026-06-02  
> **审查范围**: `frontend/src/components/chat/`, `frontend/src/hooks/useChatStreaming.ts`, `frontend/src/stores/useChatStore.ts`  
> **问题摘要**: 发送请求后，后端流式输出的全部内容被隐藏在「正在思考」标签下方，用户无法展开查看，直至输出完全结束才可见。

---

## 问题现象

1. 用户发送消息后，`ProcessContainer` 显示"正在思考..."（或"正在调用工具..."）。
2. 后端流式输出的实际内容（`message_chunk` / `thinking_chunk`）**在输出结束前完全不可见**。
3. 用户点击"正在思考"区域期望展开查看内容，但**点击无效**，无法展开。
4. 直到 `onComplete` 触发、`loading` 变为 `false` 后，内容才一次性渲染出来。

---

## 根因分析

三个独立缺陷叠加，导致上述现象：

---

### 根因 1（主因）：`ProcessStepItem` 禁止展开 `pending` 状态的节点

**文件**: [ProcessStepItem.tsx](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/components/chat/ProcessStepItem.tsx#L31-L44)

```tsx
const isPending = node.status === 'pending';

// 第 44 行 — 点击处理器
onClick={() => !isPending && hasBody && setExpanded(!expanded)}

// 第 42 行 — CSS cursor
cursor: isPending || !hasBody ? 'default' : 'pointer',
```

**逻辑缺陷**:
- 当 `node.status === 'pending'` 时，`isPending` 为 `true`。
- `!isPending` 为 `false` → 点击执行 `setExpanded(!expanded)` 的短路条件阻止了展开。
- `cursor` 变为 `default`（非手型），视觉上暗示不可点击。

**影响链路**:
1. 后端发送 `thinking_chunk` → `onThinkingChunk` 被触发。
2. 在 [useChatStreaming.ts](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/hooks/useChatStreaming.ts#L145-L168) 中，`addProcessNode` 创建的 thought 节点状态为 `'pending'`，`updateLastProcessNode` 将 chunk 追加到 `details` 字段。
3. `ProcessStepItem` 渲染该节点时，`isPending = true` → **用户无法点击展开**查看累积的思考内容。
4. 直到 `thinking_end` 触发 → `onThinkingEnd` 将状态改为 `'success'` → 此时节点才可展开，但思考阶段已结束，后续内容已切换到 `message_chunk` 流。

**结果**: 整个思考阶段的流式内容对用户完全不可见。

---

### 根因 2（次因）：`FinalAnswerBlock` 在 `!hasContent` 时无条件返回 `null`

**文件**: [FinalAnswerBlock.tsx](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/components/chat/FinalAnswerBlock.tsx#L12-L13)

```tsx
if (!hasContent && !isStreaming) return null;
if (!hasContent && isStreaming) return null;
```

等效于：
```tsx
if (!hasContent) return null;
```

**逻辑缺陷**:
- 不管 `isStreaming` 是 `true` 还是 `false`，只要 `hasContent` 为假，组件就返回 `null`。
- `hasContent` 来自 [MessageList.tsx](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/components/chat/MessageList.tsx#L90-L91)：`hasContent={!!msg.content}`。
- 在 `message_chunk` 首次到达之前，`msg.content` 为空字符串 `''`，`!!'' === false`。

**影响链路**:
1. 当 LLM 先进行思考（`thinking_start → thinking_chunk → thinking_end`），再输出正式回答（`message_start → message_chunk`）时，整个思考阶段 `msg.content` 保持为空字符串。
2. `FinalAnswerBlock` 返回 `null`，包括其中的停止按钮也被隐藏。
3. 即使用户在 `ProcessContainer` 中看到了思考步骤的标题（如"推理"、"搜索动画"），也无法在步骤下方看到任何正式回答内容 —— 因为 `FinalAnswerBlock` 根本没有渲染。

> 注：该组件未使用 `isStreaming` 参数做任何差异化渲染，该参数形同虚设。

---

### 根因 3（加剧因素）：`ProcessContainer` 在流式开始时的视觉占位

**文件**: [ProcessContainer.tsx](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/components/chat/ProcessContainer.tsx#L78-L82)

```tsx
useEffect(() => {
    if (!prevStreamingRef.current && isStreaming && !userToggledRef.current) {
      setExpanded(true);
    }
```

**行为**:
- 流式开始时，`ProcessContainer` 自动展开。
- 摘要文本显示"正在思考..."（或"正在调用工具..."）+ 步骤计数。
- 结合根因 1，页面唯一可见的 UI 元素是"正在思考..."标题 + 若干步骤条目，**所有条目均不可展开**。

**用户感受**: 所有内容都被"正在思考"这个不可交互的 UI 吃掉了。

---

## 数据流完整追踪

```
后端 SSE Event                Frontend Hook                   Store               UI 渲染
─────────────────────────────────────────────────────────────────────────────────────────
thinking_start          →     onThinkingStart()
                               ├─ addProcessNode({status:'pending'})
                               └─ updateNow() ─────────→  msg.processes = [thought] ──→ ProcessContainer 显示"正在思考..."
                                                                                         ProcessStepItem: isPending=true → 不可展开

thinking_chunk          →     onThinkingChunk(chunk)
                               ├─ updateLastProcessNode({details: prev+chunk})
                               └─ scheduleUpdate() ─────→  msg.processes[0].details += chunk
                                                                                         ProcessStepItem: 内容累积但 isPending → 不可见

message_start           →     onMessageStart()
                               ├─ processesRef 标记 thought 为 success
                               └─ ⚠️ 未调用 updateNow/scheduleUpdate → 状态未刷入 Store

message_chunk           →     onMessageChunk(chunk)
                               ├─ accumulatedContentRef += chunk
                               ├─ pendingContentRef = accumulated
                               └─ scheduleUpdate() ─────→  msg.content = "accumulated..."
                                                                                         hasContent = true
                                                                                         FinalAnswerBlock 开始渲染
                                                                                         ⚠️ 但在此之前，所有内容对用户不可见

onComplete              →     onComplete()
                               └─ updateNow() + setLoading(false)
                                                                                         loading=false → isStreaming=false
                                                                                         ProcessContainer 自动折叠
```

**关键时间窗口**: 从 `thinking_start` 到第一个 `message_chunk` 到达之间，所有流式输出对用户**完全不可见**。

---

## 解决方案

### 方案 A：最小侵入修复（推荐）

只需修改两个文件，三处代码：

#### A1. `ProcessStepItem.tsx` — 允许展开 `pending` 节点

```diff
- onClick={() => !isPending && hasBody && setExpanded(!expanded)}
+ onClick={() => hasBody && setExpanded(!expanded)}

- cursor: isPending || !hasBody ? 'default' : 'pointer',
+ cursor: !hasBody ? 'default' : 'pointer',
```

**效果**: 用户在思考进行中即可点击步骤条目，实时查看已累积的思考内容。

#### A2. `FinalAnswerBlock.tsx` — 删除阻塞逻辑

`FinalAnswerBlock` 组件目前的逻辑等价于 `if (!hasContent) return null`，且 `isStreaming` 参数未使用。直接将此组件移除，让其 children 始终渲染：

```diff
- export default function FinalAnswerBlock({ isStreaming, hasContent, children }: FinalAnswerBlockProps) {
-   if (!hasContent && !isStreaming) return null;
-   if (!hasContent && isStreaming) return null;
-   return <div className="w-full">{children}</div>;
- }
+ export default function FinalAnswerBlock({ children }: FinalAnswerBlockProps) {
+   return <div className="w-full">{children}</div>;
+ }
```

或者：在 `AgentMessageRenderer` 中移除 `FinalAnswerBlock` 包裹，直接将 children 放在 `<div className="w-full">` 中。

**效果**: 即使 `msg.content` 为空，停止按钮等其他 UI 元素也能渲染。

#### A3. `MessageList.tsx` — 允许 streaming 时渲染空内容占位

```diff
- {msg.content && defaultMessageNode}
+ {(msg.content || isStreaming) && defaultMessageNode}
```

或者在 content 为空时提供占位内容：
```diff
- {msg.content && defaultMessageNode}
+ {msg.content ? defaultMessageNode : (isStreaming ? <TypingIndicator /> : null)}
```

**效果**: 流式期间即使消息内容尚未填充，也会显示打字指示器，给用户明确的"正在生成"反馈。

---

### 方案 B：激进简化（若完全不需要"正在思考"面板）

如果产品决策是"取消正在思考面板，后端流式输出直接即时渲染"：

1. 在 [AgentMessageRenderer.tsx](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/components/chat/AgentMessageRenderer.tsx#L45-L61) 中移除 `<ProcessContainer>` 的渲染（或通过 prop 控制是否显示）。
2. 执行方案 A 的 A2 + A3 修改。
3. 保留 `ProcessContainer` 组件代码不变（以备将来按需启用），通过一个开关控制其显隐。

---

## 受影响文件清单

| 文件 | 角色 | 修改必要性 |
|------|------|-----------|
| [ProcessStepItem.tsx](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/components/chat/ProcessStepItem.tsx) | 主因 — 禁止展开 pending 节点 | **必须修改** |
| [FinalAnswerBlock.tsx](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/components/chat/FinalAnswerBlock.tsx) | 次因 — 阻塞渲染 | **必须修改** |
| [MessageList.tsx](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/components/chat/MessageList.tsx#L90-L91) | 连带 — content 空时不渲染子节点 | **建议修改** |
| [AgentMessageRenderer.tsx](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/components/chat/AgentMessageRenderer.tsx) | 入口组件 | 可选（移除 FinalAnswerBlock 包裹） |
| [ProcessContainer.tsx](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/components/chat/ProcessContainer.tsx) | 加剧因素 — 自动展开 | 可选修改 |
| [useChatStreaming.ts](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/hooks/useChatStreaming.ts) | `onMessageStart` 未刷 Store | 建议修复 |

---

## 测试策略

按「后端镜像原则」：

1. **单元测试** — `tests/hooks/test_useChatStreaming.py`（Python 端模拟 SSE 事件流，验证状态转换）
2. **组件测试** — 前端 `ProcessStepItem.test.tsx`（与 [ProcessStepItem.tsx](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/components/chat/ProcessStepItem.tsx) 同级）
   - `it('should allow expanding a pending thought node to view streaming content')`
   - `it('should show accumulated details in real-time when expanded during streaming')`
3. **集成测试** — 前端 `MessageList.test.tsx`
   - `it('should render final answer block content during streaming when messages arrive')`
   - `it('should NOT hide the stop button behind FinalAnswerBlock null return')`

**运行命令**:
```bash
# 前端组件测试
cd frontend && npx vitest run src/components/chat/ProcessStepItem.test.tsx

# Python 端流式测试
uv run pytest tests/hooks/test_useChatStreaming.py -v
```
