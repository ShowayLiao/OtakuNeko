# 思考过程连续时间线实现计划

> **面向 AI 代理的工作者：** 必需子技能：使用 superpowers:executing-plans 逐任务实现此计划。步骤使用复选框（`- [ ]`）语法来跟踪进度。

**目标：** 将思考/工具过程从可整体折叠的内部滚动面板改为无外框连续时间线，并在下一步骤开始时自动折叠上一项。

**架构：** `ProcessContainer` 负责摘要、时间线顺序和当前自动活动步骤；`ProcessStepItem` 负责单步内容和用户覆盖状态。用纯函数集中计算单步最终展开状态，避免把 `pending -> success` 误认为应立即折叠。最终回答开始后，父级不再把最后一个正常步骤视为自动活动步骤。

**技术栈：** React、TypeScript、Node `node:test`、现有前端内联样式。

---

### 任务 1：定义时间线展开状态纯函数

**文件：**
- 修改：`frontend/src/lib/processDisplayState.ts`
- 测试：`frontend/src/lib/processDisplayState.test.ts`

- [ ] **步骤 1：编写失败的测试**

新增 `resolveStepExpanded` 测试，覆盖：无内容始终关闭；最后一个正常步骤自动展开；有后继步骤时自动收起；用户手动值优先；错误步骤保持展开。

```ts
test('keeps the latest completed step open until a successor starts', () => {
  assert.equal(resolveStepExpanded({ hasBody: true, isAutoActive: true, isError: false, userExpanded: null }), true);
  assert.equal(resolveStepExpanded({ hasBody: true, isAutoActive: false, isError: false, userExpanded: null }), false);
});

test('manual step visibility overrides automatic state', () => {
  assert.equal(resolveStepExpanded({ hasBody: true, isAutoActive: true, isError: false, userExpanded: false }), false);
  assert.equal(resolveStepExpanded({ hasBody: true, isAutoActive: false, isError: false, userExpanded: true }), true);
});

test('error steps remain visible and body-less steps stay closed', () => {
  assert.equal(resolveStepExpanded({ hasBody: true, isAutoActive: false, isError: true, userExpanded: null }), true);
  assert.equal(resolveStepExpanded({ hasBody: false, isAutoActive: true, isError: false, userExpanded: null }), false);
});
```

- [ ] **步骤 2：运行测试验证失败**

运行：`node --import tsx --test frontend/src/lib/processDisplayState.test.ts`

预期：FAIL，报错 `resolveStepExpanded is not a function`。

- [ ] **步骤 3：编写最少实现代码**

在 `processDisplayState.ts` 添加 `StepExpansionInput` 类型与 `resolveStepExpanded`：先判断 `hasBody`，再使用错误状态、用户覆盖值、自动活动状态的优先级。

- [ ] **步骤 4：运行测试确认通过**

运行同一命令，预期新增测试与既有 `resolveProcessExpanded`、`selectPendingTool` 测试全部 PASS。

- [ ] **步骤 5：Commit**

```bash
git add frontend/src/lib/processDisplayState.ts frontend/src/lib/processDisplayState.test.ts
git commit -m "test: define process step expansion rules"
```

### 任务 2：改造单步组件，保留用户覆盖状态

**文件：**
- 修改：`frontend/src/components/chat/ProcessStepItem.tsx`

- [ ] **步骤 1：编写失败的组件测试**

在现有 `AgentMessageRenderer.test.tsx` 增加行为测试：传入 `autoExpanded` 后，步骤完成仍显示详情；`autoExpanded` 变为 false 后收起；点击步骤后，后续 rerender 不覆盖手动选择。

- [ ] **步骤 2：运行测试验证失败**

运行：`npx vitest run frontend/src/__tests__/components/chat/AgentMessageRenderer.test.tsx`

预期：FAIL，当前组件没有 `autoExpanded` 属性，且完成步骤按 `isPending` 自动关闭。

- [ ] **步骤 3：编写最少实现代码**

给 `ProcessStepItemProps` 增加 `autoExpanded: boolean`；用 `resolveStepExpanded` 计算展开值；保留 `userExpanded: boolean | null`，点击时只写用户覆盖值。将步骤卡片头改为真正的 `button` 或补齐键盘与 `aria-expanded` 行为。

- [ ] **步骤 4：运行测试确认通过**

运行同一 Vitest 命令，预期组件测试 PASS。

- [ ] **步骤 5：Commit**

```bash
git add frontend/src/components/chat/ProcessStepItem.tsx frontend/src/__tests__/components/chat/AgentMessageRenderer.test.tsx
git commit -m "fix: preserve process step expansion choices"
```

### 任务 3：移除外层折叠面板，渲染连续时间线

**文件：**
- 修改：`frontend/src/components/chat/ProcessContainer.tsx`
- 修改：`frontend/src/components/chat/AgentMessageRenderer.tsx`

- [ ] **步骤 1：编写失败的结构测试**

增加断言：摘要文本仍存在；摘要行没有整体折叠按钮；过程内容直接渲染；步骤列表不包含固定 `maxHeight: 360` 或内部 `overflowY: auto`；当前最后步骤接收 `autoExpanded=true`，回答开始后为 false。

- [ ] **步骤 2：运行测试验证失败**

运行：`npx vitest run frontend/src/__tests__/components/chat/AgentMessageRenderer.test.tsx`

预期：FAIL，现有组件仍渲染外层边框、Chevron 整体折叠和固定高度滚动容器。

- [ ] **步骤 3：编写最少实现代码**

删除 `ProcessContainer` 的整体 `userExpanded`、`expanded`、折叠网格、内部滚动 ref 和滚动监听；摘要改为非交互行，隐藏按钮继续独立工作。使用 `processes.map` 的最后索引计算 `autoExpanded`，错误节点始终保持自动展开；将 `hasContent`/`isResponding` 从 `AgentMessageRenderer` 传入以处理最终回答开始阶段。

- [ ] **步骤 4：运行测试确认通过**

运行同一 Vitest 命令，预期结构和交互测试 PASS。

- [ ] **步骤 5：Commit**

```bash
git add frontend/src/components/chat/ProcessContainer.tsx frontend/src/components/chat/AgentMessageRenderer.tsx frontend/src/__tests__/components/chat/AgentMessageRenderer.test.tsx
git commit -m "feat: render process steps as a continuous timeline"
```

### 任务 4：回归验证滚动、类型和现有流式行为

**文件：**
- 修改：无（仅在验证失败时回到对应任务修复）

- [ ] **步骤 1：运行过程状态和组件测试**

运行：`node --import tsx --test frontend/src/lib/processDisplayState.test.ts` 与 `npx vitest run frontend/src/__tests__/components/chat/AgentMessageRenderer.test.tsx`，预期全部 PASS。

- [ ] **步骤 2：运行前端类型检查**

运行：`npm run typecheck --prefix frontend`，预期退出码为 0。

- [ ] **步骤 3：运行前端构建或项目既有验证命令**

运行：`npm run build --prefix frontend`；若仓库脚本名称不同，先读取 `frontend/package.json` 的 scripts 并运行对应构建脚本。预期构建成功且无新增 TypeScript 错误。

- [ ] **步骤 4：检查差异范围**

运行：`git diff --check` 与 `git status --short`，确认本次变更只涉及时间线组件、状态测试和实现计划中列出的文件，不覆盖用户已有修改。

- [ ] **步骤 5：Commit（如验证修复产生额外改动）**

```bash
git add frontend/src/components/chat frontend/src/lib/processDisplayState.ts frontend/src/lib/processDisplayState.test.ts frontend/src/__tests__/components/chat/AgentMessageRenderer.test.tsx
git commit -m "test: verify process timeline behavior"
```
