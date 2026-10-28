# Anime Agent Benchmark v1：运行与扩展指南

这套基准用固定的 12 道 Anime 场景检查真实 Agent Loop。模型调用是真实 Provider；收藏数据库和搜索响应是每次重建的合成数据。它不会连接生产数据库，也不会访问真实搜索服务。

## 1. 双击运行真实模型 Smoke

在仓库根目录双击 [`run-live-anime-benchmark.cmd`](../../run-live-anime-benchmark.cmd)。脚本显式运行 `--provider real --isolated --suite smoke`，会打开本次 `report.md`；机器可读结果保存在同目录的 `report.json`。真实模型调用可能产生费用；脚本不会修改基线。

等价的 PowerShell 命令：

```powershell
uv run --directory backend python -m app.evaluation.anime_live `
  --provider real --isolated --suite smoke
```

`smoke` 运行 6 道当前可执行场景。完整 `regression` 会列出 12 道，其中 4 道会明确标记 `UNSUPPORTED`，不会伪装成通过：

| 场景 | 当前状态 | 原因 |
| --- | --- | --- |
| ANIME-001、002、003、005、007、008、009、011 | 可执行 | 使用当前 Runtime 能力、合成数据和确定性状态断言 |
| ANIME-004、012 | UNSUPPORTED | 当前 Schedule 只支持按星期重复的计划，没有隔离的一次性日期事件 |
| ANIME-006 | UNSUPPORTED | headless live runner 一次只执行一个 Runtime Run，不能保留多轮会话 |
| ANIME-010 | UNSUPPORTED | 当前聊天 Runtime 只读取 Memory，没有写入长期偏好的生产路径 |

真实评测配置 `anime-agent-benchmark-v1.yaml`、`task-benchmark.yaml`、`real-model.yaml` 和 `real-model-quality.yaml` 使用 `routing.version: model-v1`。每题会先用相同的 Provider 和模型发起一次独立 JSON 路由调用，再执行 Agent Loop；这次调用计入模型调用预算、Token、延迟、费用（有价格配置时）和 Trace。路由 Provider 失败会使该题失败。在线 HTTP 聊天仍使用 `keyword-v1` 默认路由；离线 scripted Eval 不会冒充真实模型路由。

只复测一道题时，传入 `--case`：

```powershell
uv run --directory backend python -m app.evaluation.anime_live `
  --provider real --isolated --suite regression --case ANIME-003
```

报告仍会列出整套 12 道题，未选中的题标记为 `SKIP`；本例只执行并统计 `ANIME-003`。查看该题的 `transcripts/ANIME-003.json` 和 `transcripts/traces/ANIME-003.trace.json`，Trace 中 `operation=route`、`call_role=router` 是路由模型调用，其他模型调用属于 Agent Loop。

配置默认使用 `deepseek-flash` / `deepseek`。凭据从 `OPENAI_API_KEY`、`OPENAI_BASE_URL` 或后端已有设置读取，不要把 Key 写进 YAML、用例或报告。没有凭据时命令返回非零，仍会在 run 目录中写 `status=NOT_RUN` 的报告；该报告没有成功率、质量分或成本分。

**不要把 pytest、`offline` Eval 或 suite 静态校验说成真实模型测试。** 它们用于检查代码、数据和断言，不调用付费 Provider。实时报告中的 `model_calls` 也很重要：当前生产 Recommendation specialist 有些路径本身不调用 LLM，不能把这些路径描述成模型生成的回答。

## 2. 在哪里看题目、模型、代码和结果

| 你要查看 | 文件 / 目录 | 内容 |
| --- | --- | --- |
| 用户给 Agent 的指令、12 道场景 | [`cases/anime_benchmark_v1.jsonl`](../../otakuneko-benchmark-v1/cases/anime_benchmark_v1.jsonl) | 每行一个场景；`turns[].content` 是输入指令 |
| 收藏、目录、搜索快照等测试数据 | [`fixtures/`](../../otakuneko-benchmark-v1/fixtures) | 文件都标记为 synthetic；每次 Case 在内存 SQLite 中重新 seed |
| Provider、模型、Router、限额 | [`anime-agent-benchmark-v1.yaml`](../../backend/evals/config/anime-agent-benchmark-v1.yaml) | `agent`、`routing`、`runtime_budget`、`thresholds` |
| 最新报告 | `backend/.runtime/evaluation/anime-agent-benchmark-v1/runs/<run-id>/report.json` | 汇总状态、指标、逐 Case 结果和 Run index |
| 单次对话 | 同目录 `transcripts/ANIME-xxx.json` | 输入指令、最终回答、工具摘要、运行状态 |
| 单独的 Trace | 同目录 `transcripts/traces/ANIME-xxx.trace.json` | 脱敏的模型调用、路由、工具与 Run 事件；`report.json` 的 `run_index[].trace_path` 可直接定位 |
| 本次趋势结果 | 同目录 `trend-report.json` | 基线、差异、门槛和汇总指标 |
| 本次基线快照 | 同目录 `current-baseline.json` | 成功率、波动、质量、步骤、tokens、费用、Provider 错误和 Router 指标 |

报告中几个容易混淆的状态：

- `PASS` / `FAIL`：确定性 hard checks 的最终结果；质量分不能掩盖状态或安全失败。
- `ERROR`：Provider、Runtime、Trace 或测试设施错误。Provider 与 execution error 在汇总中分别计数。
- `UNSUPPORTED`：当前功能或断言无法执行；不纳入成功率分母。
- `UNGRADED`：该 Case 已运行，但某个必需 hard check 尚无判定；不算成功。
- `SKIP`：该题不在本次 suite 选择范围内。
- `NOT_RUN`：没有真实 Provider 凭据；不产生任何分数。

## 3. 读懂指标

| 指标 | 怎么看 |
| --- | --- |
| `loop_success_rate` | 所有已尝试 Case/repeat 中 hard checks 全通过的比例。主任务成功率。 |
| `pass_at_1` | 每道题第一次运行成功的比例。 |
| `all_repeats_success_rate` | 每道题的所有重复运行都成功的题目比例。 |
| `functional_pass_rate` | 有可判定功能结果的 Case 通过比例；与 Judge 质量分分开。 |
| `router_accuracy` | 已观察到的路由决定中，符合 v1 场景路由标签的比例。它是诊断指标；不改变单题任务结果。换 Router 后可比较，但如果新 Router 合法地选择不同 Specialist，需要复核 v1 路由标签。 |
| `quality_pass_rate` | Judge 已完成评分的回答通过率；没启用 Judge 时为 `null`，人工审查在 `human_*` 计数中单列。 |
| `execution_error_rate` / `provider_error_rate` | Runtime/工具错误与 Provider 错误分开。 |
| `mean_steps`、`total_tokens`、`latency_ms` | 实际 Runtime 步数、模型 token 和延迟。未知 token 显示为 `null`，不按 0 处理。 |
| `total_cost_usd` | 有可用 Provider 用量与价格配置时才计算。当前配置没有模型价格，因此费用可能为 `null`；不会猜价格。 |
| `loop_success_variance` | 对重复 Run 的单次成功结果计算的 Bernoulli 方差；同时查看 `pass_at_1` 和 `all_repeats_success_rate`。 |

基线比较报告 `regressions`、`improvements`、`provenance_changes`。模型、Prompt、数据集或 repeat 数变化会显示为来源变化，仍会比较相同 Case 的指标；新增/缺失 Case 会单独列出。基线必须使用相同 suite 和 Case 集合才适合逐项比较。

## 4. 重复运行与基线

第一次为当前版本建立本地 Smoke 基线：

```powershell
uv run --directory backend python -m app.evaluation.anime_live `
  --provider real --isolated --suite smoke --repeats 3 `
  --baseline evals/baselines/anime-agent-benchmark-v1-smoke.json `
  --update-baseline
```

后续代码或 Prompt 修改后，用同样的 suite、模型和 repeat 数对比：

```powershell
uv run --directory backend python -m app.evaluation.anime_live `
  --provider real --isolated --suite smoke --repeats 3 `
  --baseline evals/baselines/anime-agent-benchmark-v1-smoke.json
```

`--update-baseline` 只应在你审阅并接受一轮成功结果后使用；已有基线需要显式 `--force` 才可替换。完整 12 题可以用 `--suite regression`，但报告会保留 4 个 `UNSUPPORTED` 状态，命令不会把不完整套件报成全绿。

## 5. 如何改指令、加场景或换 Router

1. **改已有输入**：编辑 `cases/anime_benchmark_v1.jsonl` 对应行的 `turns[].content`。不要把 `hard_checks`、预期答案或 rubric 拼进用户指令；它们只给评估器读取。
2. **改测试世界**：编辑 `fixtures/*.synthetic.json`，同步确认收藏和搜索快照里的 ID/别名一致。loader 会计算 fixture digest，报告会记录数据集 hash。
3. **改状态断言**：在 `backend/app/evaluation/anime_scoring.py` 增加确定性规则和测试。无法验证的硬断言必须标成 `UNSUPPORTED`，不能默认通过。
4. **新增一道 v1 场景**：v1 固定包含 ANIME-001 到 ANIME-012，loader 会拒绝多一行或少一行。不要悄悄改写 v1 基线；复制设计包并发布新的 dataset 版本，同时更新 loader 中的 ID/版本约束和对应 scorer 测试。
5. **换 Router**：先在 `backend/app/harness/execution.py` 注册新的版本化 Router 组装方式，再只把要比较的真实评测 YAML 的 `routing.version` 切到新版本。`model-v1` 会多调用一次相同的真实 Provider/模型；HTTP 在线聊天仍走 `keyword-v1` 默认路由。报告和基线会记录 Router 版本、每次实际 route decision 与 Router accuracy；任务成功仍由最终状态断言决定。
6. **每次改动后**：先跑离线回归，再双击 `run-live-anime-benchmark.cmd`。离线测试不用 API Key；双击命令是真实模型 Smoke。没有 Key 就停在 `NOT_RUN`，配置 Key 后再执行实时验证。

Judge 可沿用 `backend/evals/config/real-model-quality.yaml` 的 `judge_factory` 配置模式；按需启用 `judge.enabled` 并配置 Judge 模型、Provider 和成本费率。人工评价通过 CLI 的 `--human-reviews` 读取版本化 JSON，字段格式见 `backend/app/evaluation/human_review.py`。Judge/人工评分用于质量诊断，不覆盖功能 hard checks。
