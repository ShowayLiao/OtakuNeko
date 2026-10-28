# MIGRATION：OtakuNeko → 独立 Harness Core 实施基线

> **Status:** Approved migration approach, not an execution log.  
> **前提：** 先按 [`ARCHITECTURE.md`](../../ARCHITECTURE.md)、[`CONTRACTS.md`](../../CONTRACTS.md)、[`ADR-0001.md`](../adr/ADR-0001.md) 搭新 Core；原仓库是实现参考和外部业务服务，不是新 Core 的依赖。  
> **证据来源：** 2026-10-28 五份 Harness Foundation Audit；仅静态分析，未执行代码测试。

## 1. 目标与禁止事项

**目标：** 独立仓库、可独立安装测试的 Harness Kernel；先通过 Fake 模型/记忆/工具完成多轮循环，再引入 durable runtime 与旧后端 Adapter，最后以 Run owner 分流替换旧 Agent 路径。

**禁止：** 直接复制 `backend/app/harness` 整个目录；Core import 业务 ORM/FastAPI/模型 SDK；使用旧数据库私有表作为隐式 API；旧新 Runtime 同时执行真实写请求；未验证就标记 CI PASS；未经明确策略将匿名请求接入共享 Provider key；将 raw reasoning 透传 SSE/Event/Trace。

## 2. 新仓库建议目录

```text
harness-core/
  ARCHITECTURE.md
  CONTRACTS.md
  pyproject.toml
  src/harness_core/
    contracts/        # versioned, typed, JSON-safe; no business/SDK dependencies
    runtime/          # session/run/step references; sole Run control
    loop/             # one bounded decision strategy
    context/          # builder, budget, compaction policy
    models/           # gateway port, model types
    capabilities/     # definition and static Registry
    execution/        # Dispatcher, invocation, result normalization
    policy/           # policy / approval contracts
    state/            # journal, RunState, checkpoint ports
    events/           # safe durable/ephemeral event contracts
    memory/           # MemoryReader port only
    observability/    # safe trace/metric projection contracts
  adapters/
    model/             # scripted Fakes; real provider adapter outside Core
    memory/            # Fake, then authorized SQL/keyword adapter
    state/             # InMemory, then durable transactional adapter
    capability/        # Fake, then OtakuNeko service adapter
    transport/         # CLI/HTTP/SSE, separate package if useful
  tests/
    unit/
    contracts/
    acceptance/
    integration/
    security/
    fixtures/
  evals/
    datasets/
    baselines/
  docs/
    adr/ADR-0001.md
    migration/MIGRATION.md
    architecture/
    runbooks/
  .github/workflows/
```

目录只表达边界；不用为每个名词创建没有实际消费者的类。`src/harness_core` 与 `adapters` 的包边界必须通过自动化 import check 验证。

## 3. 旧代码参考方式与映射

| 旧实现 / 证据位置 | 新实现策略 | 要迁移的**行为**，不是目录 |
|---|---|---|
| `backend/app/harness/runtime.py` | **Rewrite boundary**：拆 Runtime 与 Loop | 有界循环、模型工具观察、错误/取消/预算语义 |
| `backend/app/harness/decision_parser.py` | **Adapt** 为 Decision validator | 明确解析、拒绝伪造身份/权限和未知 Decision |
| `backend/app/harness/model_gateway.py`, `model_types.py` | **Adapt** 为 Provider-neutral port/types | 流式/工具/usage/errors；隔离 vendor SDK 和 reasoning |
| `backend/app/capabilities/types.py`, `registry.py` | **Adapt** 为纯数据 Registry | Schema、版本、风险、可见能力过滤 |
| `backend/app/harness/dispatcher.py`, `capability_adapter.py` | **Rewrite execution seam** | schema/Policy/timeout/幂等/正常化；外部业务 Adapter 负责运行 |
| `backend/app/harness/context_manager.py` | **New Context Engine**，参考 provenance | source/trust 标记、界限和 hash；补齐历史/工具/记忆和预算 |
| `backend/app/harness/persistence/`, `checkpoint.py` | **Rewrite portable journal/checkpoint** | Run/Event、lease/重启测试；不得复制多存储不一致问题 |
| `backend/app/memory/` | **Keep External / Adapt Reader** | SQL + BM25 查询经验、提取/合并；不得把记忆生命周期放入 Core |
| `backend/app/trace/`, `backend/evals/` | **Adapt behaviors and tests** | 关联、脱敏、离线 Fake 全链路回归 |
| OtakuNeko anime/collection/calendar domain service | **Keep External** | 现有业务身份/资源授权、业务事实、REST CRUD |

每个工作包：**先读新 Contract → 再读旧代码与旧测试 → 提取行为约束 → 在新包实现 → Fake/contract/security tests → architecture review**。旧类名、目录层级、依赖对象不得成为隐式接口约束。

## 4. 可执行批次与验收标准

### P0：创建规范和工程门禁（不接旧后端）

| Batch | 任务 | 验收证据 |
|---|---|---|
| **B00** | 建新仓库、四份基线、`pyproject.toml`、README/贡献约束、最小包安装 | Clean clone 可执行本地安装和测试；无旧仓库路径依赖 |
| **B01** | 版本化 JSON-safe Contracts：ExecutionContext、Session/Run/Step、Decision、Model/Tool、Context、Memory、State/Event/Checkpoint/Approval | Round-trip + incompatible version tests；authority pollution 被拒绝 |
| **B02** | Ports、Fake Providers、Architecture dependency gate、Ruff/typecheck/pytest/CI | Offline gate 禁止网络和真实密钥；导入违规则 FAIL；全部 Fake 有使用方 |

### P1：最小可运行 Harness

| Batch | 任务 | 验收证据 |
|---|---|---|
| **B03** | RunState machine、RunBudget、cancel command、InMemory journal/events | 合法/非法状态转移；terminal 不可改；预算不重置 |
| **B04** | ModelGateway port + 两个有差异的 scripted Fake、provider feature negotiation、error normalization | 同一 conformance suite 全通过；原始 SDK chunk 不越界 |
| **B05** | 静态 Registry、Decision validator、Dispatcher、基础 deny-by-default Policy、Fake read Tool | 未注册/越权/非法 args/超时都拒绝；工具输出有界且为 untrusted |
| **B06** | Context Builder、简单 Token Budget、Fake MemoryReader、`ContextSnapshot` provenance | 每次模型调用都经 Context；工具和 Memory 注入不能伪造 system 指令 |
| **B07** | 单 Loop + AgentRuntime 端到端 Fake Vertical Slice、Event 安全投影 | `create run → model invoke → anime.search → observation → final`；错误/取消/预算测试通过 |
| **B08** | 可选最小 local CLI/HTTP/SSE adapter 与断线/重连实验 | 不重发 Run；核心与传输职责分离；P1 不承诺跨进程恢复 |

**P1 Exit:** `harness_core` 不导入 FastAPI/ORM/SDK/旧项目；无网络无 key 完成端到端；使用两个 Fake Model；Trace/Event 不含 canary secrets/reasoning；Code Review + Architecture Compliance Review 均通过。

### P2：持久化、安全和记忆增强

| Batch | 任务 | 验收证据 |
|---|---|---|
| **B09** | 持久 RunJournal、invocation intent/result、idempotency、unknown_outcome | crash before/after external effect；同 key 不重复写；无法确认则待对账 |
| **B10** | Versioned Checkpoint、recovery、lease/fencing（按部署能力）、event replay | kill/restart/duplicate resume；Run owner 和 sequence 不分裂 |
| **B11** | ApprovalRequest/Decision、args/resource digest、过期、拒绝、resume reauthorize | 改参/跨 owner/过期 approval 全拒绝；批准后只执行对应动作 |
| **B12** | 正式 Context selection、compaction、token budgeting；Memory SQL/keyword Reader | 原始 Transcript 不丢；按 owner/tenant 过滤；无向量服务也能检索 |
| **B13** | 外部 Memory Service lifecycle（若在本项目范围内）或独立集成其 Extraction/Consolidation 接口 | 不阻塞主 Loop；可追溯、纠正、删除、Profile 可重建；无越权记忆 |
| **B14** | Safe observability、Run/Model/Tool/Approval correlation、replay UI adapter、隐私全链 Canary | 所有输出 sink 无 raw reasoning/secret；Trace 不作为状态源 |

**P2 Exit:** 持久化故障注入、授权、approval、tenant、recovery、duplicate side-effect、事件回放和隐私测试均有 CI 实际结果；支持何种部署规模与恢复保证必须书面说明。Memory Service 的完整用户画像可作为独立后续交付，不应阻塞已验证的执行内核。

### Integration：接入旧服务并灰度切换

| Batch | 任务 | 验收证据 |
|---|---|---|
| **B15** | Backend Adapter：只读 anime search/detail，service-to-service identity | 业务 API/资源层重验授权；Harness 不 import 旧 ORM |
| **B16** | 旧 SSE/Event characterization 与新旧 BFF projection、Run owner index | 旧 UI 可消费兼容事件；断线 replay 不重复执行工具 |
| **B17** | 只读/合成数据 Shadow + 独立真实模型 Eval（可选） | 数据隔离，无双写；记录质量、成本、工具选择差异 |
| **B18** | 按 Run owner 的 Canary 与 Rollback，之后一次开放一个受控 write capability | 新旧不同时执行同一个真实副作用；审批、幂等、未知结果对账成功 |

## 5. CI、Review 与每批完成条件

**建议的 CI Job 类别：**

1. Format/lint/typecheck + clean package build/install。
2. Import boundary + versioned contract/JSON/schema conformance。
3. Unit state/Decision/Context/Policy tests；默认强制禁用 outbound network。
4. Scripted Fake Model + Fake Memory + Fake Tool 通过**真实 Runtime 入口**的 deterministic acceptance。
5. Security canaries 覆盖 API/Event/SSE/Trace/log/Eval；伪造 owner/tenant/role/approval 测试。
6. P2 隔离数据库 + crash injection + lease/replay + duplicate effect tests；单独 Job。
7. Live provider benchmarks 仅在显式授权、预算与隔离数据下运行；不作为基本正确性的唯一证据。

**每个 Codex Batch 的提交要求：**

- 先明确本批次触及的 Contracts、修改理由、实现步骤与实际测试命令。
- 代码实现后自审：功能、异常路径、安全、依赖方向、命名/所有权、隐私、版本兼容。
- 记录 `PASS / FAIL / NOT RUN` 及具体退出码和测试限制。不能以“已有测试文件”代替实际通过。
- 只提交本 Batch 的相关文件；发现基础架构冲突，先提 ADR/Contract 变更再编码。
- 不自动清理用户工作区、不重置不相关改动；按用户 Git 策略创建 PR/commit。

## 6. 前端和业务路由策略

- **A — Deterministic API**：收藏列表、日程 CRUD、设置 → 继续通过旧 Backend 的普通 API。
- **B — Agent-driven**：复杂动画研究/推荐、工具组合 → 新 Harness Run，工具通过服务 Adapter。
- **C — Hybrid**：模型推荐 + 用户在 UI 明确点击收藏/排班 → 可走普通业务 API；若用户明确指示 Agent 代操作，则按授权/审批/幂等走 Dispatcher。

前端只能访问经身份/owner 检查的 Run/Event/Approval API。内核事件与 UI SSE 的表示由 Transport Adapter 投影；未知事件不应破坏 terminal/cancel 处理。

## 7. Legacy → New cutover 和回滚

1. **冻结旧行为样例**：旧 `/api/v1/chat`、事件名称/游标、取消/恢复、read/write Tool 和错误边界，使用合成数据。旧业务 API 暂不改。
2. **开发新 Core + Fake**：独立运行，不链接 OtakuNeko ORM/业务私有类型。
3. **只读 Adapter**：验证身份/作用域/错误/超时等合同；保留 Domain Service 的资源 ACL。
4. **Shadow 仅只读或完全隔离**：不复制真实用户敏感数据到影子日志；禁止同时执行真实副作用。
5. **Canary 在创建 Run 时固定 `run_owner=legacy|new`**：同一 Run 的 cancel/resume/replay 都回到同一 owner。用户切换后，旧 Run 也不跨 Runtime 恢复。
6. **写路径逐能力开放**：stable idempotency key end-to-end；每一个 capability 都有审批/授权/对账测试；新旧不能双写。
7. **回滚**：停止向新 Runtime 分配新 Run；旧 Run 继续由旧 Runtime 完成/取消；新 Run 继续由新 Runtime 安全处理或中止。不能只复制 ID 就移交未完成 Run。

## 8. 已知高风险事项（必须追踪）

- 旧系统存在模型 `reasoning_content → thinking_chunk → SSE/durable event` 的已确认路径；新 Core 不得复制，旧系统另开安全修复任务。
- 旧 chat 的可选认证与服务端 Provider key 可能引发匿名配额问题；新 Runtime 首版默认认证访问。
- 旧 Run/Event 和 SQLite Checkpoint 分存不同边界，单 Worker 限制不能当作分布式恢复证明。
- 当前测试报告只有**静态审计**，不能声称旧项目 CI、恢复、安全或真实 Benchmark 已验证通过。
- 当前原审计报告可能在旧仓库被 `.gitignore` 忽略；新仓库应把**批准的基线文档**纳入 Git 跟踪，引用旧审计时注明快照日期与源码版本，不依赖未提交的旧工作区作为唯一证据。

## 9. 第一条验收场景（作为所有批次的锚）

```text
Authenticated synthetic principal P
  -> CreateRun(session S, "根据偏好推荐动画")
  -> Fake MemoryReader returns scoped anime preference
  -> ContextSnapshot with trust/provenance and token budget
  -> Scripted Fake Model proposes anime.search(read-only)
  -> Registry + Policy + Dispatcher validates, logs intent, runs Fake Tool
  -> ToolResult is passed as untrusted observation
  -> Scripted Fake Model returns final answer
  -> Runtime transitions succeeded and emits safe durable final event
  -> Event replay and Result agree; no real network, DB, keys or user data
```

再通过差异 Fake Provider、非法参数、伪造身份、拒绝、预算耗尽、取消、工具错误与重复调用变体证明框架不是空接口拼装。
