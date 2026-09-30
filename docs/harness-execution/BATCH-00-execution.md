# BATCH-00 执行记录

> Batch: `BATCH-00`  
> Task: `TASK-HARNESS-000`  
> Final status: `completed`
> 开始时间: `2026-07-31 22:47 Asia/Shanghai`  
> 分支: `feature-harness`  
> 起始 commit: `26ff29c2b2e97dd0e8b27ad601b19fe801698afd`  
> 当前记录状态: `ready_for_commit`

## 1. Preflight

### 工作区与前置条件

- `git status --short`: 初始为空；Git 仅报告用户级 global ignore、缓存目录的权限警告。
- `git branch --show-current`: `feature-harness`
- `git rev-parse HEAD`: `26ff29c2b2e97dd0e8b27ad601b19fe801698afd`
- 当前为普通 checkout，不是 linked worktree。
- 前置 Batch: 无；BATCH-00 是依赖链起点，未发现既有 Batch execution record 或前置 commit。
- 任务允许范围: `TASK-HARNESS-000` 指定的后端/前端测试和 fixture；另按根 `AGENTS.md` 要求维护本执行记录。
- 任务禁止范围: 生产后端、非测试前端、Alembic、依赖锁文件、真实 Secret、外部服务/provider。

### 已读取的权威资料

- `AGENTS.md`
- `docs/architecture/standard-agent-harness-reference.md`
- `docs/standard-agent-harness-reference-and-codex-audit-guide.md`
- `docs/harness-audit/00-executive-summary.md` 至 `11-task-backlog.md`
- `docs/harness-tasks/INDEX.md`
- `docs/harness-tasks/BATCH-00/TASK-HARNESS-000.md`
- `docs/code-review.md`
- `docs/harness-execution/README.md`、`docs/harness-execution/TEMPLATE.md`

### 基线命令

| 命令 | 退出码 | 结果 | 备注 |
|---|---:|---|---|
| `uv run --directory backend pytest tests/harness tests/agents/test_langgraph_adapter.py tests/agents/test_provider_endpoint.py tests/mcp/test_policy.py tests/memory/test_service_typed.py tests/trace/test_event_contract.py -q` | 1 | 未进入 pytest | uv 默认缓存目录权限不足 |
| `uv run --no-cache --directory backend pytest tests/harness tests/agents/test_langgraph_adapter.py tests/agents/test_provider_endpoint.py tests/mcp/test_policy.py tests/memory/test_service_typed.py tests/trace/test_event_contract.py -q` | 0 | 92 passed | 22 个既有 Pydantic/pytest cache warnings |
| `uv run --no-cache --directory backend pytest tests/acceptance/test_harness_baseline.py -q` | 1 | 目标文件不存在 | BATCH-00 待新增文件 |
| `uv run --no-cache --directory backend pytest tests/evaluation -q` | 0 | 32 passed | 20 个既有 warning |
| `uv run --no-cache --directory backend ruff check app tests` | 0 | passed | All checks passed |
| `pnpm --dir frontend vitest run src/services/CalendarService.test.ts src/lib/fetcher.test.ts` | 1 | 未进入 Vitest | PowerShell 阻止 `pnpm.ps1` |

## 2. Implementation

### Characterization 覆盖

- 新增 Agent Runtime 的 normal、single-tool、multi-tool、tool-error、provider-timeout、cancel 场景；记录当前事件顺序、`stream_sequence`、终态和安全消息元数据。
- 新增 fake qB service 的匿名 RSS read/write 基线，确认当前 `ENABLE_QB_PROXY` 开启时各路由可触发 service；不连接真实 qB。
- 新增 Memory 不可信 extractor 文本基线，记录当前文本会写入 semantic memory；未加入过滤逻辑。
- 新增 CalendarService 本地纯函数基线：MEAL 日期展开、CSV 转义、voice command 文本。
- 新增前端 fetcher 当前 SSE callback vocabulary 基线。

### 源码事实与处理方式

| 文件/符号 | 当前事实 | BATCH-00 处理 |
|---|---|---|
| `app.harness.runtime.AgentRuntime.stream` | fake normal/tool-error 保存为 `completed`，timeout 为 `failed`，cancel 为 `cancelled` | 仅记录当前行为，不改生产代码 |
| `app.api.v1.rss` | 开启 `ENABLE_QB_PROXY` 时匿名 read/write 可触发 `QBService` | 以 fake service 建立反向安全基线，交由 BATCH-01 修复 |
| `app.memory.service.MemoryServiceImpl` | extractor 返回的不可信文本当前可写入 semantic memory | 仅建立当前结果 fixture，交由后续 Batch 处理 |
| `frontend/src/services/CalendarService.ts` | 日历、CSV、语音命令均为本地纯函数 | 仅新增无网络测试，不注册 Agent Tool |

### 变更范围

- `backend/tests/acceptance/test_harness_baseline.py`（新增）
- `backend/tests/memory/test_service_typed.py`
- `frontend/src/services/CalendarService.test.ts`（新增）
- `frontend/src/lib/fetcher.test.ts`
- `docs/harness-execution/BATCH-00-execution.md`
- 未修改生产代码、依赖、数据库迁移或外部系统状态。

## 3. Verification

| 命令 | 退出码 | 结果 | 已知 warning/备注 |
|---|---:|---|---|
| `uv run --no-cache --directory backend pytest tests/acceptance/test_harness_baseline.py -q` | 0 | 7 passed | 测试在 app import 前固定 `DEBUG=false`，避免仓库 `.env` 的 `DEBUG=release` 破坏独立验收；22 个既有 warning |
| `$env:DEBUG='false'; uv run --no-cache --directory backend pytest -q` | 0 | 494 passed | 110 个既有 warning |
| `uv run --no-cache --directory backend ruff check app tests` | 0 | passed | All checks passed |
| `pnpm.cmd --dir frontend exec vitest run src/services/CalendarService.test.ts src/lib/fetcher.test.ts` | 0 | 2 files, 5 tests passed | 使用 `pnpm.cmd` 绕过 PowerShell script policy |
| `pnpm.cmd --dir frontend lint` | 0 | passed | 99 个既有 warning，0 errors |
| `pnpm.cmd --dir frontend typecheck` | 0 | passed | 无输出 |
| `pnpm.cmd --dir frontend build` | 0 | passed | Next.js 16.1.6 build 完成 |
| `DEBUG=false python -c "from app.main import app; ..."` | 0 | backend app import smoke passed | 未启动外部服务 |

未运行真实 provider、真实 qB、外部网络和生产部署流程：任务明确禁止外部副作用；fake/local characterization 已覆盖 BATCH-00 验收范围。

## 4. Review

Review 按 `docs/code-review.md` 审查完整未提交变更，包含新增文件、执行记录、scope、secret/payload 扫描、`git diff --check` 和全部验证结果。Review 阶段只审查，不修改代码。

### Remediation round 1

首轮 Review 发现一个 medium finding：验收测试在仓库默认 `.env`（`DEBUG=release`）下无法独立 collection。修复方式是在测试导入 app 配置之前显式设置测试进程的 `DEBUG=false`，未修改生产配置或生产代码。修复后重新运行了 acceptance、后端全量 pytest、ruff、前端定向测试、lint、typecheck 和 build。

```yaml
review_result:
  batch: BATCH-00
  kind: batch
  verdict: pass
  summary: "完整未提交 diff 与任务边界复核通过；无 blocker、critical、high 或未处理 medium finding。"
  findings: []
  reviewed_commands:
    - "git status --short"
    - "git diff --check"
    - "git diff --stat"
    - "git diff"
    - "uv run --no-cache --directory backend pytest tests/acceptance/test_harness_baseline.py -q"
    - "uv run --no-cache --directory backend ruff check app tests"
    - "pnpm.cmd --dir frontend exec vitest run src/services/CalendarService.test.ts src/lib/fetcher.test.ts"
    - "pnpm.cmd --dir frontend lint"
    - "pnpm.cmd --dir frontend typecheck"
    - "pnpm.cmd --dir frontend build"
  reviewed_files:
    - "backend/tests/acceptance/test_harness_baseline.py"
    - "backend/tests/memory/test_service_typed.py"
    - "frontend/src/services/CalendarService.test.ts"
    - "frontend/src/lib/fetcher.test.ts"
    - "docs/harness-execution/BATCH-00-execution.md"
  deferred_findings:
    - "当前 qB 匿名访问基线仍是已知 G-P0-01 风险，交由 BATCH-01 修复。"
    - "Memory 不可信文本写入仍是已知风险，交由后续 Memory trust/redaction Batch 修复。"
```

Remediation rounds: 1   
Review verdict: `pass`

## 5. Handoff

```yaml
batch_result:
  batch: BATCH-00
  status: completed
  commit: a398da8
  tasks_completed:
    - TASK-HARNESS-000
  tests:
    passed:
      - "backend full pytest: 494"
      - "BATCH-00 acceptance: 7"
      - "frontend targeted: 5"
      - "backend ruff"
      - "frontend lint"
      - "frontend typecheck"
      - "frontend build"
    failed: []
    skipped:
      - "real provider/qB/external-network flow: forbidden by task scope"
  review:
    verdict: pass
    rounds: 1
    deferred_findings:
      - G-P0-01 qB anonymous access
      - Memory untrusted text persistence
  changed_files:
    - backend/tests/acceptance/test_harness_baseline.py
    - backend/tests/memory/test_service_typed.py
    - frontend/src/services/CalendarService.test.ts
    - frontend/src/lib/fetcher.test.ts
    - docs/harness-execution/BATCH-00-execution.md
  unresolved_risks:
    - "本 Batch 只建立当前行为基线，不声称 Harness 重构已完成。"
  next_batch: BATCH-01
```
