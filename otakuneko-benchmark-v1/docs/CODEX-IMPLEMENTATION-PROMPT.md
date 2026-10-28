# 发给 VS Code Codex 的实施任务

你正在改造 OtakuNeko 仓库。我希望建立一套 **Anime Agent Benchmark v1**，用于每次 Harness 修改后调用**真实模型**测试完整动漫 Agent Loop 的端到端能力。请直接审计、设计、实现、验证、Review，分批完成；不要只回复建议，不要无条件声明测试通过。

## 第一优先级：先审计我现在的代码

仓库可能已有两个 live benchmark 题目（收藏/搜索路由，以及没有评分时选择推荐 specialist）。定位其源码、测试 Runner、模型 API 连接、模型选择逻辑、Mock/Stub 工具、Router/Capability/Specialist、日程与收藏读写、权限确认、多轮会话与 memory/DB 实现。当前分支代码才是事实，README 不是权威。优先扩展当前 benchmark 框架，避免创建重复执行框架。将审计结果写到 `docs/benchmarks/anime-agent-audit.md`，包括：可复用组件、缺失能力、执行风险、预期变更文件、现有测试命令。

## 交付规范

请阅读我提供的包：
- `docs/RFC-ANIME-AGENT-BENCHMARK.md`
- `cases/anime_benchmark_v1.jsonl`
- `fixtures/*.synthetic.json`

以上路径指本指令所附 benchmark 设计包中的文件；导入仓库时请采用适合现有结构的路径。12 个场景要具备唯一 ID、版本化 fixtures、case runner、hard assertion、可选语义判分、JSON + Markdown report、Trace、隔离环境、成本/时限限制；未完成时严格标记 unsupported。

### 不可让步的实现约束

1. **真实 LLM**：live 模式必须走仓库**现有真实模型 SDK、真实 AgentRuntime、Router、Tool/Capability/Specialist**。虚拟化只允许发生在模型之外的工具后端、沙盒数据库、搜索结果快照。严禁用 mock LLM、硬编码输出、自动通过的 judge 来冒充 live 结果。
2. **绝对隔离**：使用测试账户/namespace、全新 SQLite 或测试数据库、测试日历、测试 memory/checkpoint/cache。所有外部写工具在 benchmark 模式必须默认拒绝或指向测试替身；禁止访问真实用户收藏、真实 API 写权限和真实日历。每个 case / repeat 运行前 reset，执行结束清理。
3. **生产路径一致**：不为 Benchmark 添加隐藏的模型 prompt 提示答案；不把 expected/oracle 暴露给 Agent；不要为固定题强制特殊 Tool 路由；普通用户功能应完全不变。
4. **真实断言**：推荐的数量、候选 ID、过滤条件、收藏状态、日程冲突和时长、重复写入、确认权限、异常恢复都要通过实际输出与状态快照核验。未实现断言直接标记 `UNSUPPORTED`，不得跳过或当 PASS。
5. **Tool 攻击与故障**：错误注入仅通过 Tool adapter 或 fake external source。断言故障真正命中了实际 Tool call，否则该 case 记作无效，而非通过。
6. **多轮**：同一场景跨轮保留 session；跨会话 memory 在测试 user scope 共享，但不泄露到其他 user。审批操作必须遵守原始生产审批流程，不能用测试器直接绕过确认。
7. **报告**：逐 case 输出 PASS/FAIL/ERROR/SKIP/UNSUPPORTED、hard check 明细、可选 quality score、tool+LLM calls、timing、usage/cost（有数据才记录）、当前模型、provider、Git commit、fixture version/hash、失败原因和经过脱敏的 trace 路径。
8. **预算与安全**：真实模型运行必须显式 opt-in；无 API Key/连不通端点时明确报错或跳过，不可 fallback mock 后标记 live。限制 steps/requests/time/cost。敏感 token/Headers 不能出现在 Trace。默认 CI 不需要真实 key。
9. **合理的结果判定**：端到端任务以状态和约束为主，不强制精确 Tool 路由；路由精确性由已有单测负责。主观质量分和硬失败分别报告，安全与状态失败不可通过平均分掩盖。

## 分批执行；每批自行 Test + Review + 修复

**Batch 0（审计）**：上述系统现状、风险、差距、实施方案与变更点。审计中发现与本文冲突，以实际代码为准，并在报告解释调整。

**Batch 1（最小真模型闭环）**：接入真实 Agent 模型调用、隔离收藏 fixture、reset 机制、Trace、状态 oracle、报告。至少实现并验证 ANIME-001 和 ANIME-005；证明 token/key 隔离。

**Batch 2（搜索与多工具）**：实现 ANIME-002/003/004/007/008/011，包含可重放搜索快照、模拟日历与审批、工具超时、攻击载荷。

**Batch 3（多轮复杂用例）**：实现 ANIME-006/009/010/012，处理多轮重新规划、实体消歧、跨会话记忆与综合工作流。

**Batch 4（回归门禁）**：建立 smoke/regression/full 选择、重复 N 次统计、基线版本比较、Windows PowerShell 友好的命令、无秘钥 CI 的静态检查、文档、边界测试。

每批运行本地适用测试和静态检查，做 Code Review 并修复问题再继续。若当前环境没有可用的真实模型 API Key，不允许假称真实模型测试成功；实现测试基础设施并汇报被阻塞项、如何由我在本地跑真实模型，完整输出可执行命令。不要因为无法调用外部服务就改为假的 live benchmark。没有完成的 batch 不要隐瞒。

## 最后交付

1. 代码和 fixtures/cases 已被纳入仓库内合适位置；旧 live benchmark 不回归。
2. `docs/benchmarks/anime-agent-audit.md` + 新的 `README`/运行手册。
3. 每个 Case 的自动判分状态及未覆盖的原因。
4. 运行 `smoke` 和 `regression` 的 PowerShell 命令、模型/预算选择说明。
5. 一次真实运行的脱敏报告（**只有确实调用真实 LLM 时才提供**）。否则提供 `NOT_RUN` / blocked 结果而非编造分数。
6. 最终变更清单、可复现验证命令、残余风险、Review 结果，并在结尾说明下一步优先改进项。

请开始执行 Batch 0→4，不要停在方案设计。如果确有实现障碍，保证已完成代码、测试、审计报告真实可用，并明确列出阻塞原因。
