# CI Verification Pipeline 实现计划

> **面向 AI 代理的执行说明：** 本计划基于
> `docs/superpowers/specs/2026-09-02-ci-verification-pipeline-design.md`，在当前会话内按步骤执行。提交和推送不在范围内。

**目标：** 建立软件正确性、确定性 Harness 回归和离线 Agent benchmark 三层 CI 门禁，并迁移现有 evaluation 工作流的职责边界。

**架构：** 新增 `CI` 工作流，拆分 `software`、`harness`、`benchmark` 三个独立 job；`evaluation.yml` 仅保留定时/手动 observability 与 full evaluation。测试继续调用当前 Runtime、Dispatcher、CapabilityRegistry 和评估 runner。

**技术栈：** GitHub Actions、uv/uv.lock、pytest/Ruff、pnpm/pnpm-lock、Vitest、现有 `app.evaluation.runner`、Fake/Scripted model gateway 和 capability test doubles。

## 任务 1：建立 Harness 循环上限回归测试

**文件：**

- 修改：`backend/tests/acceptance/test_primary_runtime_decision_loop.py`
- 参考：`backend/app/harness/runtime.py:stream_decision`
- 参考：`backend/app/harness/budget.py:RunBudget`

- [ ] **步骤 1：先运行现有 acceptance 基线**

```powershell
uv run --directory backend pytest tests/acceptance/test_primary_runtime_decision_loop.py -q
```

预期：当前测试集通过；记录真实退出码和数量，区分既有失败。

- [ ] **步骤 2：添加确定性重复 Decision 的测试 double 和失败场景测试**

在现有 acceptance 文件中增加仅供测试使用的 gateway，保证每次调用返回新的 `decision_id`，避免 Dispatcher 的幂等缓存掩盖循环行为：

```python
class _RepeatingDecisionGateway:
    def __init__(self, decision: dict) -> None:
        self.decision = decision
        self.calls: list[dict] = []

    async def infer(self, **kwargs) -> ModelCallResult:
        self.calls.append(kwargs)
        return ModelCallResult(
            provider="fake",
            model="fake-model",
            operation="infer",
            status="completed",
            decision={
                **self.decision,
                "decision_id": f"decision-loop-{len(self.calls)}",
            },
        )
```

新增测试使用现有 `_CatalogCapability`、`CapabilityRegistry`、allowlist、`AgentTask` 和 `ExecutionContext`，通过真实 `AgentRuntime.stream_decision` 反复 invoke `catalog.search`，然后断言真实事件和预算计数：

```python
budget = RunBudget(max_steps=2, max_model_calls=8, max_tool_calls=8)
events = [
    event
    async for event in runtime.stream_decision(task, context=context, budget=budget)
]

assert events[-1]["type"] == "run_failed"
assert events[-1]["error_code"] == ErrorCode.BUDGET_EXCEEDED.value
assert not any(event["type"] == "run_completed" for event in events)
assert len(gateway.calls) == 2
assert len(capability.calls) == 2
assert budget.steps_used == 2
assert budget.model_calls_used == 2
assert budget.tool_calls_used == 2
```

已有测试继续负责单步完成、tool feedback、工具超时、取消、provider 失败和非法 Decision；`tests/harness/test_runtime_orchestration.py` 继续负责已有真实多工具 workflow。

- [ ] **步骤 3：运行新增测试，确认行为证据**

```powershell
uv run --directory backend pytest tests/acceptance/test_primary_runtime_decision_loop.py::test_primary_runtime_stops_repeating_decisions_at_step_budget -q
```

预期：PASS；如果失败，只调查 Runtime 现有行为，不通过放宽断言或修改生产逻辑制造通过结果。

- [ ] **步骤 4：运行 acceptance 与 harness 相关回归**

```powershell
uv run --directory backend pytest tests/harness tests/acceptance tests/capabilities tests/trace -q
uv run --directory backend ruff check app/harness app/capabilities app/trace tests/harness tests/acceptance tests/capabilities tests/trace
```

预期：PASS；记录完整退出码、通过/跳过数量和既有 warning。

## 任务 2：新增 PR/push CI 工作流

**文件：**

- 创建：`.github/workflows/ci.yml`
- 参考：`backend/pyproject.toml`、`frontend/package.json`、`frontend/pnpm-lock.yaml`

- [ ] **步骤 1：添加只读触发器、权限和并发设置**

```yaml
name: CI

on:
  pull_request:
    branches: [main]
  push:
    branches: [main]

permissions:
  contents: read

concurrency:
  group: ci-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true
```

不在工作流中配置 secrets、provider credentials 或外部 API。

- [ ] **步骤 2：实现 `software` job**

后端步骤固定为 checkout、setup uv、`uv sync --locked --dev`、`uv run ruff check app tests`、`uv run pytest`。

前端步骤使用 Node 20.19.0、pnpm 10.15.1 和 `frontend/pnpm-lock.yaml`，依次运行：

```text
pnpm install --frozen-lockfile
pnpm lint
pnpm typecheck
pnpm test
pnpm build
```

每条命令都作为普通失败步骤执行，不使用 `continue-on-error` 或错误吞掉逻辑。

- [ ] **步骤 3：实现 `harness` job**

使用独立的 uv 安装步骤和下列确定性验证命令：

```text
uv run pytest tests/harness tests/acceptance tests/capabilities tests/trace -q
uv run ruff check app/harness app/capabilities app/trace tests/harness tests/acceptance tests/capabilities tests/trace
```

该 job 不需要模型 API key。

- [ ] **步骤 4：实现 `benchmark` job 和 artifact**

运行：

```text
uv run python -m app.evaluation.runner --config evals/config/fast.yaml
```

上传 `backend/.runtime/evaluation/fast.json`。上传步骤允许使用 `if: always()` 保存失败诊断，但 benchmark runner 的退出码仍直接决定 job 成败。

- [ ] **步骤 5：检查工作流静态契约**

```powershell
rg -n "pull_request|push:|branches:|permissions:|continue-on-error|OPENAI_API_KEY|uv sync|pnpm install|evaluation.runner|upload-artifact" .github/workflows/ci.yml
```

预期：只有 `contents: read` 权限；CI 没有 secret/live provider；三项 job 均存在；没有 `continue-on-error` 或 `|| true`。

## 任务 3：迁移现有 evaluation 工作流职责

**文件：**

- 修改：`.github/workflows/evaluation.yml`
- 参考：`backend/evals/config/observability.yaml`
- 参考：`backend/evals/config/full.yaml`

- [ ] **步骤 1：保留定时和手动触发**

移除 PR/push 触发，仅保留 schedule 和 workflow dispatch，并声明 `contents: read`。

- [ ] **步骤 2：保留 observability evaluation**

将现有 fast job 的职责收窄为运行：

```text
uv run python -m app.evaluation.runner --config evals/config/observability.yaml
```

继续上传 `.runtime/evaluation/observability.json`，不删除该评估职责。

- [ ] **步骤 3：保留 full evaluation 的受限 secret 边界**

full job 继续只在 schedule/workflow dispatch 执行，保留 `OPENAI_API_KEY` 环境变量和 full report artifact。不得把该 secret 或 full config 引入 `ci.yml`。

- [ ] **步骤 4：检查迁移后的职责分离**

```powershell
rg -n "pull_request|push:|schedule:|workflow_dispatch|OPENAI_API_KEY|fast.yaml|observability.yaml|full.yaml" .github/workflows/evaluation.yml .github/workflows/ci.yml
```

预期：fast evaluation 只在 `ci.yml`；observability/full 仍在 `evaluation.yml`；普通测试只在 `ci.yml`。

## 任务 4：按本地契约运行完整验证

**文件：** 无新增文件；只验证任务 1–3 的变更。

- [ ] **步骤 1：运行后端完整验证**

```powershell
uv run --directory backend pytest
uv run --directory backend ruff check app tests
```

- [ ] **步骤 2：运行前端完整验证**

```powershell
pnpm --dir frontend lint
pnpm --dir frontend typecheck
pnpm --dir frontend test
pnpm --dir frontend build
```

- [ ] **步骤 3：运行 Harness 和 benchmark**

```powershell
uv run --directory backend pytest tests/harness tests/acceptance tests/capabilities tests/trace -q
uv run --directory backend python -m app.evaluation.runner --config evals/config/fast.yaml
```

记录 benchmark 的总案例数、通过数、pass rate、阈值/baseline 结果、报告路径和命令退出码。

- [ ] **步骤 4：完成完整 diff 自审**

```powershell
git status --short
git diff --check
git diff --stat
git diff -- .github/workflows/ci.yml .github/workflows/evaluation.yml backend/tests/acceptance/test_primary_runtime_decision_loop.py docs/superpowers/specs/2026-09-02-ci-verification-pipeline-design.md docs/superpowers/plans/2026-09-02-ci-verification-pipeline.md
```

确认：没有业务代码、依赖、数据库、secret、缓存、生成报告或用户已有 `README.md` 修改；工作流没有绕过失败；没有提交或推送。

## 任务 5：交付前审查与报告

- [ ] 按 `docs/code-review.md` 格式审查完整未提交 diff，逐项确认 blocker/critical/high/medium finding。
- [ ] 若发现问题，先修复，再重新运行所有受影响检查并重新审查完整 diff。
- [ ] 使用 verification-before-completion 的真实命令输出作为证据，不宣称未运行项目通过。
- [ ] 最终报告包含：仓库审计、CI 架构、Fake loop、benchmark、命令、PASS/FAIL/SKIPPED、变更文件、剩余 gap、下一步建议。
- [ ] 明确工作区原有 `README.md` 修改未被触碰。
- [ ] 不执行 `git add`、`git commit`、`git push`。
