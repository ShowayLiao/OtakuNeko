# BATCH-XX 执行记录

> Batch：`BATCH-XX`
> Task：`TASK-HARNESS-XXX`
> 开始时间：`YYYY-MM-DD HH:mm Asia/Shanghai`
> 当前分支：
> 起始 commit：
> 记录状态：`in_progress | completed | blocked`

## 1. Preflight

### 工作区和前置条件

```text
git status --short:
git branch --show-current:
git rev-parse HEAD:
前置 Batch 及 commit:
当前任务允许修改:
当前任务禁止修改:
```

### 权威资料

- `docs/architecture/standard-agent-harness-reference.md`
- `docs/standard-agent-harness-reference-and-codex-audit-guide.md`
- `docs/harness-audit/<相关文件>.md`
- `docs/harness-tasks/INDEX.md`
- `docs/harness-tasks/BATCH-XX/<任务文件>.md`
- `docs/code-review.md`
- 修改路径下更具体的 `AGENTS.md`

### 基线命令

| 命令 | 退出码 | 通过 | 失败 | 跳过 | 警告/备注 |
|---|---:|---:|---:|---:|---|
| `完整命令` |  |  |  |  |  |

## 2. 源码事实和不一致

| 文件/符号 | 实际行为 | 文档/任务预期 | 处理方式 |
|---|---|---|---|
| `path::symbol` |  |  | 修正 / 记录 / 阻塞 |

## 3. 实施记录

### 变更范围

- 修改：
- 新增：
- 未修改且明确保留：

### 关键决策

-

### 兼容与回滚

- 兼容入口或 feature flag：
- 回滚步骤：
- 已写入外部状态的人工核对方式：

## 4. Verification

| 命令 | 退出码 | 通过 | 失败 | 跳过 | 已知警告 |
|---|---:|---:|---:|---:|---|
| `完整命令` |  |  |  |  |  |

未运行项目及原因：

## 5. Review

Review 必须审查完整未提交 diff，且 Review 阶段不修改代码。

```yaml
review_result:
  batch: BATCH-XX
  verdict: pass | changes_required | blocked
  summary: ""
  findings: []
  reviewed_commands: []
  reviewed_files: []
  deferred_findings: []
```

Remediation rounds：

## 6. Handoff

```yaml
batch_result:
  batch: BATCH-XX
  status: committed | blocked
  commit: null
  tasks_completed: []
  tests:
    passed: []
    failed: []
    skipped: []
  review:
    verdict: pass | changes_required | blocked
    rounds: 0
    deferred_findings: []
  changed_files: []
  unresolved_risks: []
  next_batch: null
```
