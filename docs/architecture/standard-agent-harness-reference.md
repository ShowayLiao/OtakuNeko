# OtakuNeko Standard Agent Harness Reference

> 版本：1.0
> 日期：2026-07-31
> 适用范围：`backend/app/agents`、`backend/app/harness`、`backend/app/capabilities`、`backend/app/mcp_server`、`backend/app/memory`、`backend/app/trace` 及其 API、前端事件投影和测试。

本文档是 OtakuNeko 的项目级 Harness 规范入口。通用术语、完整架构模型、审计输出格式和成熟度定义见 [`../standard-agent-harness-reference-and-codex-audit-guide.md`](../standard-agent-harness-reference-and-codex-audit-guide.md)。当前源码审计证据见 [`../harness-audit/`](../harness-audit/)。

## 1. 规范地位

本文档中的 MUST 是当前仓库的硬约束，SHOULD 是默认工程约定，MAY 需要在任务文件中明确理由。规范不要求替换 LangGraph、引入某个供应商 SDK 或构建通用平台；每项设计必须能映射到当前源码和一个可验证的 Batch。

当本文档、审计、任务或 README 与源码不一致时：

1. 记录文件路径、符号和实际行为；
2. 将不一致写入 `docs/harness-execution/BATCH-XX-execution.md`；
3. 在当前任务允许范围内修正文档或增加兼容适配；
4. 超出任务范围时停止，不通过伪造模块或 Prompt 约束掩盖差异。

## 2. 不变量

### 2.1 Runtime 是 Run 的唯一控制者

一次 Agent Run MUST 只有一个控制面。Runtime 负责创建和推进 Run、预算、取消、终止、重试决策、状态持久化和 terminal result。HTTP Controller、LangGraph、Tool、MCP Server 和 Subagent 不得各自维护一套互不知情的 Agent Loop。

在 OtakuNeko 当前实现中，`backend/app/harness/runtime.py::AgentRuntime` 是迁移目标；`backend/app/agents/graph.py::ChatWorkflow` 当前仍实际拥有 `think -> tools -> think -> speak` 图循环，因此只能作为事实记录或 adapter 演进，不能在任务中直接宣称已满足唯一 Runtime。

### 2.2 LLM 只能提出 Decision

模型输出 MUST 先被解析为有限、结构化、版本化的 Decision。只有 Runtime 经过 Schema、Policy 和资源授权后，才能生成 Invocation 并调度 Tool、Capability、Workflow 或 Subagent。

模型不得直接获得：

- 数据库连接或 ORM Session；
- 文件句柄、Shell 或任意系统调用；
- 用户凭据、JWT、BYOK Secret 或内部网络客户端；
- 未经 Registry 和 Allowlist 暴露的能力。

### 2.3 身份由可信上下文注入

`user_id`、租户、角色、scope 和资源归属 MUST 来自认证后的 Runtime/Domain Service 上下文，不得信任模型参数、Tool 参数或前端展示字段。Tool 和 Service 必须再次执行资源级授权；Prompt 中的“只能访问当前用户数据”不构成权限控制。

聊天线程继续使用 `backend/app/api/v1/agent.py` 的用户范围 Thread Scope；迁移中的新契约应把该主体映射到显式 `ExecutionContext`，而不是改变 JWT 格式或把身份暴露给模型 Schema。

### 2.4 外部副作用必须显式治理

所有写入、发送、下载、删除、收藏修改、日程写入、Memory 写入和文件写入 MUST 标记副作用和风险，并在执行前完成：

- 权限与资源归属检查；
- 超时、取消和重试语义；
- 幂等键或明确的不可重试理由；
- 审计事件；
- 超时后“可能已成功”的处理；
- 部分成功、补偿或人工介入路径。

qBittorrent 是当前最高风险边界：`backend/app/api/v1/rss.py` 的写路由必须先经过认证和能力策略，不能因为 `ENABLE_QB_PROXY` 开启就获得匿名执行权。`backend/app/mcp_server` 已有局部 side-effect/idempotency policy，但不能代替 REST RSS 路由的授权。

### 2.5 SSE 只是投影通道

SSE/WebSocket MUST 作为 Run Event 的订阅或投影，不能作为 Run 状态唯一存储。断线、浏览器 Abort、代理重连和服务重启不得被默认为成功或直接丢弃 Run。恢复语义需要稳定的 `run_id`、`event_id`、单调 sequence、Invocation 状态和可查询的 terminal result。

当前 `backend/app/api/v1/agent.py`、`backend/app/agents/langgraph_adapter.py` 和 `frontend/src/lib/fetcher.ts` 的 SSE 行为属于兼容边界；新任务必须先保留现有事件消费能力，再逐步接入 durable Run/Event。

### 2.6 契约必须结构化、可版本化

跨 Runtime、Model、Tool、Capability、API、SSE、Trace 和 Eval 的数据 MUST 使用明确 Schema。迁移目标至少包括：

| 契约 | 最低要求 |
|---|---|
| `RunRequest` | 用户目标、可信执行上下文引用、预算和兼容入口 |
| `AgentDecision` | 版本、类型、能力名、结构化参数或最终回答 |
| `InvocationRequest` | invocation ID、run/step 关联、能力版本、策略快照、幂等语义 |
| `InvocationResult` | success/failure、结构化错误、safe output、usage 和审计引用 |
| `RunEvent` | run/step/invocation 关联、sequence、状态、safe payload 和时间 |
| `RunResult` | 唯一 terminal status、结果引用、错误和恢复信息 |

供应商对象（LangChain、OpenAI-compatible response、LangGraph message）不得泄漏到业务层；适配器负责归一化 provider、usage、finish reason 和错误。

### 2.7 外部数据默认不可信

Tool output、RSS、Bangumi、MCP、网页内容、用户上传文本和历史 Memory MUST 视为不可信数据。它们不得升级为 system instruction，不得绕过 Policy，不得未经 provenance、scope 和 retention 规则写入长期 Memory。大结果应保存为 Artifact 或受控引用，前端和模型只接收 safe output。

### 2.8 错误、取消和预算必须可观测

错误 MUST 有稳定 code/category，并明确 retryable、terminal、cancelled、timeout、denied 和 budget-exceeded 语义。参数错误、权限错误和不可幂等副作用不得盲目重试；模型、Tool、Step 和 Run 必须有独立的超时/预算边界。

至少应能关联：`run_id`、`trace_id`、`step_id`、`invocation_id`、sequence、provider、model、usage、latency、error_code。日志、Trace、SSE 和 Eval fixture 默认不得包含 Secret、完整 BYOK、raw exception、完整 Prompt 或未经裁剪的 Chain-of-Thought。

## 3. OtakuNeko 当前组件边界

| 目录/符号 | 当前事实 | 迁移目标 |
|---|---|---|
| `backend/app/api/v1/agent.py` | 组装请求、Thread Scope、Memory、Trace、Runtime 和 SSE | Ingress 与事件投影，不拥有完整 Agent Loop |
| `backend/app/harness/runtime.py` | 已有 AgentRuntime、状态/结果/Trace 包装 | 唯一 Run Coordinator |
| `backend/app/agents/graph.py` | LangGraph 图、模型、ToolNode 和循环 | 受控 Loop adapter，不是第二个 Run 控制面 |
| `backend/app/agents/langgraph_adapter.py` | 将图事件转换为 Runtime/Trace/SSE 可消费事件 | Decision/Invocation/Result adapter |
| `backend/app/capabilities/` | ActionDescriptor、Registry、业务能力和 LangChain adapter | 能力定义、Schema、Allowlist 和 Dispatcher 边界 |
| `backend/app/mcp_server/` | MCP Exposure、Policy、可信上下文和局部幂等 | 与 HTTP/LangGraph 共用策略和结果归一化 |
| `backend/app/memory/` | SQL Memory 与 LangGraph Store 两条路径 | 明确 Memory、Context、Artifact 的来源和生命周期 |
| `backend/app/trace/` | Trace、redaction、SQL/InMemory Store | 可观测/审计投影，不替代 Run/Event 状态机 |
| `backend/app/harness/scheduler/` | Proactive task、lease、重试和持久化 | 可复用调度语义，但不与交互 Run 争夺控制权 |

这张表是当前事实映射，不表示所有目标模块都已经存在。任务不得为了填满目标架构而创建空接口或伪实现。

## 4. 生命周期和持久化目标

Run 至少应能经历：`queued -> running -> waiting/paused -> completed | failed | cancelled | timed_out | budget_exceeded | abandoned`。状态转换必须由 Runtime 单调推进，Terminal 状态不得再次执行 Invocation。

持久化演进顺序为：

1. 先冻结 Run/Decision/Invocation/Event/Result 错误契约；
2. 再接入 Runtime 和 LangGraph adapter；
3. 再持久化 Run、Invocation、Event、Checkpoint 和幂等记录；
4. 最后把 SSE 改为 durable Event projection，并验证重连、重启和取消。

当前 `data/checkpoints.db`、SQLite/PostgreSQL、Alembic 与 Docker volume 的真实恢复语义尚需按任务验证，不得仅凭存在 checkpoint 类或 SSE sequence 宣称已支持 Durable Harness。

## 5. 批次、范围和完成门槛

- 批次顺序以 [`../harness-tasks/INDEX.md`](../harness-tasks/INDEX.md) 为准；一次只实施一个 Batch。
- 当前没有“正在执行”的 Batch 时，只能做审计、规划或文档整理，不得伪造 `BATCH-XX-execution.md`。
- 每个 Batch 必须有允许/禁止文件范围、前置条件、验收测试、兼容策略、回滚方式和执行记录。
- 新增能力先覆盖 read-only 和契约测试，再进入写能力；不得为了符合目标架构同时迁移 Runtime、所有 Tool、Memory、数据库和前端协议。
- 提交前必须完成完整 diff Review；Blocker、Critical、High 和未处理 Medium Finding 均阻止提交。
- 文档变更也必须检查相对链接、路径与源码事实；不能把审计结论或目标架构写成已实现事实。

## 6. 项目验证命令

命令来源于当前仓库的 `backend/pyproject.toml`、`backend/uv.lock`、根 `package.json` 和 `frontend/package.json`：

```powershell
# 后端：从 backend 目录执行
uv run pytest
uv run ruff check app tests

# 前端：从仓库根目录执行
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend test
pnpm --dir frontend build
```

文档-only 变更至少运行 Markdown/路径检查、`git diff --check` 和完整 diff Review；只有触及对应源码或契约时才要求运行后端/前端测试。所有跳过项及原因写入执行记录。
