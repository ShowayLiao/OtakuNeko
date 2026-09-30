# Harness Execution Records

本目录保存每个 Harness Batch 的实际执行记录。它与审计文档、任务文件和实现代码的职责不同：

- `docs/harness-audit/` 记录源码事实、风险和 Gap；
- `docs/harness-tasks/` 记录允许实施的目标、范围和验收条件；
- `docs/harness-execution/` 记录实际执行过的命令、退出码、变更、发现和最终 Review。

## 文件命名

```text
BATCH-XX-execution.md
```

只有开始执行某个 Batch 时才创建对应记录。当前仓库的 `BATCH-00–13` 仍由任务索引管理；没有已批准的活动 Batch 时，不要创建虚假的执行记录。

## 必须记录

1. Preflight：分支、commit、工作区状态、前置 Batch 和文件边界；
2. 基线：实际测试、lint、typecheck、构建或 Eval 命令及结果；
3. Implementation：每次变更、源码与文档不一致、兼容开关；
4. Verification：完整命令、退出码、通过/失败/跳过数量、已知警告；
5. Review：完整 diff、Finding、verdict 和 remediation round；
6. Handoff：变更文件、回滚方式、未解决风险和下一批次。

使用 [`TEMPLATE.md`](TEMPLATE.md) 创建记录。记录中不得写入 Secret、Token、密码、完整用户数据、完整 BYOK 或 raw provider payload。
