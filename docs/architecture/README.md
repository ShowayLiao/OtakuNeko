# Architecture Documentation

本目录保存 OtakuNeko 的长期架构约束和必要开发规范，不保存个人计划、审计明细或验证记录。

## 规范入口

- [项目级 Harness 规范](standard-agent-harness-reference.md)：Runtime ownership、可信身份、受控调度及真实实现边界。
- [通用 Harness 参考与审计指南](standard-agent-harness-reference-and-codex-audit-guide.md)：术语、目标模型、审计方法与任务模板。
- [Runtime 目标架构](agent-runtime-target-architecture.md)：组件边界、契约及迁移退出条件；不能替代当前源码证据。
- [Code Review 规范](code-review.md)：审查输入、证据要求、严重度和验收门槛。
- [仓库协作指引](../../AGENTS.md)：任务范围、验证命令、Git 规则及本地资料读取条件。

源码和真实验证优先于架构目标、历史审计或文件命名。新克隆只依赖随仓库分发的规范和用户提供的当前任务；不得凭空补造不存在的 Batch 或执行记录。

## Git 文档边界

`docs/` 只分发本目录和 [changelog](../changelog/archive.md)。architecture 中遗留的 `a-l1-01-test-matrix-plan.md` 与 `a-l1-01-test-matrix-report.md` 属于历史验证记录，也仅保留本地。

审计、任务、执行记录、质量报告、原始测试输出、截图和个人资料由 `.gitignore` 忽略；取消跟踪时保留本地文件。需要交付的运行证据使用单独 artifact，新增架构说明不得夹带这些材料或把它们作为必读链接。

本地历史材料存在时可以辅助核对，但不随 Git 分发。用户明确要求执行 Batch 时，仍必须具备任务范围、依赖、验收与回滚信息；缺少必需信息时停止该 Batch 实施。取消跟踪不会清除已有 Git 历史。
