# CI Verification Pipeline 第一版设计

日期：2026-09-02  
范围：为 OtakuNeko 建立第一版可维护的 CI Verification Pipeline，不改变业务运行时行为。

## 1. 目标与非目标

### 目标

- 为后端和前端提供完整的软件正确性门禁。
- 为 Agent Harness 的真实 Runtime/Dispatcher/Capability 执行链提供确定性回归门禁。
- 为现有离线评估数据集提供可重复、带阈值和 baseline 的最小 Agent benchmark 门禁。
- 让必需 PR CI 不依赖 live LLM、外部 API 或 secret。
- 保留现有 observability 与 full evaluation 的职责和触发方式。

### 非目标

- 不重写 Agent Runtime、Decision、Dispatcher、Capability 或评估框架。
- 不在本任务中加入 live provider、API key、性能压测或新的评估抽象。
- 不把目标架构或历史审计结论写成已经实现的源码事实。
- 不创建、提交或推送 Git commit。

## 2. 当前源码事实

- 后端入口由 `backend/pyproject.toml` 提供，包括 `pytest`、Ruff 和
  `otakuneko-eval = "app.evaluation.runner:main"`。
- 前端 `frontend/package.json` 已提供 `lint`、`typecheck`、`test` 和 `build`，并提交了
  `frontend/pnpm-lock.yaml`。
- `.github/workflows/evaluation.yml` 当前同时承担 fast correctness、离线 fast evaluation、
  observability evaluation 和定时/手动 full evaluation。
- `backend/app/evaluation/runner.py` 已提供人类可读摘要、JSON 报告、阈值门禁和 baseline 检查。
- `backend/evals/config/fast.yaml` 使用离线 fixture target，当前数据集包含 9 个案例；其阈值
  和 `backend/evals/baselines/v1-fast.json` 是现有评估契约，不在本任务中下调或重写。
- `backend/app/evaluation/adapter.py` 的 `RuntimeEvaluationTarget` 会通过现有
  `AgentRuntime` 执行离线事件输入；真实 `stream_decision` 闭环由 Harness acceptance 测试单独验证。
- 当前工作区已有用户修改 `README.md`，本任务不触碰该文件。

## 3. CI 拓扑

新增 `.github/workflows/ci.yml`：

```text
CI
├── software
│   ├── backend: uv sync --locked --dev → ruff → pytest
│   └── frontend: pnpm install --frozen-lockfile → lint → typecheck → test → build
├── harness
│   └── deterministic Harness/Acceptance/Capability/Trace regression
└── benchmark
    └── offline fast evaluation → threshold/baseline gate → JSON artifact
```

工作流约束：

- 触发器为 `pull_request` 到 `main` 和推送到 `main`。
- 权限为 `contents: read`。
- 每个 job 都在干净 checkout 后锁定依赖。
- 三个 job 独立显示和失败，便于区分软件、Harness 与 benchmark 回归。
- 必需门禁命令失败时 job 失败；artifact 上传可使用 `if: always()` 保存诊断，但不改变失败结果。
- CI YAML 只编排现有命令，不实现评估或业务判断逻辑。

## 4. 现有 evaluation 工作流迁移

`.github/workflows/evaluation.yml` 改为仅承担：

- 定时和手动触发的 observability evaluation；
- 定时和手动触发、需要 `OPENAI_API_KEY` 的 full evaluation。

从该工作流移除 PR/push 触发，以及其中重复的普通测试、Ruff 和 fast evaluation；这些职责由
`ci.yml` 的三个 job 接管。full evaluation 的 secret 只存在于原有受限 job，不进入 `ci.yml`。

## 5. Harness 确定性回归设计

测试使用现有 `AgentRuntime.stream_decision`、`Dispatcher`、`CapabilityRegistry` 和
`RunBudget`，不新增生产接口。

测试 double 的行为：

- Fake Model Gateway 按预先编排的 Decision 序列返回结构化结果，并记录每次模型调用的输入。
- Fake Tool/Capability 记录调用顺序和参数，返回确定性的成功或失败结果。
- 断言来自真实的 Run Event、Runtime state、Invocation/Result 和终态，而不是预写的结果计数。

覆盖场景：

1. 单步工具调用后完成；
2. 多步工具调用，验证调用顺序和后续 Decision 能看到工具 observation；
3. 工具失败后的真实错误/反馈路径；
4. 非法或不可信工具/Capability Decision 被拒绝；
5. 重复工具 Decision 在有限 `RunBudget` 下以 budget-exceeded 终止，不无限循环。

如果现有实现没有独立的 cancellation/timeout 语义，则只保留当前已有测试覆盖，不为达到覆盖表面新增架构。

## 6. Offline benchmark 设计

benchmark job 运行：

```text
uv run python -m app.evaluation.runner --config evals/config/fast.yaml
```

数据流为：

```text
fast.yaml
  → v1.jsonl dataset
  → RuntimeEvaluationTarget / OfflineOrchestrationAdapter
  → AgentRuntime execution result
  → metrics + observability snapshot
  → thresholds + v1-fast baseline
  → human summary + redacted JSON report
```

现有 9 个 fixture case 覆盖搜索、staff/cast、推荐、上下文 follow-up、路由歧义、安全注入、
provider failure 和 cancellation recovery 等类别。报告由现有 runner 生成并上传为 artifact；
命令退出码继续作为硬门禁。

该 benchmark 的准确定位是离线 fixture/replay evaluation，不宣称它等同于 live-provider 或
完整的模型决策质量测试。真实多轮 Decision loop 由第 5 节的 Harness 回归负责。

## 7. 本地与 CI 命令契约

CI 使用仓库已有的标准命令：

```text
uv run --directory backend ruff check app tests
uv run --directory backend pytest
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend test
pnpm --dir frontend build
uv run --directory backend pytest tests/harness tests/acceptance tests/capabilities tests/trace -q
uv run --directory backend python -m app.evaluation.runner --config evals/config/fast.yaml
```

依赖准备命令是 CI 环境专用的锁定安装，不改变上述验证入口：

```text
uv sync --directory backend --locked --dev
pnpm --dir frontend install --frozen-lockfile
```

## 8. 风险、边界与回滚

- 前端 lint 当前可能产生既有 warning；只有命令真实退出非零时才阻断，并不通过修改规则隐藏问题。
- 项目没有现成后端 typecheck 配置，因此本版本不添加未经项目配置支持的 typecheck 命令。
- full evaluation 仍依赖 provider credential，只能在原有定时/手动路径运行。
- benchmark 的 latency、token 和 cost 取决于现有 fixture/adapter 的真实输出，不新增伪造基准。
- 回滚方式为恢复本任务新增/修改的工作流、测试和本文档文件；不涉及数据库、依赖或生产配置迁移。

## 9. 预期修改文件

- `.github/workflows/ci.yml`
- `.github/workflows/evaluation.yml`
- `backend/tests/acceptance/test_primary_runtime_decision_loop.py`
- `docs/superpowers/specs/2026-09-02-ci-verification-pipeline-design.md`

不创建 harness Batch execution record，因为当前没有明确批准的活动 Batch。
