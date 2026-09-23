# Harness 文档结构实现计划

> **面向 AI 代理的工作者：** 本计划只处理 Harness 文档入口、执行记录模板和审查规范，不修改业务代码、依赖、数据库或 Batch 任务目标。

**目标：** 让 OtakuNeko 的 Harness 规范路径、执行记录、源码事实和 Code Review 规则与当前项目实际结构一致。

**架构：** 新增项目级 architecture reference，保留完整通用审计指南作为上位资料；新增执行记录说明和模板。`AGENTS.md` 负责工作流与范围控制，`docs/code-review.md` 负责证据型审查，二者共享实际源码边界和验证命令。

**技术栈：** Markdown、PowerShell、Git；后端验证命令来自 `backend/pyproject.toml`，前端验证命令来自 `frontend/package.json`。

---

### 任务 1：建立文档入口和执行记录模板

**文件：**

- 创建：`docs/architecture/README.md`
- 创建：`docs/architecture/standard-agent-harness-reference.md`
- 创建：`docs/harness-execution/README.md`
- 创建：`docs/harness-execution/TEMPLATE.md`

- [x] 明确项目级参考规范、完整审计指南、审计结果和执行记录的职责边界。
- [x] 写入 OtakuNeko 当前 `backend/app/agents`、`backend/app/harness`、`backend/app/capabilities`、`backend/app/mcp_server`、`backend/app/memory`、`backend/app/trace` 的事实映射。
- [x] 写入 Run、Decision、Invocation、Event、SSE、授权、副作用、恢复和验证不变量。

### 任务 2：同步 Agent 工作规则

**文件：**

- 修改：`AGENTS.md`

- [x] 修正权威资料路径和当前 Batch 判定。
- [x] 记录真实后端、前端、Eval、lint、typecheck 和构建命令。
- [x] 明确文档-only 变更、执行记录、未跟踪草稿和源码事实优先级。

### 任务 3：同步 Code Review 规则

**文件：**

- 修改：`docs/code-review.md`

- [x] 增加 OtakuNeko 专项边界：FastAPI/SSE、LangGraph adapter、Capability/MCP、Memory/Trace、qBittorrent 和 Provider endpoint。
- [x] 保留完整 diff、证据、严重度、验证命令和 YAML 输出门槛。
- [x] 增加 Markdown 链接、目标架构不得冒充已实现架构等文档审查项。

### 任务 4：验证

**文件：**

- 检查：本计划列出的全部文件及相关 Markdown 引用。

- [x] 运行 `git diff --check`。
- [x] 检查仓库内 Harness 路径引用和相对链接。
- [x] 审查完整未提交 diff，确认未触碰业务代码、依赖和数据库。
