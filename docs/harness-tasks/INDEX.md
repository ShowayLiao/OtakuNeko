# OtakuNeko Harness 重构任务索引

> 本目录是基于标准 Harness 参考文档 §25 和 `docs/harness-audit/` 生成的执行任务；本轮只生成计划，不修改生产代码。

## 依赖与批次顺序

```text
BATCH-00 基线与回归样本
   ↓
BATCH-01 qBittorrent P0 认证封堵
   ↓
BATCH-02 统一 Run/Decision/Invocation/Event 契约
   ↓
BATCH-03 Capability Registry / Schema / Allowlist
   ↓
BATCH-04 Model Gateway / Usage / Error
   ↓
BATCH-05 Runtime Coordinator / Budget / Cancellation contract
   ↓
BATCH-06 Run / Invocation / Event 持久化
   ├─→ BATCH-07 SSE 断线补拉（后端投影 + 前端消费）
   └─→ BATCH-08 Checkpoint / 重启恢复 / 取消传播
          ↓
       BATCH-09 qBittorrent 幂等与补偿
          ↓
       BATCH-10 Schedule 模型能力的 Principal / Approval
          ↓
       BATCH-11 Collection HTTP 写入幂等
          ↓
       BATCH-12 Context / Memory 信任边界
          ↓
       BATCH-13 Observability / Eval 门禁
```

依赖关系来自审计 Gap：统一契约先于 Registry、Model 和 Runtime；Run/Event 存储先于 SSE 补拉和重启恢复；可信 Principal/Policy 先于写能力幂等。参考批次原则见参考文档 §23–§24（参考文档:1888-2005），垂直切片要求见参考文档:1908-1916。

## Gap → 任务映射

| Gap | 首个处理任务 | 后续任务 | 说明 |
|---|---|---|---|
| G-P0-01 | TASK-HARNESS-001 | TASK-HARNESS-009 | 先封堵匿名 qB 路由，再补 qB 幂等/补偿。 |
| G-P1-01 | TASK-HARNESS-002 | TASK-HARNESS-005 | 先冻结契约，再把 AgentRuntime 变为唯一 Coordinator；LangGraph 保留为 adapter。 |
| G-P1-02 | TASK-HARNESS-002 | TASK-HARNESS-003、010 | 先定义上下文/调用契约，再统一只读能力，最后接入 Schedule 写能力。 |
| G-P1-03 | TASK-HARNESS-006 | TASK-HARNESS-007、008 | 持久化 Run/Event 后才能支持重连和重启恢复。 |
| G-P1-04 | TASK-HARNESS-009 | TASK-HARNESS-010、011 | qB、Schedule、Collection 分开处理，避免一批重构全部写能力。 |
| G-P1-05 | TASK-HARNESS-004 | TASK-HARNESS-005 | provider usage 先统一，Runtime 再统一预算/取消。 |
| G-P1-06 | TASK-HARNESS-002 | TASK-HARNESS-006、007、013 | Event schema → durable store → projection/eval。 |
| G-P1-07 | TASK-HARNESS-003 | TASK-HARNESS-009、012 | Tool result 先版本化，再治理日志和 Memory trust。 |
| G-P1-08 | TASK-HARNESS-006 | TASK-HARNESS-008 | Run/Event 存储与 checkpoint/deployment 分开 PR。 |
| G-P1-09 | TASK-HARNESS-004 | TASK-HARNESS-013 | 先适配多模型，再纳入 Eval/费用门禁。 |
| G-P1-10 | TASK-HARNESS-012 | TASK-HARNESS-013 | Memory 单实现和 provenance 先于 Memory Eval。 |
| G-P1-11 | TASK-HARNESS-002 | TASK-HARNESS-005 | 统一 terminal error，再由 Coordinator 唯一落状态。 |

## 任务目录

| 批次 | 单 PR 任务 | 目标 | 允许的变更面 |
|---|---|---|---|
| BATCH-00 | [TASK-HARNESS-000](BATCH-00/TASK-HARNESS-000.md) | 固定当前行为与测试基线 | 测试、Eval fixture、纯函数回归 |
| BATCH-01 | [TASK-HARNESS-001](BATCH-01/TASK-HARNESS-001.md) | 修复 qBittorrent P0 | qB API 认证依赖和安全测试 |
| BATCH-02 | [TASK-HARNESS-002](BATCH-02/TASK-HARNESS-002.md) | 统一结构化契约 | Harness contracts 与 adapter 测试 |
| BATCH-03 | [TASK-HARNESS-003](BATCH-03/TASK-HARNESS-003.md) | 统一只读 Tool/Capability 元数据 | Registry、schema、allowlist |
| BATCH-04 | [TASK-HARNESS-004](BATCH-04/TASK-HARNESS-004.md) | 统一 Model Gateway 结果 | provider adapter、usage、error |
| BATCH-05 | [TASK-HARNESS-005](BATCH-05/TASK-HARNESS-005.md) | 唯一 Runtime Coordinator | runtime adapter、预算、终止 |
| BATCH-06 | [TASK-HARNESS-006](BATCH-06/TASK-HARNESS-006.md) | Run/Invocation/Event 持久化 | SQL Store、模型、迁移、Runtime hook |
| BATCH-07 | [TASK-HARNESS-007](BATCH-07/TASK-HARNESS-007.md) | SSE 断线补拉 | API projection、前端消费 |
| BATCH-08 | [TASK-HARNESS-008](BATCH-08/TASK-HARNESS-008.md) | checkpoint、重启和取消传播 | Graph adapter、部署配置、测试 |
| BATCH-09 | [TASK-HARNESS-009](BATCH-09/TASK-HARNESS-009.md) | qB 写入幂等和补偿 | qB service、idempotency adapter |
| BATCH-10 | [TASK-HARNESS-010](BATCH-10/TASK-HARNESS-010.md) | Schedule 写能力安全接入 | Principal、approval、idempotency |
| BATCH-11 | [TASK-HARNESS-011](BATCH-11/TASK-HARNESS-011.md) | Collection 写入幂等 | Collection API/service、测试 |
| BATCH-12 | [TASK-HARNESS-012](BATCH-12/TASK-HARNESS-012.md) | Context/Memory 信任治理 | Memory adapter、provenance、injection tests |
| BATCH-13 | [TASK-HARNESS-013](BATCH-13/TASK-HARNESS-013.md) | Observability/Eval 门禁 | Trace projection、metrics、回归门禁 |

## Post-BATCH-13 统一 Runtime 规划

当前 BATCH-00～26 均已有实际 execution record；状态以对应记录和源码为准，不代表当前存在活动 Batch。

审计基线：[`docs/harness-audit/12-post-batch13-current-audit.md`](../harness-audit/12-post-batch13-current-audit.md)

任务包：[`POST-AUDIT-UNIFIED-RUNTIME/README.md`](POST-AUDIT-UNIFIED-RUNTIME/README.md)

| 规划任务 | 目标 | 依赖 |
|---|---|---|
| [TASK-POST-AUDIT-001](POST-AUDIT-UNIFIED-RUNTIME/TASK-POST-AUDIT-001.md) | 主聊天接入 Decision / Dispatcher | 当前 contracts、Registry、Policy |
| [TASK-POST-AUDIT-002](POST-AUDIT-UNIFIED-RUNTIME/TASK-POST-AUDIT-002.md) | Runtime 唯一控制、取消与恢复 | 001 |
| [TASK-POST-AUDIT-003](POST-AUDIT-UNIFIED-RUNTIME/TASK-POST-AUDIT-003.md) | Capability、Tool、MCP 与副作用收口 | 001、002 |
| [TASK-POST-AUDIT-004](POST-AUDIT-UNIFIED-RUNTIME/TASK-POST-AUDIT-004.md) | Model、Memory、Checkpoint 与部署一致性 | 001、002、003 |
| [TASK-POST-AUDIT-005](POST-AUDIT-UNIFIED-RUNTIME/TASK-POST-AUDIT-005.md) | 主路径 Acceptance、Review 与 Hardening | 001～004 |

## Unified Runtime Consolidation 规划

POST-AUDIT-001～005 已建立基础边界，BATCH-19 / TASK-POST-AUDIT-006 已完成 Runtime-owned Decision Loop canary；严格目标架构仍要求完成后续 canonical persistence、ContextManager、shared recovery 和 legacy 退役。后续任务见 [`UNIFIED-RUNTIME-CONSOLIDATION/README.md`](UNIFIED-RUNTIME-CONSOLIDATION/README.md)，只有 execution record 标记为 started/completed 才代表活动 Batch。

| 任务 | 目标 | 依赖 | 状态 |
|---|---|---|---|
| [TASK-POST-AUDIT-006](UNIFIED-RUNTIME-CONSOLIDATION/TASK-POST-AUDIT-006.md) | 主聊天 Runtime-owned Decision Loop | POST-AUDIT-001～005 | BATCH-19 canary completed |
| [TASK-POST-AUDIT-007](UNIFIED-RUNTIME-CONSOLIDATION/TASK-POST-AUDIT-007.md) | Canonical Invocation / Result / Event pipeline | 006 | BATCH-22 completed |
| [TASK-POST-AUDIT-008](UNIFIED-RUNTIME-CONSOLIDATION/TASK-POST-AUDIT-008.md) | ContextManager 与 Memory/Provider trust boundary | 006、007 | BATCH-23 completed |
| [TASK-POST-AUDIT-009](UNIFIED-RUNTIME-CONSOLIDATION/TASK-POST-AUDIT-009.md) | Shared checkpoint、durable cancellation 与 worker recovery | 007、008 | BATCH-24 completed |
| [TASK-POST-AUDIT-010](UNIFIED-RUNTIME-CONSOLIDATION/TASK-POST-AUDIT-010.md) | Legacy bypass 退役、真实主 API Eval 与最终 hardening | 006～009 | BATCH-26 completed |

执行 runbook：[`docs/harness-execution/POST-AUDIT-EXECUTION-PLAN.md`](../harness-execution/POST-AUDIT-EXECUTION-PLAN.md)

## Target Architecture Closure 补充任务

基于 [`docs/harness-audit/14-target-architecture-gap-audit.md`](../harness-audit/14-target-architecture-gap-audit.md)，TASK-POST-AUDIT-011～013 用于补齐当前源码审计中尚未被 TASK-006～010 充分验收的模型取消、结果契约和 Provider 网络安全边界；对应的 BATCH-20、BATCH-21、BATCH-25 execution record 已存在，状态以记录和源码为准。

| 任务 | 目标 | 依赖 | 状态 |
|---|---|---|---|
| [TASK-POST-AUDIT-011](UNIFIED-RUNTIME-CONSOLIDATION/TASK-POST-AUDIT-011.md) | ModelGateway cancellation、timeout 与 provider error hardening | 006 | BATCH-20 completed |
| [TASK-POST-AUDIT-012](UNIFIED-RUNTIME-CONSOLIDATION/TASK-POST-AUDIT-012.md) | ResultNormalizer、schema、safe output 与 authority contract | 006、011 | BATCH-21 completed |
| [TASK-POST-AUDIT-013](UNIFIED-RUNTIME-CONSOLIDATION/TASK-POST-AUDIT-013.md) | Provider SSRF、egress allowlist 与 endpoint authorization | 011 | BATCH-25 completed |

统一执行计划：[`docs/harness-execution/TARGET-ARCHITECTURE-CLOSURE-EXECUTION-PLAN.md`](../harness-execution/TARGET-ARCHITECTURE-CLOSURE-EXECUTION-PLAN.md)

## 所有批次的共同约束

- 先添加失败测试或契约测试，再实现最小 adapter；不直接重写 LangGraph、全部 Tool 或业务 Service。
- 每个任务保持一个可审查 PR；任务之间不共享未提交的隐式接口，接口以任务文档中的字段名和状态枚举为准。
- 除明确列出的迁移任务外，不修改业务表；不升级依赖、不移动文件、不删除旧实现。
- 每批验收必须包含：应用可启动、相关测试通过、至少一个真实用户只读流程可用、回滚开关或兼容路径可用。
- BATCH-00 中把日历能力固定为纯前端 CSV/语音命令回归；当前没有证据表明 Agent 能直接写第三方 Calendar，因此不把日历伪造为现有 Agent Tool。
