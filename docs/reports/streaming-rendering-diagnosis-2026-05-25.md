# 流式渲染诊断分析报告

> **日期**: 2026-05-25  
> **范围**: 前后端完整流式渲染链路  
> **问题**: 发送消息后前端持续显示「正在思考」，且正文内容错误地落入推理区域

---

## 1. 问题现象

用户在聊天框发送消息后，观察到的三个关联症状：

| # | 现象 | 严重性 |
|---|------|--------|
| A | 模型已在输出文字，但前端状态栏始终显示「正在思考...」 | 🔴 阻塞 |
| B | 生成结束后，用户看到的是全部内容**一次性出现**，而非逐字流式渲染 | 🔴 阻塞 |
| C | 在不调用工具的情况下，模型的回复正文出现在了「推理」面板中，正文区域为空 | 🔴 错位 |

---

## 2. 端到端流式链路架构

```
[LLM Provider] ──(SSE token stream)──▶ [Backend graph.py]
                                            │
                          ┌─ <think> 检测 ──┤
                          ▼                  ▼
                   thinking_chunk       message_chunk
                          │                  │
                          ▼                  ▼
              [Backend /api/v1/chat SSE endpoint]
                          │
                          ▼
              [Frontend fetcher.ts parseSSE]
                          │
              ┌───────────┴────────────┐
              ▼                        ▼
      onThinkingChunk()          onMessageChunk()
              │                        │
              ▼                        ▼
    store.reasoningText         store.content
              │                        │
              ▼                        ▼
    AgentMessageRenderer       ChatItem message
    "推理" 面板展开可见         "正文" 流式渲染可见
```

---

## 3. 根因分析

### 3.1 核心根因：后端 `graph.py` 的流式相位机默认状态错误

**文件**: [graph.py](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/agents/graph.py)  
**函数**: `ChatWorkflow.stream_chat()` 内嵌的异步生成器  
**问题行**: 第 220-228 行（约）

```python
# ⚠️ BUG 所在
if phase == _StreamPhase.IDLE:
    phase = _StreamPhase.THINKING       # ← 默认进入 THINKING 相位！
    yield _emit("thinking_start")

if phase == _StreamPhase.THINKING:
    yield _emit("thinking_chunk", content=delta)   # ← 所有内容走 thinking_chunk
elif phase == _StreamPhase.FINAL_MESSAGE:
    if not message_started:
        message_started = True
        yield _emit("message_start")
    yield _emit("message_chunk", content=delta)     # ← 只有显式跳转到 FINAL_MESSAGE 才走这里
```

**相位转换逻辑的完整路径**：

```
         ┌──────────────────────────────────────┐
         │           stream_chat() 入口           │
         │         phase = _StreamPhase.IDLE     │
         └────────────────┬─────────────────────┘
                          │
              ┌───────────▼──────────────┐
              │  收到第一个 token delta    │
              └───────────┬──────────────┘
                          │
              ┌───────────▼──────────────────────┐
              │  _detect_think_boundary(delta)    │
              │  检测是否包含 <think / </think>    │
              └───┬──────────────┬───────────────┘
                  │              │
        检测到 <think>     未检测到任何标签
                  │              │
                  ▼              ▼
         phase = THINKING   phase = THINKING  ← ⚠️ BUG!
         (正确)             (错误：应该是 FINAL_MESSAGE)
```

**相位机仅在一种情况下进入 `FINAL_MESSAGE`**：
```python
if not entering and _inside_think and toggle:  # 即: 检测到 </think>
    _inside_think = False
    yield _emit("thinking_chunk", content=delta)
    yield _emit("thinking_end")
    phase = _StreamPhase.FINAL_MESSAGE         # ← 唯一进入 FINAL_MESSAGE 的路径
```

**结论**: 对于不使用 `` 标签的主流模型（OpenAI GPT、Claude、Gemini、以及 DeepSeek 的非 reasoning 模式等），流式输出**永远不会**进入 `FINAL_MESSAGE` 相位。所有 token 都被错误地归类为 `thinking_chunk`。

---

### 3.2 前端症状的因果链

```
后端: 所有 token → thinking_chunk (无 message_chunk)
                    │
                    ▼
前端: onThinkingChunk() 被持续调用
                    │
                    ├─► reasoningTextRef.current += chunk
                    ├─► store.updateMessage(..., reasoningText=reasoningTextRef.current)
                    │
                    ├─► store 中 message.content 始终为 ''
                    ├─► store 中 message.reasoningText 不断增长
                    │
                    ▼
AgentMessageRenderer.deriveStatus():
  hasContent = !!msg.content = !!'' = false
  reasoningText = "大段模型回复正文..."
  → returns 'thinking'  ← 「正在思考...」
                    │
                    ▼
MessageList: ChatItem message={msg.content || ' '}
  → 正文区域为空，看不到流式文字
                    │
                    ▼
AgentMessageRenderer 的 "推理" 面板:
  {reasoningText}  ← 显示的是模型真正的回复正文！
```

**三个现象的一因多果**：
| 现象 | 原因 |
|------|------|
| A: 始终显示「正在思考」 | `deriveStatus` 因 `hasContent=false` 返回 `'thinking'` |
| B: 一次性出现全部内容 | 所有内容存在 `reasoningText`，流式更新的是推理面板（默认折叠），用户看不到逐字过程 |
| C: 正文落入推理区 | `reasoningText` 存的是真正的回复内容，正文 `content` 为空 |

---

### 3.3 辅助问题：`on_chat_model_end` 的相位处理逻辑

```python
elif kind == "on_chat_model_end":
    if _inside_think:
        yield _emit("thinking_end")
        _inside_think = False
    if phase == _StreamPhase.THINKING:
        yield _emit("thinking_end")
    if message_started:
        yield _emit("message_end")
    phase = _StreamPhase.IDLE
```

当模型不使用 `` 标签时，`phase == THINKING`，会触发 `thinking_end` 事件。但 `message_started` 始终为 `False`（因为从未进入 `FINAL_MESSAGE`），所以不会发送 `message_end`。这导致前端收不到流式完成的信号（不过 `onComplete` 由外层 Promise 控制，影响不大）。

---

### 3.4 影响范围矩阵

| 模型类型 | 是否受影响 | 说明 |
|---------|-----------|------|
| OpenAI GPT-4/GPT-3.5 | 🔴 完全受影响 | 不使用 `` |
| Claude 系列 | 🔴 完全受影响 | 不使用 `` |
| Gemini 系列 | 🔴 完全受影响 | 不使用 `` |
| DeepSeek V3 (非 reasoning) | 🔴 完全受影响 | 不使用 `` |
| DeepSeek R1 (reasoning) | 🟢 正常 | 使用 `` |
| Ollama 本地模型 (无 reasoning) | 🔴 完全受影响 | 不使用 `` |
| Ollama 本地模型 (有 reasoning) | 🟢 正常 | 使用 `` |

---

## 4. 修复方案

### 4.1 后端核心修复（graph.py）

**原则**: 将流式相位机的默认路径从 `THINKING` 改为 `FINAL_MESSAGE`。仅当检测到 `` 标签时才进入 `THINKING` 相位。

**修改位置**: [graph.py:L214-L228](file:///e:/HACCI/Documents/tools/OtakuNeko/backend/app/agents/graph.py#L214-L228)

```python
# ===== 修改前 =====
if phase == _StreamPhase.IDLE:
    phase = _StreamPhase.THINKING
    yield _emit("thinking_start")

if phase == _StreamPhase.THINKING:
    yield _emit("thinking_chunk", content=delta)
elif phase == _StreamPhase.FINAL_MESSAGE:
    if not message_started:
        message_started = True
        yield _emit("message_start")
    yield _emit("message_chunk", content=delta)

# ===== 修改后 =====
if phase == _StreamPhase.IDLE:
    phase = _StreamPhase.FINAL_MESSAGE

if phase == _StreamPhase.THINKING:
    yield _emit("thinking_chunk", content=delta)
elif phase == _StreamPhase.FINAL_MESSAGE:
    if not message_started:
        message_started = True
        yield _emit("message_start")
    yield _emit("message_chunk", content=delta)
```

**修复后的相位流转**：

- **无 `` 模型**: `IDLE → FINAL_MESSAGE` → 直接产出 `message_start` + `message_chunk` ✅
- **有 `` 模型**: `IDLE → FINAL_MESSAGE` → 检测到 `` → 切换到 `THINKING` → 检测到 `` → 切回 `FINAL_MESSAGE` ✅
- **工具调用**: `on_tool_start` 中将 `phase` 设为 `TOOLING`，不依赖默认路径 ✅

### 4.2 后端辅助修复：`on_chat_model_end` 节

```python
elif kind == "on_chat_model_end":
    if _inside_think:
        yield _emit("thinking_end")
        _inside_think = False
    if phase == _StreamPhase.THINKING:
        yield _emit("thinking_end")
    if message_started:
        yield _emit("message_end")
    phase = _StreamPhase.IDLE
```

此段逻辑在修复后仍然正确：对于无 `` 模型，`message_started=True`，正常发送 `message_end`。

### 4.3 前端（无需修改）

前端 `useChatStreaming.ts`、`AgentMessageRenderer.tsx`、`MessageList.tsx` 的流式处理逻辑在本次根因下工作正确。修复后端后，前端会自动正确渲染：
- `onMessageChunk` → 流式更新正文
- `deriveStatus` → 检测到 `hasContent=true` → 返回 `'responding'` → 显示「正在回复...」

---

## 5. 验证方案

请用户在后端修复后，按以下步骤验证：

```bash
# 1. 重启后端服务
cd backend
uv run uvicorn app.main:app --reload

# 2. 前端无需修改，直接使用
cd frontend
npm run dev

# 3. 在聊天界面发送消息，验证：
#    a) 状态栏是否从「正在回复...」切换为流式文字
#    b) 文字是否逐字出现（而非一次性）
#    c) 对于 DeepSeek R1，推理内容是否正确显示在推理面板
#    d) 对于 OpenAI 等，正文是否正确显示（不落入推理面板）
```

---

## 6. 附加发现：前端 `toolCallDeltaRef` 的 Key 不一致

**文件**: [useChatStreaming.ts](file:///e:/HACCI/Documents/tools/OtakuNeko/frontend/src/hooks/useChatStreaming.ts)

在 `onToolCallDelta` 中，`toolCallDeltaRef` 使用 event 的 `id` 作为 key：
```typescript
const accumulated = (toolCallDeltaRef.current.get(id) || '') + delta;
toolCallDeltaRef.current.set(id, accumulated);
```

而 `onToolCallStart` 中 delete 使用的是 `toolCallId`（由 `toolCallMapRef` 映射）：
```typescript
toolCallDeltaRef.current.delete(toolCallId);
```

如果 event.id 与生成的 toolCallId 不一致，会导致 delta 累积异常。建议使用 `name` 或统一使用 `toolCallId` 作为 `toolCallDeltaRef` 的 key。这是次要问题，不影响本次核心故障。

---

## 7. 总结

| 项目 | 内容 |
|------|------|
| **根因** | `graph.py` 流式相位机默认进入 `THINKING` 而非 `FINAL_MESSAGE` |
| **修复范围** | 仅 `backend/app/agents/graph.py` 第 214-228 行 |
| **修复行数** | 净变化 2 行 |
| **风险等级** | 🟢 低 — 仅改默认路径，不改变检测逻辑 |
| **影响模型** | 所有不使用 `` 标签的模型 |
| **前端改动** | 无需修改 |

