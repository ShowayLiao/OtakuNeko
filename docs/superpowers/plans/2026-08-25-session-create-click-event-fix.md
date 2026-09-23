# 新建会话点击事件修复实施计划

> **面向 AI 代理的工作者：** 在当前会话内按 TDD 顺序执行本计划；不创建 commit，除非用户另行授权。

**目标：** 点击会话面板的 `+` 按钮时，只调用无参数的会话创建回调，避免把 React 点击事件误用为 `sessionId`。

**架构：** 在 `SessionPanel` 的 UI 事件边界丢弃点击事件，保持 Store 的 `createSession(requestedSessionId?)` API 不变。使用组件回归测试验证回调被调用一次且参数列表为空。

**技术栈：** React 19、TypeScript、Vitest、Testing Library。

---

### 任务 1：锁定并修复点击事件泄漏

**文件：**

- 修改：`frontend/src/components/chat/SessionPanel.test.tsx`
- 修改：`frontend/src/components/chat/SessionPanel.tsx`

- [x] **步骤 1：编写失败回归测试**

  让测试中的 `ActionIcon` mock 渲染真实按钮并转发 `onClick`，点击“新建会话”后断言：

  ```ts
  expect(onCreateSession).toHaveBeenCalledOnce();
  expect(onCreateSession.mock.calls[0]).toEqual([]);
  ```

- [x] **步骤 2：运行定向测试确认红灯**

  运行：`pnpm --dir frontend test -- src/components/chat/SessionPanel.test.tsx`

  预期：新增测试失败，因为当前 `onClick={onCreateSession}` 会把点击事件作为第一个参数。

- [x] **步骤 3：实施最小修复**

  将新建按钮改为显式无参数调用：

  ```tsx
  onClick={() => onCreateSession()}
  ```

- [x] **步骤 4：运行定向测试确认绿灯**

  运行：`pnpm --dir frontend test -- src/components/chat/SessionPanel.test.tsx`

  预期：测试文件全部通过。

- [x] **步骤 5：运行前端完整验证**

  依次运行：

  ```powershell
  pnpm --dir frontend lint
  pnpm --dir frontend typecheck
  pnpm --dir frontend test
  pnpm --dir frontend build
  ```

  预期：所有命令退出码为 0；记录已有警告，不修改无关文件。

- [x] **步骤 6：审查完整任务 diff**

  运行 `git diff --check`，并审查本计划、`SessionPanel.tsx` 和 `SessionPanel.test.tsx` 的 diff，确认没有无关改动。
