# Architecture Documentation

## Target architecture

- [`agent-runtime-target-architecture.md`](agent-runtime-target-architecture.md): the persisted AgentRuntime-only target topology, contracts, ownership rules, current implementation gap, and migration exit criteria.

- [`../harness-audit/13-unified-runtime-consolidation-audit.md`](../harness-audit/13-unified-runtime-consolidation-audit.md): current gap audit after the first unified-runtime task package.
- [`../harness-audit/14-target-architecture-gap-audit.md`](../harness-audit/14-target-architecture-gap-audit.md): target exit criteria matrix and remaining architecture closure gaps.
- [`../harness-tasks/UNIFIED-RUNTIME-CONSOLIDATION/`](../harness-tasks/UNIFIED-RUNTIME-CONSOLIDATION/): follow-up tasks for migrating the primary chat loop and retiring legacy control paths.

本目录保存 OtakuNeko Agent Harness 的稳定架构约束和边界说明。

## 文档职责

- [`standard-agent-harness-reference.md`](standard-agent-harness-reference.md)：本仓库执行 Harness 重构时的项目级规范入口。
- [`../standard-agent-harness-reference-and-codex-audit-guide.md`](../standard-agent-harness-reference-and-codex-audit-guide.md)：完整的通用参考架构、审计方法和任务编写指南。
- [`../harness-audit/`](../harness-audit/)：基于当前源码形成的审计事实、Gap、目标架构和迁移建议。

项目级规范优先说明 OtakuNeko 当前真实边界；通用参考文档提供术语、成熟度模型和审计模板。两者冲突时，以源码事实和项目级任务约束为准，并把不一致记录到对应执行记录。

## 当前成熟度

当前审计结论为 Level 4：启用的主聊天路径已由 AgentRuntime 控制，并通过 ModelGateway、DecisionParser、Policy/Approval、Dispatcher 和 canonical Run/Event 持久化；LangGraph 兼容回滚、未迁移 specialist 和 SQLite 单 worker 边界仍明确保留。详细证据见 [`14-target-architecture-gap-audit.md`](../harness-audit/14-target-architecture-gap-audit.md) 与 BATCH-20～26 execution records。

当前重构批次按 [`../harness-tasks/INDEX.md`](../harness-tasks/INDEX.md) 顺序推进，一次只实施一个 Batch。
