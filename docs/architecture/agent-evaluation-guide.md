# Agent 评估与测试上手指南

本文帮助你从仓库根目录运行 OtakuNeko 的 Agent 测试与 Eval，读懂输入、模型、指标、报告和基线。源码与配置是能力事实的依据；README 只作为导航。`backend/evals/datasets/v1-real-model.jsonl` 当前有六个 case。

Anime Agent Benchmark v1 的真实模型一键运行、12 道场景状态、重复实验和 Router 对比见[专项上手指南](anime-agent-benchmark-v1.md)。

## 1. 先分清测试与 Eval

- `pytest` 验证代码单元、集成边界和回归；Capability contract 测试用真实注册的 Capability handler，但把 provider、数据库等依赖隔离成合成数据。
- 离线 Eval 验证固定数据集和 Runtime 行为。L5 gate 和 loop gate 使用合成模型决策，不会测出模型能否自行推理。
- Live Eval 使用真实模型 Provider。它有费用、波动和运行环境依赖；即使 Runtime、数据库或部分外部服务受到隔离，也不等于完整生产用户场景。

从仓库根目录打开 PowerShell。以下命令使用 `uv run --directory backend`，报告等相对路径因此位于 `backend/` 下。

Windows 用户也可以在仓库根目录双击 [`run-live-task-benchmark.cmd`](../../run-live-task-benchmark.cmd)：它会运行两道真实模型题并打开本次报告。该操作会调用真实 Provider，可能产生费用；脚本不会更新 baseline。

## 2. 导航表

| 要验证什么 | 配置 / 数据集 | 模型与执行目标 | 从仓库根运行 | 主要产物 |
| --- | --- | --- | --- | --- |
| 后端全部 Python 测试 | pytest 配置；不加载 Eval dataset | 测试替身、隔离依赖；是否调用模型由具体测试决定 | `uv run --directory backend pytest` | 终端输出；只有显式加 `--junitxml=...` 才保存 JUnit |
| 新任务基准定向回归 | `tests/evaluation/test_final_answer.py`、`test_task_benchmark.py` | Fake Provider，ProductionRuntimeTarget 和真实 Capability handler；断言两工具正确/错误最终 JSON | `uv run --offline --locked --directory backend pytest tests/evaluation/test_final_answer.py tests/evaluation/test_task_benchmark.py -q -p no:warnings` | pytest 输出；不调用真实 Provider |
| Capability contract 快速运行 | `tests/capabilities/contracts/`；`fixtures_core.py`、`fixtures_external.py` | 真实 Registry、Dispatcher 和 handler；外部依赖使用合成 fixture | `uv run --directory backend pytest tests/capabilities/contracts -q` | pytest 输出 |
| Capability contract 覆盖门禁 | 同上；生产 Registry 是动作清单来源 | 同上；检查动作和版本的必需场景确实执行 | `uv run --directory backend pytest -p tests.capabilities.contracts.plugin tests/capabilities/contracts --capability-contract-gate --capability-contract-report=.runtime/capability-contracts/coverage.json -q` | `backend/.runtime/capability-contracts/coverage.json` |
| 快速 Eval | `fast.yaml` → `v1.jsonl` | `offline-fixture-v1`；固定 fixture，不是真实 LLM | `uv run --directory backend python -m app.evaluation.runner --config evals/config/fast.yaml` | `backend/.runtime/evaluation/fast.json` |
| 观测性 Eval | `observability.yaml` → `v1-observability.jsonl` | `offline-fixture-v1`；固定 fixture，不是真实 LLM | `uv run --directory backend python -m app.evaluation.runner --config evals/config/observability.yaml` | `backend/.runtime/evaluation/observability.json` |
| Runtime Entrypoint Eval | `entrypoint.yaml` → `v1-entrypoint.jsonl` | `ScriptedLLM`，结构化 fixture 决策；每 case 使用隔离的内存 SQLite | `uv run --directory backend python -m app.evaluation.runner --config evals/config/entrypoint.yaml` | `backend/.runtime/evaluation/entrypoint.json` |
| L5 离线 PR gate | `l5-contract-v2.yaml` → `v2-l5-contract.jsonl`；`l5-scenarios-v3.yaml` → `v3-l5-scenarios.jsonl` | 固定 `entrypoint-fixture-v1` 决策；共享 Runtime entrypoint；不访问网络 | `uv run --directory backend python -m app.evaluation.l5_gate` | `backend/.runtime/evaluation/l5-gate.json`、`l5-gate-diff.json`、逐 case transcript |
| Runtime loop 认证 | 固定七场景目录，无 YAML/JSONL | 合成 ModelGateway 和 Capability；Runtime、Dispatcher、SQL Run/Event/Trace 存储是真实实现 | `uv run --directory backend python -m app.evaluation.loop_gate --output .runtime/agent-gate` | `backend/.runtime/agent-gate/report.json`、`cases/<case-id>.replay.json` |
| 新任务基准：先跑离线版 | `task-benchmark-offline.yaml` → `v1-task-benchmark-offline.jsonl` | fake echo 多步决策；只验证 Runtime loop/最终结果合约，不覆盖生产 Capability | `uv run --directory backend python -m app.evaluation.runner --config evals/config/task-benchmark-offline.yaml` | `backend/.runtime/evaluation/task-benchmark-offline.json` |
| 新任务基准：真实模型 | `task-benchmark.yaml` → `v1-task-benchmark.jsonl`，含两个 case | `ProductionRuntimeTarget`、真实 Provider；配置打开 `routing.enabled` | `uv run --directory backend python -m app.evaluation.real_model --config evals/config/task-benchmark.yaml` | `backend/.runtime/evaluation/task-benchmark/runs/<run-id>/report.json`、manifest、transcript |
| 真实模型 smoke | `real-model.yaml` → `v1-real-model.jsonl`，当前数据文件有六个 case | `deepseek-flash` 或传入 `--model`；真实 Runtime/Registry，受控 capability allowlist | `uv run --directory backend python -m app.evaluation.real_model --config evals/config/real-model.yaml --case real-model-tool-time` | `backend/.runtime/evaluation/real-model/runs/<run-id>/report.json`、manifest 和 transcript |
| 真实模型 + Judge | `real-model-quality.yaml` → `v1-real-model.jsonl` | 真实 `deepseek-flash` Agent 和 Judge；controlled-v1 allowlist | `uv run --directory backend python -m app.evaluation.runner --config evals/config/real-model-quality.yaml` | `backend/.runtime/evaluation/real-model-quality.json`（含 review_queue）、transcript |
| 完整 live Eval | `full.yaml` → `v1-full.jsonl` | `gpt-4o-mini` ProductionRuntimeTarget + Judge；需要 Provider 凭据 | `uv run --directory backend python -m app.evaluation.runner --config evals/config/full.yaml` | `backend/.runtime/evaluation/full.json` |
| 重复运行与趋势对比 | `task-benchmark.yaml`；先在 §7 创建本地 `task-v1.json` | 多次真实 Provider 调用，默认三次重复 | `uv run --directory backend python -m app.evaluation.trend --config evals/config/task-benchmark.yaml --repeats 3 --baseline .runtime/evaluation/baselines/task-v1.json --history .runtime/evaluation/task-benchmark/history.jsonl` | `backend/.runtime/evaluation/l6-trend/<run-id>/` 下的 `report.json`、`current-baseline.json`、`trend-report.json`、`trend-diff.json`；并追加 task-specific history |
| 前端 Vitest | 前端测试项目；与 Agent Eval 分开 | 前端测试替身 | `pnpm --dir frontend test` | Vitest 终端输出 |

### 第一次运行：离线任务基准

先在仓库根目录运行 fake echo 任务，再查看整体报告与逐 case 结果：

```powershell
uv run --directory backend python -m app.evaluation.runner --config evals/config/task-benchmark-offline.yaml
$report = Get-Content -Raw 'backend/.runtime/evaluation/task-benchmark-offline.json' | ConvertFrom-Json
$report.aggregates | ConvertTo-Json -Depth 8
$report.cases | Select-Object case_id, outcome, passed, run_id, trace_id | Format-Table
```

这一步完全使用预编排 fake decisions，不调用真实 Provider。接下来可以运行 L5 和 loop gate 检查既有固定契约。需要验证 live routing 时，再运行表中的 `task-benchmark.yaml` 命令。不要把 `full.yaml` 当作离线配置：它没有 `real-model.yaml` 的 controlled block，运行前必须确认数据集、能力、Provider endpoint 和环境。

## 3. Fake 模型和真实模型分别在测什么

### L5 的 fake 多步 case

可查看 `backend/evals/datasets/v3-l5-scenarios.jsonl` 中的 `l5-scenario-multi-step`。它的核心字段是：

```json
{
  "input_messages": [{"role": "user", "content": "连续读取两次固定值，再基于观察结果回答。"}],
  "fixtures": {
    "events": [
      {"type": "tool_call_start", "name": "entrypoint.echo", "arguments": {"text": "first"}},
      {"type": "tool_call_start", "name": "entrypoint.echo", "arguments": {"text": "second"}},
      {"type": "message_chunk", "content": "两次读取已完成。"}
    ]
  }
}
```

`input_messages` 是 case 输入；`fixtures.events` 是预先编排的模型输出事件。目标把它们交给 `ScriptedLLM`，所以该 case 能检查 Runtime 是否按顺序调度两次 echo、收到观察后完成、拒绝禁止动作、满足参数摘要和步数断言。它**不证明模型能从问题中自行规划两次调用**。fake 模型每个事件都已写在 JSONL 里。

### 真实模型 case

`real-model-tool-time` 的输入要求 Agent 使用 `get_current_time` 回答本地日期和时间。其确定性条件要求调用该 capability、不得调用 `list_collections`、Run 完成、决策步数在 2–3 之间且工具错误数为 0。该 case 的 `fixtures.events` 明确写着 live target 不使用 fixture events；真实模型 gateway 会从 Provider 请求决策。

`real-model.yaml` 仍使用真实 Runtime、Registry、Dispatcher 和 capability 实现；每个 case 的 SQL Run/Event/Trace 数据库及用户是隔离的合成数据。controlled-v1 当前只允许 `get_current_time`、`list_collections`、`get_collection_statistics` 和 `search_anime_advanced`；Bangumi anime 搜索响应在进程内固定。真实模型调用 Provider 仍会产生费用和波动；未被 fixture 替换的 read capability 可能调用其正常外部服务。没有凭据或 endpoint 不符合策略时会 fail closed，不回退到 fake model。

### 新增任务 benchmark 与 Router 证据

`task-benchmark-offline.yaml` 用 fake echo 预编排两次工具调用，最终答案要求精确匹配 JSON 对象 `{"first":"alpha","second":"beta"}`。它验证 fake 决策经过 Runtime loop 后能执行两次调用并满足 final-answer contract；它不运行生产 Capability，也不测试真实模型的计划能力。

另有定向 pytest 覆盖生产路径：真实 ProductionRuntimeTarget 和 Capability handler 接收 fake Provider 的两次工具决策，再用正确和错误的最终 JSON 验证接受规则。这能在不发起 Provider 请求时检查生产 Runtime 组合和最终答案判定；它仍不测真实模型是否会自行选工具或生成该答案。本次指南整理没有运行下面的 live 命令，也没有生成真实模型报告。

`task-benchmark.yaml` 有两个 case：

- `task-multi-tool-result`：真实模型读取隔离用户的收藏列表，再读取 controlled fixture 的 Frieren 搜索结果，并按 `expected_json` 输出是否为空和首个结果 ID；期望 Runtime specialist 为 `fallback`。
- `task-router-cold-start`：触发推荐 specialist 的冷启动路径；期望 `expected_agent=recommendation`，并要求最终回复提示用户先给看过的作品评分。该场景可能在 Runtime 路由/冷启动边界结束，不一定调用模型。

真实任务配置打开 `routing.enabled`，`expected_agent` 要求 trace 中确实观察到 Runtime route decision 才计入 `router_accuracy`；历史 `routing_accuracy` 仍是兼容分类指标，不能替代这个断言。该 dataset 只含两条定向 case，能为这些 case 提供证据，不代表所有 query 的 Router 准确率，也不单独证明 Router 修复已验收。

## 4. JSONL 输入怎么编辑

Eval dataset 是 JSONL，不是一个 JSON 数组：

1. 第一条 JSON object 是 manifest，含 `dataset_version` 与 `schema_version`。
2. 后续每个 case 各占一整行；case 必须有唯一 `id`，并符合 `EvalCase` 的严格 schema。
3. `input_messages` 写对话输入；`fixtures.events` 写 fake target 的脚本；`deterministic` 写可机械判定的期望；`answer_quality` 声明可选的主观质量门槛；有 Router 期望时用 `expected_agent` 声明期望的 specialist。
4. 不要把多行缩进 JSON、注释或逗号留在同一 case 中。Loader 会逐行执行 `json.loads`，只把每行解析成 object。
5. 保存为 UTF-8 无 BOM。Loader 使用 `read_text(encoding="utf-8")`，不会剥除 UTF-8 BOM；Windows PowerShell 5.1 的 `Set-Content -Encoding utf8` 会写 BOM，可能让首个 manifest 无法解析。
6. 每次内容变化都会改变 dataset SHA-256 digest，因而可能触发基线版本失败。任务迭代时复制数据集和配置，递增 dataset version 并让新配置指向新 dataset；不要直接改已发布的任务文件。dataset/config/baseline 按 append-only 管理。即使 loader 忽略空行和 `#` 注释行，这些字符仍计入文件 digest。

从仓库根目录 fork 一份任务文件时，可以先复制：

```powershell
Copy-Item backend/evals/datasets/v1-task-benchmark.jsonl backend/evals/datasets/v2-task-benchmark.jsonl
Copy-Item backend/evals/config/task-benchmark.yaml backend/evals/config/task-benchmark-v2.yaml
```

然后在副本中把 manifest 的 `dataset_version` 改成 `v2-task-benchmark`，并同步新 YAML 的 `name`、`dataset` 和 `report_path`。旧版本保持原样，比较时也要使用匹配该新版本的新 baseline。

新增一个 fake case 时，一起改输入、预编排事件和 deterministic assertions，并确认事件顺序能覆盖你要验证的 Runtime 行为。新增 live case 时，fixture event 不会决定模型输出；要写用户指令、运行约束和 deterministic 期望，并检查它使用的 capability 是否在受控配置范围内。

## 5. 规则评分、质量评分和成功率分母

### 确定性规则评分

`deterministic` 是 case 规格和 Runtime 规范化结果的纯函数评分。当前维度包含终态、必需/禁止工具、参数键与执行摘要、evidence/citation、recovery、模型决策步数和工具错误。所有启用维度通过才是 `task_success`。这适合精确答案、工具选择、参数、调用顺序和错误边界等可验证任务。

可选的 `deterministic.final_answer` 是额外维度：`required_text` / `forbidden_text` 对最终文本做子串检查；`expected_json` 接受对象或数组，要求严格等值 JSON，忽略对象 key 顺序，但不接受缺字段、多字段、不同值或不同数组顺序。JSON 解析也拒绝 NaN/Infinity，并区分布尔值和整数。旧 case 不写该字段时行为不变。

### Judge 质量评分的限制

Judge 分数与规则分数分开；可用分数低于 case 的 `min_score` 会让 case 失败，`required` 只控制 Judge 不可用时是否失败。Judge 不会改写 `DeterministicScore`。

当前 `runner.py` 构造 Judge 请求时传入的是 `config.judge.rubric` 和 `config.judge.rubric_version`，而不是 `case.answer_quality.rubric`。`judge.py` 的请求只有用户输入、最终回复和 rubric，不包含 tool evidence、Capability invocation 或 trace。因此当前 Judge 不能验证“答案是否被某个工具结果支持”；逐 case 的 rubric 文本也没有实际进入请求。这是现有边界，不能把 Judge 分数当作工具使用或事实依据正确性的证明。

### 两个容易混淆的比例

- `pass_rate` 是端到端比例：`CaseResult.passed / 所有选中 case`。Provider error、execution error 等失败会留在总分母中。
- `l6_functional_pass_rate` 是条件性功能成功率：只在 `outcome` 为 `passed` 或 `functional_failure` 的 case 中计算。因此它排除 provider error、execution error 和 cancelled case。

做复杂任务的结论时，应把这两个数字放在一起，并同时报告 `l6_provider_error_count/rate`、`l6_execution_error_count/rate` 和 `l6_cancelled_count`。只报 functional pass rate 会隐藏系统未能完成评估的运行。没有可评分的功能 case 时，runner 不会给出 `l6_functional_pass_rate`。另外，预期的 refusal/cancellation 若满足 case contract，可以算通过；`passed` 不总是等同于 terminal status 为 completed。

当 case 声明 `expected_agent` 时，runner 额外计算 `router_accuracy`，要求实际观察到的 Runtime route 决策与期待 agent 相同。没有声明 agent 的普通 case 不生成该指标。

loop gate 使用另一套固定样本指标，每项都输出分子、分母和值：`loop_pass_rate`、`observation_accuracy`、`recovery_rate` 和 `duplicate_call_rate`。基准分别要求 100%、100%、100% 和 0%；缺少必需 observation 或 recovery 样本会使 gate 失败。

Trend schema 2 的主端到端指标是 `loop_success_rate = CaseResult.passed / 所有 live 运行`，provider error、execution error 和 cancelled 都留在分母中。`functional_pass_rate` 只在有功能判定的运行中统计，分母是 `passed + functional_failure`。这与 `loop_pass_rate` 不同：loop gate 的后者只看固定七个合成场景是否满足场景断言，用来认证 Runtime loop；它不能代替真实模型任务的全运行最终正确率。Trend 还保存成功运行数、错误率、取消率和 loop success variance，可发现“功能成功率看起来稳定，但部分运行根本没有完成”的退化。

## 6. 按报告追到 Run、transcript 和 Trace

通用 Eval 的报告顶层记录 `dataset_version`、`dataset_digest`、`code_revision`、`prompt_version`、`agent` 和 `environment`；`run_index` 再把每个 case 关联到 `run_id`、`trace_id`、transcript 路径、输入消息数、Provider/model、usage 与错误。先核对这组版本信息和聚合，再从 run index 找对应 transcript，最后按其中相同的 `run_id` / `trace_id` 查看 Trace：

```powershell
$report = Get-Content -Raw 'backend/.runtime/evaluation/task-benchmark-offline.json' | ConvertFrom-Json
$report | Select-Object dataset_version, dataset_digest, code_revision, prompt_version
$report.agent | Format-List
$report.environment | Format-List
$report.run_index | Format-Table case_id, run_id, trace_id, transcript_path, message_count
$entry = $report.run_index | Where-Object case_id -eq 'task-scripted-multi-step'
$transcript = Get-Content -Raw (Join-Path 'backend' $entry.transcript_path) | ConvertFrom-Json
$transcript.trace.steps | Format-List
$transcript.events | Format-Table sequence, type, run_id
```

`code_revision` 是运行时读取的 Git `HEAD`；当前报告不计算未提交工作区内容的 digest。做可复现的基线运行前，先确认 `git status --short` 并保存你要测的代码版本；否则两个不同的未提交工作区可能显示同一个 `code_revision`。

把表里目标 case 的 `transcript_path` 接到 `backend/` 下查看。transcript 是脱敏诊断视图，包含输入消息、Decision（参数键）、Invocation observation、规范化结果、事件、Trace 与 terminal facts；不会导出 raw provider payload 或完整参数值。L5 gate 的聚合报告也包含 case/run/trace 身份，逐 case transcript 位于 `backend/.runtime/evaluation/transcripts/<config-name>/<case-id>.json`。Run/Event 持久化事实与 Trace 投影用途不同；不要把 SSE 或 transcript 当成 Run 状态存储。

loop gate 在 `cases/<case-id>.replay.json` 保存合成的决策、执行、事件、Trace 和 terminal evidence。可在新的隔离数据库中验证一个固定场景的 replay：

```powershell
uv run --directory backend python -m app.evaluation.loop_gate --replay .runtime/agent-gate/cases/multi_step.replay.json --output .runtime/agent-gate-rerun
```

Replay 只接受固定场景目录，不会执行 bundle 提供的任意 import、网络 endpoint 或生产 capability。生成的 ID 和时间可以不同。

## 7. 怎么读基线对比

L5 gate 默认比较 `evals/baselines/v2-l5-gate.json`。它要求配置、dataset 版本与 digest、模型和 prompt contract metadata 对得上；case 回归、基线里缺失的新 case、报告里缺失的基线 case、步数/Token/工具错误增量和 termination/recovery 差异都可能失败。查看：

- `l5-gate.json`：哪个 config/case、Run、Trace 和断言维度失败；
- `l5-gate-diff.json`：case outcome、行为回归和版本失败详情；
- 关联 transcript：事件和 Trace 证据。

Trend 的重复 live 运行会生成 schema 2 统计。显式 baseline gate 同时比较逐 case 指标和总体分布：总体 `loop_success_rate` 按成功运行数／全部运行数加权计算，因此某个 case 的运行次数较多时会按实际样本数计入。比较项包括 loop 与 functional success、L6 分数、延迟、token、成本、Provider/执行错误、取消和实际步数；Judge quality 仅在基线与当前运行都有可评分样本时比较。默认成功率/质量下降与错误率上升容忍度为 10 个百分点，延迟、token、成本、实际步数上升容忍度为 50%。方差也会写入汇总与 history，用于观察波动，不单独触发回归门禁。Trend baseline 记录 Router 版本和启用状态，供你核对更换前后的运行身份；改 Router 时应同步递增配置中的 `routing.version`，然后比较同一 dataset 上的总体与逐 case 成功率、错误率。只有配置费率且 Provider 返回 usage 才估算成本；未知值保持 null。Trend 是测量和比较工具，不会自动修复 Router 或模型行为。当前仓库里的 `l6-trend-deepseek-flash.json` 仍是 schema 1；新版代码可读取，但旧数据缺少全运行指标，不能建立完整的 schema 2 比较。刷新基线前需要人工确认并审查结果，不会自动迁移或更新该文件。`trend-report.json` 中的 `history_trend` 与显式 baseline diff 分开；history 是诊断信息。

任务基准使用单独的本地 baseline 路径 `.runtime/evaluation/baselines/task-v1.json`，不覆盖 Git 跟踪的 schema 1 文件 `evals/baselines/l6-trend-deepseek-flash.json`。首次创建 baseline 与后续比较都运行真实 Provider，下面两条命令会对数据集中的每个 case 重复三次。创建只在当前 gates 通过时写新文件；它不应成为默认 CI 步骤。创建前先完成离线与定向回归，并人工审查报告、错误率和 transcript：

```powershell
uv run --directory backend python -m app.evaluation.trend --config evals/config/task-benchmark.yaml --repeats 3 --baseline .runtime/evaluation/baselines/task-v1.json --update-baseline --history .runtime/evaluation/task-benchmark/history.jsonl
```

后续对照同一份 baseline 时，不带 `--update-baseline`：

```powershell
uv run --directory backend python -m app.evaluation.trend --config evals/config/task-benchmark.yaml --repeats 3 --baseline .runtime/evaluation/baselines/task-v1.json --history .runtime/evaluation/task-benchmark/history.jsonl
```

不要把 baseline 更新放进默认命令或 CI。先确认是有意接受的行为变化，审查当前报告、dataset digest、错误率和逐 case transcript，再由负责人明确决定是否更新 baseline。未审查的回归不能通过刷新基线来消除。当前 task-benchmark 配置的 `pass_rate` 与 `router_accuracy` 是单次报告阈值；不要把 threshold gate 和 baseline comparison 混为一谈。

## 8. 增加 Capability 合约与受控模型工具

### 增加 contract fixture

生产 `build_capability_registry()` 是动作清单来源；每个 public action 和版本都要在 `backend/tests/capabilities/contracts/fixtures_core.py` 或 `fixtures_external.py` 有明确的 `Case`：

1. 写合法且有非空嵌套字段的 arguments，以及业务输出子集断言。
2. 用异步 `prepare` 在被导入的 domain/provider 边界替换依赖，记录依赖调用并检查传入的可信 principal/session；保留真实 Capability handler。
3. 不发出真实 Provider、qBittorrent 或网络请求。合约样例返回合成业务数据。
4. 查看 descriptor executable schema/metadata；若 schema fingerprint 变化，按要求显式更新 `snapshots.py`，CI 不自动刷新。
5. 运行上表中的 contract gate，并跑相关 domain/service/API 回归。contract handler 认证不取代 service/SQL 或 live provider 测试。

### 让真实模型看到一个新工具

仅把名字加进 `real-model.yaml` 的 `controlled.allowed_capabilities` 不够。`controlled-v1` profile 在 `backend/app/evaluation/controlled.py` 有固定 allowlist，target 会验证该动作确实是本地/DB 能力或有受控外部 fixture；未知动作 fail closed。配套任务 benchmark 使用 `controlled-task-v1`，在相同受控能力上增加只读、在隔离 case 数据库内运行的 `generate_user_profile_tool`；动漫搜索仍使用固定响应。其他外部动作需要提供进程内 fixture 并验证 allowlist 配置。无 approval 时副作用动作不进入 catalog。修改前应确认服务、数据库和副作用边界，并让配置检查覆盖该项。

## 9. 面试或交接时能准确说什么

- “L5 offline gate 使用预编排 fake decisions，但经过共享 Runtime entrypoint、Dispatcher、持久化事件与 Trace，并验证固定 case contract。”可以说；“它证明了模型会规划和调用工具”不可以。
- “Capability contract 测试保留真实 registered handler，只替换外部/领域依赖，用合成数据检查 Runtime 边界和动作版本。”可以说；“它覆盖 live provider 或生产 SQL 数据”不可以。
- “Loop gate 在七个固定合成场景中认证指定控制流，并保存 replay evidence。”可以说；不能外推到任意任务或真实模型的一般推理能力。
- “真实模型 smoke 使用 ProductionRuntimeTarget 和受限控制配置，样本较小，结果会波动并可能有 Provider 成本。”可以说；不能将小型 smoke 说成完整生产用户评估。
- “Trend 能按样本重复运行并比较 baseline。”可以说；这不表示待设计/待验收的 Router 或趋势修复已完成。要宣称修复，需要对应的定向 case、指标、报告和验收结论。

## 10. 源码索引与验收边界

- Eval schema、JSONL loader：`backend/app/evaluation/types.py`、`dataset.py`。
- 通用 runner、指标汇总、Judge 请求：`runner.py`、`metrics.py`、`l6_scoring.py`、`judge.py`。
- fake entrypoint 与 L5 基线：`entrypoint.py`、`scripted_llm.py`、`l5_gate.py`。
- 真实模型、受控 fixture、趋势比较：`adapter.py`、`real_model.py`、`controlled.py`、`trend.py`。
- loop 认证：`loop_gate.py`。
- Capability contract 测试：`backend/tests/capabilities/contracts/README.md`、`fixtures_core.py`、`fixtures_external.py`、`plugin.py`。

task benchmark 包含两条 live case 和一个 fake 离线 loop case；定向回归使用 fake Provider 验证真实 Runtime/Capability 路径。本文记录了可运行命令与证据边界；本次没有执行真实模型 Provider、趋势 baseline 创建或 baseline 对比，也不声称 Router 修复已经通过 live Eval 验收。
