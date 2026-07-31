# BATCH-03 执行记录

> Batch：`BATCH-03`
> Task：`TASK-HARNESS-003`
> 开始时间：`2026-07-31 23:22 Asia/Shanghai`
> 当前分支：`feature-harness`
> 起始 commit：`1e4f340acccf76495b18f594a23509a01720561e`
> 记录状态：`completed`

## 1. Preflight

### 工作区和前置条件

```text
git status --short: clean（仅存在 Git ignore/cache 访问警告）
git branch --show-current: feature-harness
git rev-parse HEAD: 1e4f340acccf76495b18f594a23509a01720561e
前置 Batch 及 commit: BATCH-00 95a7406；BATCH-01 9ffa22e；BATCH-02 1e4f340
当前任务允许修改: capabilities/types.py、registry.py、langchain_adapter.py；agents/registry.py、tools.py；mcp_server/entry.py；TASK-HARNESS-003 列出的测试和本执行记录
当前任务禁止修改: services、qB/collection/schedule 业务行为、agents/graph.py、Runtime、DB、frontend、Memory；不得启用写能力
```

### 权威资料

- `docs/architecture/standard-agent-harness-reference.md`
- `docs/standard-agent-harness-reference-and-codex-audit-guide.md`
- `docs/harness-audit/00-executive-summary.md` 至 `11-task-backlog.md`
- `docs/harness-tasks/INDEX.md`
- `docs/harness-tasks/BATCH-03/TASK-HARNESS-003.md`
- `docs/code-review.md`

### 基线命令

| 命令 | 退出码 | 通过 | 失败 | 跳过 | 警告/备注 |
|---|---:|---:|---:|---:|---|
| `$env:DEBUG='false'; uv run --no-cache --directory backend pytest tests/capabilities tests/agents/test_registry.py tests/mcp/test_entry.py tests/mcp/test_policy.py -q` | 0 | 80 | 0 | 0 | 21 warnings |
| `$env:DEBUG='false'; uv run --no-cache --directory backend ruff check app tests/capabilities tests/agents/test_registry.py tests/mcp/test_entry.py tests/mcp/test_policy.py` | 0 | - | 0 | - | clean |

## 2. 源码事实和不一致

| 文件/符号 | 实际行为 | 任务预期 | 处理方式 |
|---|---|---|---|
| `app.capabilities.types.ActionDescriptor` | 仅包含基础输入/权限/副作用字段 | 需要版本化公开元数据和输出契约 | 本 Batch 扩展兼容字段 |
| `app.capabilities.langchain_adapter.derive_tools` | 遍历所有已注册动作，包含写动作 | 只能从 Registry 派生安全公开工具 | 改为读取 Registry 公开定义并过滤写动作 |
| `app.mcp_server.entry.build_registry` | 入口重复注册四个能力 | Registry 应成为统一来源 | 改为调用 canonical factory，保持现有 ExposureMap |

## 3. 实施记录

### 变更范围

- 先新增契约、公开定义、只读 allowlist、工具派生和 MCP Registry 复用测试。
- 保留旧 `CapabilityResult.to_dict()` 和七个 legacy 工具名称；新增安全公开 envelope/校验接口。
- 不修改 capability service、ToolNode、Runtime、数据库或前端。

### 关键决策

- `ActionDescriptor` 新字段全部提供兼容默认值；副作用动作在公开定义层强制 `approval_required=True`。
- 公开 input schema 递归移除 `user_id`，可信身份只由后续受控执行上下文注入。
- Registry 默认公开定义只包含非副作用动作；显式 allowlist 只能进一步收窄，不能启用写动作。

### 兼容与回滚

- 兼容入口：`ActionDescriptor` 旧位置参数、`CapabilityResult.to_dict()`、`ALL_TOOLS` 七个名称、MCP 现有 read Exposure。
- 回滚：移除本 Batch 提交及其执行记录 finalization commit，不触碰前置 Batch。

## 4. Verification

| 命令 | 退出码 | 通过 | 失败 | 跳过 | 已知警告 |
|---|---:|---:|---:|---:|---|
| `$env:DEBUG='false'; uv run --no-cache --directory backend pytest tests/capabilities tests/agents/test_registry.py tests/mcp/test_entry.py tests/mcp/test_policy.py -q` | 0 | 89 | 0 | 0 | 21 warnings |
| `$env:DEBUG='false'; uv run --no-cache --directory backend ruff check app tests/capabilities tests/agents/test_registry.py tests/mcp/test_entry.py tests/mcp/test_policy.py` | 0 | - | 0 | - | clean |
| `$env:DEBUG='false'; uv run --no-cache --directory backend pytest` | 0 | 528 | 0 | 0 | 110 warnings |
| `$env:DEBUG='false'; uv run --no-cache --directory backend ruff check app tests` | 0 | - | 0 | - | clean |
| Registry/adapter 手工只读与写能力边界检查（`python -c`） | 0 | 1 | 0 | 0 | derived=8；current_time 成功；MCP exposure 保持 |
| `git diff --check` | 0 | - | 0 | - | clean |

未运行项目及原因：未运行 frontend lint/typecheck/test/build，因为本 Batch 只修改 backend，前端文件和协议未变；未运行真实外部 Anime/qB/数据库写操作，因为任务明确禁止实际业务副作用。

## 5. Review

```yaml
review_result:
  batch: BATCH-03
  verdict: pass
  summary: "完整未提交 diff 与受限路径审查通过；只读 Registry、公开 schema、可信身份注入和写能力 deny 边界满足任务要求。"
  findings: []
  reviewed_commands:
    - "git diff --check"
    - "uv run --no-cache --directory backend pytest"
    - "uv run --no-cache --directory backend ruff check app tests"
    - "Registry/adapter 手工边界检查"
  reviewed_files:
    - "backend/app/capabilities/types.py"
    - "backend/app/capabilities/registry.py"
    - "backend/app/capabilities/langchain_adapter.py"
    - "backend/app/agents/registry.py"
    - "backend/app/agents/tools.py"
    - "backend/app/mcp_server/entry.py"
    - "backend/tests/capabilities/test_action_contract.py"
    - "backend/tests/capabilities/test_registry.py"
    - "backend/tests/capabilities/test_tool_parity.py"
    - "backend/tests/agents/test_registry.py"
    - "backend/tests/mcp/test_entry.py"
    - "docs/harness-execution/BATCH-03-execution.md"
  deferred_findings: []
```

Review 检查项：无 blocker/critical/high/medium finding；未修改 services、Graph、Runtime、DB、frontend 或依赖；未发现 Secret/Token/用户数据进入 diff。

Remediation rounds：0

## 6. Handoff

```yaml
batch_result:
  batch: BATCH-03
  status: committed
  commit: 8488d32
  tasks_completed:
    - "ActionDescriptor 版本化风险/超时/重试/幂等/审批/Schema 元数据"
    - "CapabilityRegistry public definition 与只读 allowlist"
    - "LangChain/legacy Tool parity 与 trusted ExecutionContext 身份边界"
    - "MCP canonical Registry-backed read Exposure"
    - "CapabilityResult safe envelope、output schema 与 payload limit"
  tests:
    passed:
      - "backend targeted: 89"
      - "backend full: 528"
      - "backend ruff: pass"
      - "manual read/write boundary: pass"
    failed: []
    skipped: []
  review:
    verdict: pass
    rounds: 0
    deferred_findings: []
  changed_files:
    - "backend/app/capabilities/types.py"
    - "backend/app/capabilities/registry.py"
    - "backend/app/capabilities/langchain_adapter.py"
    - "backend/app/agents/registry.py"
    - "backend/app/agents/tools.py"
    - "backend/app/mcp_server/entry.py"
    - "backend/tests/capabilities/test_action_contract.py"
    - "backend/tests/capabilities/test_registry.py"
    - "backend/tests/capabilities/test_tool_parity.py"
    - "backend/tests/agents/test_registry.py"
    - "backend/tests/mcp/test_entry.py"
    - "docs/harness-execution/BATCH-03-execution.md"
  unresolved_risks:
    - "Registry/Schema 统一完成，但 Runtime 仍未成为唯一 Coordinator，按任务延后 BATCH-05。"
    - "Schedule approval/idempotency 真实执行接入延后 BATCH-10；本 Batch 未启用任何写能力。"
  next_batch: "按 INDEX 重新确认 BATCH-04 前置条件"
```
