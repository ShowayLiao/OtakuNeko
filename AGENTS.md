# OtakuNeko Agent Instructions

本文件适用于整个仓库。子目录中的 `AGENTS.md` 可以补充本文件；`AGENTS.override.md` 可以在明确范围内覆盖本文件。更具体的规则只适用于其所在目录及子目录。

## 1. 项目边界与源码事实

OtakuNeko 当前是一个前后端仓库：

- 后端：`backend/`，FastAPI、LangGraph、SQLModel/SQLAlchemy、Alembic、SQLite/PostgreSQL、Redis 配置、MCP、Memory、Trace 和 Evaluation；
- 前端：`frontend/`，Next.js 16、React 19、TypeScript、SSE/HTTP 消费和 Vitest；
- Harness 相关后端边界：`backend/app/harness/`、`backend/app/agents/`、`backend/app/capabilities/`、`backend/app/mcp_server/`、`backend/app/memory/`、`backend/app/trace/`；
- 业务和集成服务：`backend/app/services/`、`backend/app/api/v1/`；
- 任务与审计文档：`docs/harness-audit/`、`docs/harness-tasks/`、`docs/harness-execution/`。

源码事实优先于 README、设计计划、审计推断和历史文档。不能从目标架构、类名、配置项或已有测试名称推断功能已经接入真实路径。发现不一致时，记录文件路径、符号、实际行为和置信度；当前任务无法处理时停止，不伪造模块、能力或完成状态。

## 2. 权威资料读取顺序

处理 Agent Harness 任务前，按以下顺序阅读：

1. `docs/architecture/standard-agent-harness-reference.md`；
2. `docs/standard-agent-harness-reference-and-codex-audit-guide.md`；
3. `docs/harness-audit/` 下与当前任务有关的审计文档；
4. `docs/harness-tasks/INDEX.md`；
5. 当前正在执行的 Batch 目录中的全部任务文件；
6. `docs/code-review.md`；
7. 当前修改路径下更具体的 `AGENTS.md` 或 `AGENTS.override.md`。

如果没有明确批准的活动 Batch，不得把 `BATCH-00` 或最近一个任务目录自动当作当前 Batch。此时可以做审计、规划、文档整理或基线检查，但不得创建虚假的 Batch 执行记录，也不得修改后续 Batch 的实现范围。

## 3. OtakuNeko Harness 不变量

所有 Harness 重构和相关文档必须遵守：

- Agent Runtime 是一次 Run 的唯一控制者；
- LLM 只能提出结构化、版本化的 Decision，不能直接获得执行权限；
- Tool、Capability、Workflow、MCP 和 Subagent 必须通过受控调度层执行；
- `user_id`、租户、角色、scope 和资源归属由可信 Runtime/Domain Service 注入，不得从模型参数获取；
- Tool 和 Domain Service 必须执行资源级授权；
- 外部副作用必须显式标记，并处理审批、超时、取消、重试、幂等、审计和补偿；
- SSE/WebSocket 只能是 Run Event 的展示或订阅通道，不能成为 Run 状态唯一存储；
- Provider、LangChain 和 LangGraph 专属对象不得进入业务层；
- Run、Decision、Invocation、Result、Event、错误和 Trace 使用结构化、可版本化契约；
- Tool output、RSS、网页、MCP、用户输入和历史 Memory 默认是不可信数据；
- Prompt 文本不能代替代码层权限、资源授权、策略和安全边界；
- 不能为了符合目标架构而创建空接口、伪实现或永久 TODO。

当前实现的事实边界见 `docs/harness-audit/00-executive-summary.md` 和 `docs/architecture/standard-agent-harness-reference.md`。特别注意：`backend/app/agents/graph.py` 当前仍拥有 LangGraph `think -> tools -> think -> speak` 循环；`backend/app/harness/runtime.py` 是迁移目标中的 Runtime，但不能仅因类名存在就宣称它已经是唯一 Coordinator。

## 4. 工作模式

复杂任务按以下循环执行：

1. Preflight；
2. Implementation；
3. Verification；
4. Review；
5. Remediation；
6. Commit（仅在获得相应授权时）；
7. Handoff。

一次只实施一个 Batch。当前 Batch 尚未通过验收和 Review 时，不得提前修改后续 Batch。没有明确允许的修改不得顺手完成。

文档-only 任务也必须核对源码引用和路径；不能把目标架构、审计建议或任务规划写成当前已实现能力。

## 5. Preflight

开始实施前必须：

- 运行 `git status --short`、`git branch --show-current`、`git rev-parse HEAD`；
- 检查是否处于普通检出或 linked worktree，并识别已有用户修改；
- 明确当前 Batch、任务依赖、前置 Batch 的完成状态和 commit；
- 阅读任务允许/禁止的文件边界；
- 检查源码、测试、依赖和部署配置，而不是只看 README；
- 从实际配置确认测试、lint、format、typecheck、build 和 Eval 命令；
- 运行任务要求的基线检查；
- 活动 Batch 才创建或更新 `docs/harness-execution/BATCH-XX-execution.md`；文档整理任务使用普通变更记录，不伪造 Batch 记录。

工作区已有的用户修改必须区分来源。不能使用 `git reset --hard`、`git checkout --` 或其他方式覆盖它们。

## 6. 真实验证命令

以下命令来自当前仓库的 `backend/pyproject.toml`、`backend/uv.lock`、根 `package.json` 和 `frontend/package.json`。从仓库根目录执行：

~~~powershell
# 后端
uv run --directory backend pytest
uv run --directory backend ruff check app tests

# 前端
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend test
pnpm --dir frontend build
~~~

也可以从 `backend/` 目录执行 `uv run pytest` 和 `uv run ruff check app tests`。不存在项目配置依据的命令不得自行写入执行记录；未运行的项目必须说明原因。

文档-only 变更至少运行：

~~~powershell
git diff --check
git diff --stat
rg -n "standard-agent-harness-reference|harness-execution|BATCH-[0-9]+" AGENTS.md docs
~~~

随后审查完整未提交 diff，确认没有业务代码、依赖、数据库、Secret、缓存或生成文件的意外变化。

## 7. 修改约束

实施任务时：

- 只修改当前任务允许的文件；
- 不进行无关重构、全仓库格式化或无关依赖升级；
- 不改变公共 API，除非任务明确要求并提供兼容路径；
- 不删除兼容层、旧实现、失败测试或强断言来制造通过结果；
- 不把 Secret、Token、密码、完整用户数据、完整 BYOK 或 raw provider payload 写入日志、测试、Eval fixture 或文档；
- 不向模型暴露数据库连接、文件句柄、Shell、凭据或任意网络客户端；
- 不绕过 Domain Service 的权限、业务约束和资源范围；
- 不执行生产部署、生产数据库操作或生产迁移；
- 新增文档中的路径、符号、命令和状态必须能由仓库验证。

文档结构维护任务默认只允许修改：`AGENTS.md`、`docs/architecture/`、`docs/harness-execution/`、`docs/code-review.md`、必要的相关审计链接，以及对应的计划文档。Harness Batch 仍必须严格遵守任务文件列出的边界；不得借文档任务修改业务代码或 Batch 任务目标。

## 8. Verification 与执行记录

每次修改后，按变更范围运行适用的：

- 单元、集成、回归和安全测试；
- ruff/eslint/lint；
- format check、typecheck；
- 前端 build；
- 后端启动检查、Alembic/数据库迁移检查；
- Agent Eval 或真实 API + fake provider/tool 回归。

执行记录必须记录完整命令、退出码、通过/失败/跳过数量、已知警告和未运行项目及原因。不能只写“测试通过”。

## 9. Code Review

Harness Batch 和会改变 Harness 规范的文档变更都必须按照 `docs/code-review.md` 审查完整未提交 diff。

Review 阶段只审查、不修改。发现问题后退出 Review，进入 Remediation；修复后重新运行全部相关检查，再审查完整 diff，而不是只看最后几行。

提交门槛：

- Review verdict 为 `pass`；
- 不存在 blocker、critical、high Finding；
- 不存在未处理的 medium Finding；
- 任务验收项全部满足；
- 适用测试和检查均有真实退出码；
- 修改范围符合任务约束；
- 回滚方式明确。

## 10. Git 规则

允许查看 `status`、`diff`、`log`，以及在明确授权后创建本地 commit。提交前必须运行：

~~~powershell
git status --short
git diff --check
git diff --stat
git diff
~~~

禁止：

~~~text
git add .
git add -A
git commit --no-verify
git reset --hard
git push --force
~~~

暂存时必须显式列出当前任务文件路径。未经用户明确授权，不得 `git push`、创建或合并 PR、修改主分支、删除远程分支、发布、部署或运行生产迁移。

推荐 commit 格式：

~~~text
<type>(harness): <batch objective>

Batch: BATCH-XX
Tasks: TASK-HARNESS-XXX
Gaps: GAP-XXX
Tests: <summary>
Review: pass
~~~

没有活动 Batch 的文档整理不应伪造 Batch 编号；使用能准确描述文档变更的 commit message。

## 11. 停止条件

出现以下情况时停止当前工作，不得继续扩大范围：

- 前置条件不满足或当前 Batch 无法确定；
- 工作区存在无法归属的修改；
- 任务要求相互矛盾；
- 需要超出允许范围的大规模修改；
- 关键测试失败且无法在当前范围内修复；
- 发现跨用户访问、Secret 泄漏或未授权副作用；
- 无法确定写操作的幂等语义、回滚路径或外部状态；
- 连续三轮 Review 仍未通过；
- 计划与源码事实严重不一致；
- 当前上下文不足以可靠完成下一步。

停止时必须报告：阻塞原因、源码证据、当前分支和 commit、工作区状态、已完成内容和建议恢复方式。

## 12. Handoff

Batch 完成时使用 `docs/harness-execution/TEMPLATE.md` 中的结构输出：批次状态、commit、任务、测试通过/失败/跳过、Review verdict、rounds、changed files、deferred findings、未解决风险和下一批次。

没有活动 Batch 的文档任务至少应输出：变更文件、验证命令和退出码、未运行项目及原因、审查结论、未解决风险和回滚方式。


# Project Management

This repository uses the global `$ticktick-project-system` skill for external project management.

Use `$ticktick-project-system` when the user explicitly asks to:

* create a TickTick project structure
* sync a plan to TickTick
* update project state
* review project progress
* create or update hypotheses, capabilities, or AI actions
* perform a weekly review
* materialize the current plan into TickTick tasks

Do not modify TickTick when the user only asks for analysis, brainstorming, coding, or planning unless they explicitly ask to sync/update/create the project state.

Assume AI handles most implementation details. Do not create TickTick tasks for individual file edits, functions, shell commands, test commands, plots, or other low-level implementation steps unless they require independent human tracking.

---

## Project Identity

Project name:
Otakuneko

TickTick project:
Otakuneko

Project mode:
Agent development

Repository purpose:
`OtakuNeko 是一个前后端分离的个人番剧管理与分析助手：后端基于 FastAPI 提供收藏同步、排班、外部集成和 AI 聊天能力，前端基于 Next.js 提供管理与实时聊天界面。Agent Harness 正在从现有 LangGraph 运行路径向 Runtime-owned、可观测且可恢复的控制面演进；是否已接入真实主路径必须以源码和测试为准。`


# Mode B — Agent / Software System Development

> 如果当前项目不是 Agent / 软件系统开发项目，可保留本节但忽略执行。
> 当 `Project mode = Agent development` 时，遵循本节。

## Management Model

Use this hierarchy:

`Project -> Workstream -> Capability -> AI Action`

Development loop:

`Problem -> Capability Spec -> AI Implementation -> Eval -> Acceptance -> Decision -> Next Capability / Iteration`

## Project Top Notes

The TickTick project should contain two top notes:

### `00｜Project Definition`

Maintain:

* outcome
* scope
* non-goals
* definition of done
* current stage/version
* important links

### `01｜System Metrics`

Maintain:

* current version
* baseline/current/target metrics
* current bottlenecks
* current best commit/eval
* current focus
* regression guardrails
* latest major decision

These two notes are the source of truth for system state.

## Workstream

TickTick groups represent stable technical workstreams.

Examples:

* `CORE RUNTIME`
* `TOOLS & SANDBOX`
* `CONTEXT & MEMORY`
* `PLANNING & CONTROL`
* `EVAL & OBSERVABILITY`
* `PERFORMANCE`
* `RELEASE`

Use workstreams to express where the capability belongs, not whether it is complete.

## Capability Parent Task

A parent task represents a system capability.

Recommended title format:

`Capability Name｜vX`

Examples:

* `Context Compaction｜v1`
* `Tool Recovery｜v2`
* `Stuck Detection｜v1`

A capability task should contain:

* Problem
* Goal
* Scope
* Expected Behavior
* Acceptance Criteria
* Metrics
* Result
* Decision
* Next
* Artifacts

A capability is complete only after evaluation leads to a clear decision:

* Accept
* Iterate
* Rework
* Revert
* Park

Do not mark a capability complete merely because the implementation exists.

## AI Action Subtask

A child task represents one independently delegable AI work package.

Recommended title format:

`Axxx｜完成实现 + eval + regression + 结论`

A good AI Action may include:

* implementation
* tests
* eval
* regression checks
* benchmark comparison
* result summary

Prefer one outcome-oriented AI Action over many coding micro-tasks.

Example:

`实现 Context Compaction v1，完成 long-task eval、regression 检查并输出结果总结`

Avoid creating separate TickTick tasks for:

* editing individual files
* implementing functions
* running shell commands
* writing unit tests
* changing config files

unless they require independent tracking.

## Capability Decision Rule

After an AI Action:

1. update Result
2. check Acceptance Criteria
3. update system metrics if necessary
4. decide Accept / Iterate / Rework / Revert / Park
5. identify the next bottleneck
6. create a new capability or iteration only if justified
7. mark only the true next action as `#next`

---

# Shared TickTick Rules

These rules apply to both project modes.

## Tags

Use only a small set of execution-state tags:

* `#next`
* `#waiting`
* `#blocked`

Meaning:

### `#next`

The item can be acted on now and is a genuine next step.

### `#waiting`

The item is waiting for:

* training
* machine/GPU
* external result
* another person
* dependency

### `#blocked`

There is a known blocker preventing progress.

Do not use project-name tags when the project is already represented by a TickTick list.

## Dates

TickTick dates mean:

`I plan to handle this around this date.`

They do not mean hard calendar commitments.

Only assign dates to:

* genuine short-term execution plans
* items that truly need to appear in Today

Do not pre-schedule large amounts of future research or development work.

## Calendar Boundary

Apple Calendar is the source of truth for hard time commitments.

Use Calendar for:

* meetings
* appointments
* travel
* fixed-time reviews
* hard deadlines
* anything that occupies a specific time slot

Do not duplicate ordinary TickTick work into Calendar unless time-blocking is explicitly desired.

## Reminder Boundary

Apple Reminders is the capture inbox.

Use it for:

* quick Siri capture
* things the user is afraid of forgetting
* temporary unprocessed actions

After review:

* project-related item -> TickTick
* knowledge/idea -> Apple Notes
* fixed-time event -> Apple Calendar
* simple timed reminder -> remain in Apple Reminders
* irrelevant -> delete

## Notes Boundary

Apple Notes stores durable information, not project execution state.

Use it for:

* knowledge
* ideas
* reflections
* life systems
* book/movie/series lists
* long-term references

Do not use Apple Notes as the primary project task manager.

---

# Weekly Review

Use the `$ticktick-project-system` skill when the user asks for a weekly review.

The weekly review should:

1. clear Apple Reminders Inbox
2. review Apple Notes Inbox
3. inspect the next two weeks of Calendar
4. review all active TickTick projects
5. update LLM metrics/hypotheses or Agent capabilities/metrics
6. review `#waiting`
7. review `#blocked`
8. update routines/habits if necessary
9. select weekly focus
10. identify true `#next` actions

Weekly focus should normally contain:

## ONE BIG THING

The single most important result, judgment, or capability to advance.

## SECONDARY

At most 1–2 additional priorities.

## NOT THIS WEEK

Explicitly defer attractive but non-critical work.

For LLM research, weekly focus should prefer:

* resolving an important uncertainty
* validating/rejecting a hypothesis
* identifying the true bottleneck

For Agent development, weekly focus should prefer:

* getting a capability to an acceptance decision
* removing the largest system bottleneck
* completing a meaningful reliability/eval milestone

---

# TickTick Tool Usage

When syncing or creating project state:

1. first inspect the currently available TickTick MCP/CLI/tooling
2. read its actual schema/help
3. map the semantic operations to the available commands
4. reuse existing project objects when possible
5. avoid duplicate lists, groups, notes, tasks, or tags
6. update existing objects before creating new ones
7. preserve user-written content unless an update is explicitly required

Required semantic operations may include:

* find/create project list
* find/create group
* find/create/update note
* find/create/update parent task
* find/create/update subtask
* set/remove tags
* set/remove dates
* complete/archive task
* move task/group
* inspect current project state

Do not assume a specific MCP function name or CLI syntax.

---

# Project-Specific Overrides

Use this section for rules unique to this repository.

## Technical Constraints

- 后端 `requires-python = ">=3.10"`，使用 FastAPI、SQLModel/SQLAlchemy、Alembic、LangChain/LangGraph 和 pytest/Ruff；前端使用 Next.js 16、React 19、TypeScript 和 Vitest。
- 前端包管理器为 pnpm `10.15.1`；CI 使用 Node.js `20.19.0`。版本与命令以 `backend/pyproject.toml`、`backend/uv.lock`、`frontend/package.json` 和工作流配置为准。
- 本地 SQLite checkpoint adapter 仅按单 Worker 使用；当前已有受限的 checkpoint、取消和重启恢复路径，但不得据此宣称支持共享多 Worker recovery。容器化部署使用 Docker Compose 编排 PostgreSQL、Redis、Backend、Frontend 和 qBittorrent。
- Agent 运行必须遵守本文前述 Runtime ownership、结构化 Decision、可信身份/资源授权、显式副作用、审计和恢复不变量；Provider/LangChain/LangGraph 专属对象不得泄漏到业务层。

## Evaluation Source of Truth

评估以 `backend/app/evaluation/runner.py`、`backend/evals/config/`、`backend/evals/datasets/` 和 `backend/evals/baselines/` 为准；离线快速评估使用 `evals/config/fast.yaml`，可观测性评估使用 `evals/config/observability.yaml`，完整评估使用 `evals/config/full.yaml`。仓库未配置 WandB 作为权威来源。

适用的工程门禁为：`uv run --directory backend pytest`、`uv run --directory backend ruff check app tests`、`pnpm --dir frontend lint`、`pnpm --dir frontend typecheck`、`pnpm --dir frontend test` 和 `pnpm --dir frontend build`；Eval 命令和报告路径以 `.github/workflows/` 及 `backend/evals/README.md` 为准。

## Important Repositories / Paths

- 后端控制面与边界：`backend/app/harness/`、`backend/app/agents/`、`backend/app/capabilities/`、`backend/app/mcp_server/`、`backend/app/memory/`、`backend/app/trace/`。
- 业务与集成：`backend/app/services/`、`backend/app/api/v1/`；评估与测试：`backend/app/evaluation/`、`backend/evals/`、`backend/tests/`。
- 前端：`frontend/src/`、`frontend/src/__tests__/`；部署与自动化：`docker-compose.yml`、`.github/workflows/`。
- Harness 权威资料与执行记录：`docs/architecture/`、`docs/harness-audit/`、`docs/harness-tasks/`、`docs/harness-execution/`。

## Current Active Focus

当前没有明确批准的活动 Batch；BATCH-26 是最近已完成的执行批次。近期焦点是维护 Level 4 Runtime-owned 主路径及其 CI/Eval 门禁，并处理已声明的剩余风险：Dispatcher-backed specialist/subagent 合约，以及超出 SQLite 单 Worker 限制的共享 checkpoint、取消和 worker recovery。目标架构或历史 execution record 仍不能替代当前源码与真实验证证据。

## Explicit Non-Goals

- 不仅凭 README、目标架构、任务计划、类名或测试名称断言真实接入；当前能力必须由源码和真实验证证据确认，也不在没有活动 Batch 时伪造执行记录。
- 没有明确任务范围时，不重写 LangGraph 图、不替换模型框架，也不整体迁移收藏/日程等业务 Service；相关变更必须保留受控 Runtime、Registry、Policy 和 adapter 边界。
- 不执行生产部署、生产数据库操作或生产迁移；不把真实 Secret、Token、完整用户数据或 raw Provider payload 写入仓库、日志、测试、Eval fixture 或文档。
- 用户未明确要求时，不同步或修改 TickTick 等外部项目状态，也不扩展到与当前任务无关的业务功能。
