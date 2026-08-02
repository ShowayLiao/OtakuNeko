# BATCH-20 Execution Record

> Batch: `BATCH-20`
> Task: `TASK-POST-AUDIT-011`
> Start: `2026-08-01 22:47 Asia/Shanghai`
> Branch: `feature-harness`
> Start commit: `65d48429144c97699862494807e31fb9f1a591e2`
> Status: `completed`

## Preflight

- 前置 TASK-POST-AUDIT-006 已在 BATCH-19 execution record 中标记 completed，Review verdict 为 pass；其 canary 和 legacy rollback flag 保留。
- BATCH-14～19 的未提交源码、测试、审计和执行文档属于既有用户工作树，全部保留，不执行 reset/checkout/restore。
- 本 Batch 只修改 ModelGateway contract、model types/budget/runtime/coordinator、相关 Harness/Acceptance tests 和本 execution record。
- 不切换 `/chat` 默认 flag，不删除 LangGraph compatibility adapter，不升级 provider 依赖，不写入 Secret/raw provider payload。

## Baseline

| Command | Exit | Result |
|---|---:|---|
| `$env:DEBUG='false'; uv run --no-cache --directory 'E:\\HACCI\\Documents\\tools\\OtakuNeko\\backend' pytest -q` | 0 | 675 passed, 1 skipped, 140 warnings |
| `uv run --no-cache --directory 'E:\\HACCI\\Documents\\tools\\OtakuNeko\\backend' ruff check app tests` | 0 | All checks passed |
| `pnpm.cmd --dir 'E:\\HACCI\\Documents\\tools\\OtakuNeko\\frontend' lint` | 0 | 0 errors, 99 warnings |
| `pnpm.cmd --dir 'E:\\HACCI\\Documents\\tools\\OtakuNeko\\frontend' typecheck` | 0 | Passed |
| `pnpm.cmd --dir 'E:\\HACCI\\Documents\\tools\\OtakuNeko\\frontend' test` | 0 | 9 files, 41 tests passed |
| `pnpm.cmd --dir 'E:\\HACCI\\Documents\\tools\\OtakuNeko\\frontend' build` | 0 | Next.js build passed, 8 routes generated |

## TDD / implementation

- 首轮 focused 红灯：`pytest tests/harness/test_model_gateway_cancellation.py tests/acceptance/test_primary_runtime_decision_loop.py -q`，退出码 1，5 failed / 7 passed；失败分别证明 provider task 未受 cancellation/deadline 控制、`CancelledError` 被 adapter 吞掉，以及 Runtime 会把模型 cancelled/timeout 先交给 Parser 并产生 `run_failed`。
- 最小实现：ModelGateway 增加 provider-neutral `cancellation`、`deadline`、`budget` contract；统一 `_run_with_controls()` 负责 provider task 竞速、取消后回收、deadline 终止和 caller cancellation 传播；所有 Provider adapter 不再捕获 `asyncio.CancelledError`/`GeneratorExit`；Runtime 在 DecisionParser 前映射模型 terminal result，并把 controls 传入 `infer()`；legacy synthesis 复用相同控制边界。
- 绿灯 focused：13 个 Runtime/ModelGateway contract tests 通过；追加 synthesis boundary remediation 后，ModelGateway/Coordinator/相关测试 24 passed。

## Verification

| Command | Exit | Result |
|---|---:|---|
| `$env:DEBUG='false'; uv run --no-cache --directory 'E:\\HACCI\\Documents\\tools\\OtakuNeko\\backend' pytest tests/harness/test_model_gateway_cancellation.py tests/acceptance/test_primary_runtime_decision_loop.py -q` | 1 | 首轮红灯：5 failed, 7 passed |
| `$env:DEBUG='false'; uv run --no-cache --directory 'E:\\HACCI\\Documents\\tools\\OtakuNeko\\backend' pytest tests/harness/test_model_gateway_cancellation.py tests/acceptance/test_primary_runtime_decision_loop.py -q --disable-warnings` | 0 | 13 passed；追加 synthesis remediation 前 |
| `$env:DEBUG='false'; uv run --no-cache --directory 'E:\\HACCI\\Documents\\tools\\OtakuNeko\\backend' pytest tests/harness/test_model_gateway_cancellation.py::test_gateway_synthesis_uses_the_same_cancellation_boundary -q --disable-warnings` | 1 | Review remediation 红灯：1 failed |
| `$env:DEBUG='false'; uv run --no-cache --directory 'E:\\HACCI\\Documents\\tools\\OtakuNeko\\backend' pytest tests/harness/test_model_gateway_cancellation.py tests/harness/test_coordinator.py tests/harness/test_model_gateway.py -q --disable-warnings` | 0 | 24 passed |
| `uv run --no-cache --directory 'E:\\HACCI\\Documents\\tools\\OtakuNeko\\backend' ruff check app/harness/model_gateway.py app/harness/coordinator.py tests/harness/test_model_gateway_cancellation.py` | 0 | All checks passed |
| `$env:DEBUG='false'; uv run --no-cache --directory 'E:\\HACCI\\Documents\\tools\\OtakuNeko\\backend' pytest -q --disable-warnings` | 0 | 683 passed, 1 skipped, 140 warnings |
| `uv run --no-cache --directory 'E:\\HACCI\\Documents\\tools\\OtakuNeko\\backend' ruff check app tests` | 0 | All checks passed |
| `$env:DEBUG='false'; uv run --no-cache --directory 'E:\\HACCI\\Documents\\tools\\OtakuNeko\\backend' python -m app.evaluation.runner --config evals/config/fast.yaml` | 0 | 9/9 passed, 100.0% |
| `$env:DEBUG='false'; uv run --no-cache --directory 'E:\\HACCI\\Documents\\tools\\OtakuNeko\\backend' python -m app.evaluation.runner --config evals/config/observability.yaml` | 0 | 14/14 passed, 100.0% |
| `pnpm.cmd --dir 'E:\\HACCI\\Documents\\tools\\OtakuNeko\\frontend' lint` | 0 | 0 errors, 99 warnings |
| `pnpm.cmd --dir 'E:\\HACCI\\Documents\\tools\\OtakuNeko\\frontend' typecheck` | 0 | Passed |
| `pnpm.cmd --dir 'E:\\HACCI\\Documents\\tools\\OtakuNeko\\frontend' test` | 0 | 9 files, 41 tests passed |
| `pnpm.cmd --dir 'E:\\HACCI\\Documents\\tools\\OtakuNeko\\frontend' build` | 0 | Next.js build passed, 8 routes generated |
| `git -C 'E:\\HACCI\\Documents\\tools\\OtakuNeko' diff --check` | 0 | No diff errors; existing CRLF/permission warnings only |

## Review

```yaml
review_result:
  batch: BATCH-20
  task: TASK-POST-AUDIT-011
  verdict: pass
  remediation_rounds: 1
  findings: []
  deferred_findings:
    - "Canonical Run/Invocation/Result/Event persistence and SSE fact-source convergence remain BATCH-22 / TASK-POST-AUDIT-007."
    - "Legacy LangGraph default-path retirement and primary API cutover remain BATCH-26 / TASK-POST-AUDIT-010; this Batch does not change the rollback flag."
```

## Handoff

```yaml
batch_result:
  batch: BATCH-20
  status: completed
  commit: null
  tasks_completed:
    - TASK-POST-AUDIT-011
  tests:
    passed:
      - 683 backend tests
      - backend Ruff
      - 13 focused ModelGateway/Runtime contract tests
      - 24 ModelGateway/Coordinator regression tests
      - fast Eval 9/9
      - observability Eval 14/14
      - frontend lint with 0 errors and 99 warnings
      - 41 frontend tests
      - frontend typecheck and build
      - git diff --check
    failed:
      - 5-test initial red run, fixed by this Batch
      - 1-test synthesis remediation red run, fixed before final verification
    skipped:
      - 1 backend test in the full suite
  review:
    verdict: pass
    rounds: 1
    deferred_findings:
      - TASK-POST-AUDIT-007 canonical persistence/SSE pipeline
      - TASK-POST-AUDIT-010 default cutover and legacy retirement
  changed_files:
    - backend/app/harness/model_gateway.py
    - backend/app/harness/coordinator.py
    - backend/app/harness/runtime.py
    - backend/tests/harness/test_model_gateway_cancellation.py
    - backend/tests/acceptance/test_primary_runtime_decision_loop.py
    - docs/harness-execution/BATCH-20-execution.md
  unresolved_risks:
    - "The primary /chat default remains the BATCH-19 legacy-compatible path until canonical persistence and replay parity are closed; HARNESS_PRIMARY_DECISION_LOOP_ENABLED was not changed."
    - "Provider stream compatibility adapters retain their existing event interface; BATCH-20 hardens the controlled complete/synthesis boundaries used by Runtime and leaves primary default cutover to BATCH-26."
  rollback: "Restore only the BATCH-20 ModelGateway/Coordinator/Runtime contract changes and focused tests after preserving this execution record; keep BATCH-14 through BATCH-19 and all canonical safety constraints. No git reset/checkout/restore or commit was performed."
  next_batch: BATCH-21 / TASK-POST-AUDIT-012
```
