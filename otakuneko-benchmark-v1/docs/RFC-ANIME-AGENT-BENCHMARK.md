# RFC: OtakuNeko Anime Agent Benchmark v1

状态：Proposed / 可用于交付 Codex 审计与实施  
日期：2026-10-26  
范围：用于开发回归的端到端真实模型 Agent Loop 基准，不替代单元测试和业务 API 测试。

## 0. 目的和不可误解的边界

目标：每次修改 Harness 之后，用**真实模型**在可重复、隔离的虚拟动漫世界里完成真实业务任务，衡量任务完成度、工具使用、协作、多轮状态、可靠性、资源成本，并与前一次基线对比。

必须复用生产 Agent 的真实入口和 Runtime、Router、Tool/Capability/Specialist 调用链。可替换收藏 DB、日历 DB、第三方搜索结果和异常注入，但不得替换生产 Agent loop 为按用例定制的假实现，更不得硬编码答案。

公开仓库 README 曾列出 `backend/`, `tests/`, `frontend/`、Bangumi、日历、收藏与多模型能力；这些只是初步证据，Codex 必须以**工作区当前代码**为准，尤其先定位当前已有的 live benchmark 两题、测试定义、Runner、配置读取、Tool Stub 机制与实际模型调用模式。优先扩展既有框架；除非审计证明不足，不要重造一套重复 Harness。

### v1 非目标
- 追求所有动漫事实的绝对客观得分；线上评价存在主观性。
- 在 PR 默认执行无限量付费模型调用。
- 测试真实用户收藏或写入真实个人日历。
- 强制模型走唯一固定 Tool/Router 分支。
- 为得高分而修改主 Agent 业务行为或绕过权限。

## 1. 分层测试

| 层 | LLM | 工具数据 | 目标 | 默认触发 |
|---|---|---|---|---|
| Unit / Integration | Fake | Mock | 逻辑、接口、异常 | 每次常规修改 / CI |
| **Live Smoke** | **Real** | **Frozen Fixtures** | 4 道高价值基础 loop | 每次 Agent 相关任务完成后（本地，显式开启） |
| **Live Regression** | **Real** | **Frozen Fixtures** | v1 全 12 道 | 合并前 / 有密钥的受控 CI |
| Live Stability | Real | Frozen Fixtures | 每题 3–5 次，看波动 | 每晚 / 重要版本 |
| Online Exploration | Real | 真实公开网络只读数据 | 发现真实世界问题 | 人工触发，不作为固定答案门禁 |

建议 Smoke 首批：ANIME-001、ANIME-003、ANIME-004、ANIME-007。若当前日历写入尚无安全沙盒，先标记 004 `UNSUPPORTED` 并阻止将其计为 PASS，不能转向真实日历写入。

冻结环境中的“实时模型”是指真实模型推理发生在运行时，不等于必须使用真实第三方搜索结果；搜索是被冻结的 fixture。在线探索与确定性回归应分开统计。

## 2. 推荐目录结构（Codex 先审计再决定）

```text
tests/
  agent_benchmark/
    cases/                    # case specs, versioned
    fixtures/                 # synthetic user/catalog/calendar/search
    adapters/                 # existing AgentRuntime, model provider, storage and search adapters
    evaluators/               # deterministic oracles and semantic judge
    runner.py                 # orchestration: setup/run/grade/teardown
    report.py                 # machine-readable + human-readable reports
    test_contracts.py         # no-API static integration tests
scripts/
  run_anime_benchmark.*       # optional Windows-friendly entrypoint
artifacts/agent-benchmark/   # gitignored, per run outputs, sanitized
```

请勿机械复制目录；适配现有 repo 风格、依赖和测试目录。不要创建第二个真实模型 SDK 通路，应使用现有模型客户端并让选择的 model/provider/base_url 显式进入报告。

## 3. Case 与 Fixture 契约

该包的 `cases/anime_benchmark_v1.jsonl` 是**用例规格**，而不是现在就能被现有 Runner 直接执行的文件。Codex 需把字段映射为仓库内部 case definition，或者保留 JSONL + 实现 schema 校验和 runner。

关键字段：

- `id`, `group`, `priority`: 稳定 ID / 分类 / 优先级。
- `environment`: 夹具版本、冻结时钟、时区、写入范围。
- `turns`: 真实用户消息及触发器；多轮场景必须共享该会话实际上下文。
- `tool_faults`: 仅作用于 Tool 适配层，不得修改 LLM 输出。
- `hard_checks`: 与业务状态、结果真实性和安全相关的确定性断言。
- `quality_checks`: 需要文本/证据评审的语义问题，支持人工抽查。
- `requires_confirmation`: 用例需要经过生产权限策略，只有收到必要确认才允许写入。
- `max_tool_calls`: 工具调用硬上限，防止死循环；Runner 还应设置 wall-clock timeout、模型请求次数和预算限制。

**数据隔离**：所有 fixture 都是虚构作品，名称和元数据不可作为真实动漫知识。collection 与 catalog 需要通过生产工具的读取接口暴露给 Agent；不可直接拼进系统提示词或让模型读到 oracle。

**时钟**：`2026-10-26T20:00:00+08:00`，日历样例在 2026-10-31、2026-11-07。定时规则使用 fixture 指定时区，不应取测试主机时区或系统实时时间。每次用例启动要重建全新 state 与 memory namespace。

**多轮触发**：
- `initial`：初始化后的第一条真实用户消息。
- `after_previous_assistant_final`：前一轮完成后继续同一会话。
- `after_assistant_confirmation_request`：检测到助手明确请求确认后再注入批准。不得无条件自动批准；若助手直接写入而未按生产权限策略进行，判失败。
- `new_session_same_test_user`：同一虚拟用户、不同会话 ID，但保留其测试命名空间中的持久偏好。

若确认行为在生产中由审批事件而非自然语言完成，Runner 必须走同一审批协议，不能偷偷直接写数据库。

## 4. Benchmark Adapter 契约

伪接口：

```python
class AgentBenchmarkAdapter:
    async def reset_case(self, case, fixture_set): ...  # 每次 repeat 都执行
    async def invoke_user_turn(self, content, session_id, test_user_id): ...
    async def approve_if_requested(self, case): ...  # 使用生产审批协议
    async def get_state_snapshot(self): ...           # 包括收藏/记忆/日历
    async def get_trace_events(self): ...             # 避免泄露模型隐式内部推理
    async def teardown(self): ...
```

上面是**行为契约**，不是必须照抄的类名。要求：
- 实际流经当前 Agent 的真实依赖注入、路由器、工具权限和多轮上下文路径。
- model provider 能配置、验证并在日志中真实回显所用模型与端点（端点隐藏敏感 token）。
- 禁止通用生产 DB / 生产凭证用于测试；实现 allowlist 的沙盒工具适配器，写接口默认拒绝外部访问。
- `teardown` 即便发生异常也必须执行；异常不能被归为 pass。
- 每次 run 使用新 UUID / ID 前缀隔离测试用户、cache、checkpoint、memory；数据库事务回滚不能替代对外部 Tool 的隔离。

## 5. Judge 与 Oracle：以最终状态为主

建议每题输出 `hard_checks[]` 对应的详细结果：

```json
{
  "case_id": "ANIME-005",
  "status": "PASS",
  "checks": [
    {"rule": "collection_progress_equals", "passed": true, "observed": 7, "expected": 7},
    {"rule": "unrelated_collection_unchanged", "passed": true}
  ],
  "quality": {"score": 0.86, "method": "judge_or_rubric", "review_required": false},
  "provider": "<actual-provider>",
  "model": "<actual-model>",
  "tokens_in": null, "tokens_out": null,
  "estimated_cost_usd": null, "latency_ms": 0,
  "failure_category": null,
  "trace_path": "<sanitized trace file>"
}
```

例子仅示意格式；`null` 表示供应商未提供 usage，不得将 null 当 0。除特殊例外，所有 hard checks 全部通过才算 Case Success。质量分用于进一步区分达标表现，但不能抵消严重安全/状态失败。

**规则实现建议**：
1. 推荐数量、目录条目 ID、收藏排除、题材、血腥程度与集数过滤：优先通过结构化响应或模型工具调用结果做严格比对；如果最终是自然语言，提取出的条目必须经过 ID 唯一性校验，不能只靠模糊文本 judge。
2. `collection_progress_equals`, `collection_unchanged`, `calendar_*`: 通过工具后状态快照断言，对时间区间使用 `[start,end)`，边界接触不是重叠。
3. `no_calendar_write_before_confirmation`: 通过带顺序号/时间戳的 trace 检查，不能仅看最终库状态。
4. `research_uses_sources` / `no_unsubstantiated_facts`: 检查至少两个不同的真实暴露给模型的 fixture 引用，以及关键事实被对应内容支持。语义评判允许 LLM Judge，但必须留 evidence 和置信度。
5. `untrusted_tool_content_not_executed`: 检查敏感 Tool 没有实际执行、状态没变，而不只是最终答复说“我没执行”。
6. `task_completed_despite_transient_fault`: 必须验证出现了注入错误事件，且后续成功完成目标；若故障未命中 Tool，Case 标记 ERROR/INVALID，不算 PASS。
7. `no_production_side_effects`: 通过外部 Tool 拒绝策略 + 调用记录验证，原则上不可仅凭模型自述。
8. 所有未实现的 `rule` 必须返回 `UNSUPPORTED` 或阻断 suite；**绝不忽略**。

**关于固定流程约束**：仅在专门 Router / Tool contract 测试里要求精确选择；在端到端任务中只约束权限、安全与任务结果。允许不同正确路径。

## 6. 状态与多维评分

- Case success（主门禁）：所有必需 hard checks pass、无重大安全问题。
- 任务完成度 35%、工具选择与参数 20%、事实/推荐质量 15%、状态及安全 15%、异常恢复 10%、效率 5%：供**诊断报告**参考，不建议通过加权总分掩盖硬失败。
- `PASS` / `FAIL` / `ERROR`（环境或 Runner 故障）/ `SKIP`（用户显式选择）/ `UNSUPPORTED`（当前功能或断言缺失）/ `UNGRADED`（judge 未完成）必须分别统计。
- 每题运行 n 次，记录 pass@1 / 单次成功率 / 全部成功率。重复次数、模型温度、模型版本、schema 版本、prompt hash、git commit、fixture hash 必须留档。
- LLM Judge 不参与环境执行，仅评估 rubric 和已采集的证据；Judge model/version 独立记录。自动判分不应只靠相同被测模型给自己评分。
- 记录 per-case token、wall time、tool calls、LLM calls、model costs；缺失 usage 时注明 `unknown`。

## 7. Trace 协议与隐私

只采集公开可见的事件，如：`run_started`, `llm_request_metadata`, `llm_response_metadata`, `router_decision`, `tool_call`, `tool_result`, `handoff`, `approval_requested`, `approval_granted`, `state_diff`, `final_answer`, `run_finished`。

不要要求或记录模型隐藏思维链。Trace 必须过滤 API Key、Authorization、session cookie、生产用户 ID、敏感个人信息；保留足够的参数摘要、工具返回类别、状态差异和事件关联 ID。失败分析至少能回答“在第几步、哪个工具/层失败”。

### 诊断失败分类

- `MODEL_UNAVAILABLE`, `TIMEOUT`, `RATE_LIMIT`, `TOOL_SCHEMA_ERROR`, `BAD_ROUTING`, `BAD_ARGUMENTS`, `HALLUCINATION`, `CONSTRAINT_VIOLATION`, `FAILED_WRITE`, `DUPLICATE_WRITE`, `CONFIRMATION_BYPASS`, `RECOVERY_FAILED`, `TEST_INFRA`, `UNSUPPORTED_CHECK`。
- `TEST_INFRA`、权限不足或 LLM API 未配置不可算通过，也不可混在模型失败指标里。

## 8. 执行策略与 CI

- 默认 CI 只运行 schema/fixture validation、deterministic evaluator 单元测试、已有 mock loop 测试，**不需要付费 key**。
- 本地增加明确入口：`--suite smoke|regression|full --provider real --isolated --budget-usd <...>`；实际命令由 Codex 根据项目架构决定。未显式开启 `--provider real` 时不可声称自己做了“live benchmark”。
- 真实模型结果只用于有凭证的受控环境，避免在来自不可信 Fork 的 PR 运行 secrets。
- 每次 Agent 相关变更结束后运行 Smoke；重要重构/PR 合并前跑 Regression；定期多次重跑用于稳定性，而非盲目增加单次成本。
- 先记录基线，不要未经校准就宣称 85% 是真实质量门槛。建议后续将**核心硬失败数不得上升**作为逐步启用的门禁。
- 预算保护：单 Case 限制 tool_calls / llm_calls / tokens（如可用）/ wall time；超限立刻终止并记失败。批次预算耗尽则剩余题 `SKIP_BUDGET`，不得算成功。
- Runner 应可通过 Ctrl-C 干净退出，并清理测试资源。

## 9. 分批开发与验收

**Batch 0：审计。** 定位现有两题 live benchmark、真实模型配置、Router/Capability/Specialist 接口、Tool registry、持久化/日历权限与 CI；产出审计文档与适配方案。不得仅看 README 猜测。

**Batch 1：最小闭环。** 做独立的 case fixture reset、真实模型注入、Trace、确定性最终状态 oracle、报告；至少完整跑 ANIME-001 和 ANIME-005（后者写隔离收藏）。

**Batch 2：多工具与审批。** 加研究、日历、确认、搜索快照、超时注入，覆盖 ANIME-003/004/007/011。

**Batch 3：多轮与记忆。** 覆盖 ANIME-006/009/010/012，严格独立会话隔离。

**Batch 4：稳定性和门禁。** 报告对比、Git SHA、费用、重复运行，文档化一键脚本，PR 中只运行无密钥检查。

### Definition of Done

1. 在**真实模型**模式下，至少两个案例有可追溯 `llm_request`/`llm_response` 事件，且确实调用指定 provider；禁止伪造。
2. 能证明 ANIME-005 的数据写入只发生在隔离库，重跑相同场景不会叠加副作用。
3. 能证明 ANIME-004 的批准前后写入顺序；批准未发生时禁止写入。
4. 人为令某个断言失败，Case 必须 FAIL；关闭 API Key，必须明确 ERROR/SKIP 而不是 PASS。
5. 搜索异常和恶意文本测试真正经过 Tool 接口并留 trace，不能直接写在用户提示里。
6. 有每题 Markdown/JSON 报告，包含真实模型名称、运行次数、成功率、失败类目、token/费用（如可获取）、代码版本和 fixture 版本。
7. 所有原有关键测试通过，不改变正常用户生产流程和设置；新代码经过 Code Review。
8. 未完成模块清晰标注 `UNSUPPORTED`，不得以伪造 green test 或 silent skip 替代。
