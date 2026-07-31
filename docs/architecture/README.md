# Architecture Documentation

本目录保存 OtakuNeko Agent Harness 的稳定架构约束和边界说明。

## 文档职责

- [`standard-agent-harness-reference.md`](standard-agent-harness-reference.md)：本仓库执行 Harness 重构时的项目级规范入口。
- [`../standard-agent-harness-reference-and-codex-audit-guide.md`](../standard-agent-harness-reference-and-codex-audit-guide.md)：完整的通用参考架构、审计方法和任务编写指南。
- [`../harness-audit/`](../harness-audit/)：基于当前源码形成的审计事实、Gap、目标架构和迁移建议。

项目级规范优先说明 OtakuNeko 当前真实边界；通用参考文档提供术语、成熟度模型和审计模板。两者冲突时，以源码事实和项目级任务约束为准，并把不一致记录到对应执行记录。

## 当前成熟度

审计结论为 Level 1.5：LangGraph Agent Loop 已可运行，`backend/app/harness` 已具备局部 Runtime、Capability、Model Gateway、Policy、Checkpoint 和 Trace 能力，但聊天主路径尚未形成统一的 durable Run Coordinator。

当前重构批次按 [`../harness-tasks/INDEX.md`](../harness-tasks/INDEX.md) 顺序推进，一次只实施一个 Batch。
