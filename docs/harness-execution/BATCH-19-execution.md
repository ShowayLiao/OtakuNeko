# BATCH-19 Execution Record

> Batch: `BATCH-19`
> Task: `TASK-POST-AUDIT-006`
> Start: `2026-08-01 21:10 Asia/Shanghai`
> Branch: `feature-harness`
> Start commit: `65d48429144c97699862494807e31fb9f1a591e2`
> Status: `completed`

## Preflight

- TASK-POST-AUDIT-006 is the first task in `UNIFIED-RUNTIME-CONSOLIDATION` and is explicitly started by the user request.
- BATCH-14 through BATCH-18 remain uncommitted and are preserved.
- Existing user-owned changes in `AGENTS.md`, architecture/reference documents, audit documents, task documents and execution plans are preserved.
- This Batch is limited to the primary Runtime Decision Loop seam, ModelGateway/contract compatibility, API wiring and acceptance/harness tests.
- No Domain Service rule, dependency, production data, production migration or deployment environment will be changed.

Baseline:

| Command | Exit | Result |
|---|---:|---|
| `$env:DEBUG='false'; uv run --no-cache --directory 'E:\HACCI\Documents\tools\OtakuNeko\backend' pytest -q` | 0 | 669 passed, 1 skipped, 140 warnings |
| `uv run --no-cache --directory 'E:\HACCI\Documents\tools\OtakuNeko\backend' ruff check app tests` | 0 | All checks passed |

## TDD / implementation

The primary-path contract test was added before implementation. The initial focused run returned exit `1` because `AgentRuntime.stream_decision` and `_primary_decision_loop_enabled` did not yet exist. After implementation, the focused contract suite passed. A follow-up red assertion caught that a dispatcher string `timeout` was being collapsed to `tool_error`; the Runtime now maps terminal invocation status to the canonical timeout/cancelled code.

The implementation adds a Runtime-owned streaming Decision Loop and an explicit API canary switch: `HARNESS_PRIMARY_DECISION_LOOP_ENABLED=true`. The default remains `false` until TASK-POST-AUDIT-007 makes durable Invocation/Event persistence and SSE projection canonical. This is an intentional migration gate, not a claim that the old LangGraph loop has already been retired.

Review remediation removed a duplicate `thinking_start` emitted by the API before the Runtime-owned stream. The legacy path retains its early flush; the canary path now emits the event only from `stream_decision()`.

## Verification

| Command | Exit | Result |
|---|---:|---|
| `$env:DEBUG='false'; uv run --no-cache --directory 'E:\HACCI\Documents\tools\OtakuNeko\backend' pytest tests/acceptance/test_primary_runtime_decision_loop.py -q` | 1 | Expected red run before implementation: missing Runtime API/flag |
| `$env:DEBUG='false'; uv run --no-cache --directory 'E:\HACCI\Documents\tools\OtakuNeko\backend' pytest tests/acceptance/test_primary_runtime_decision_loop.py -q` | 0 | 6 passed, 22 warnings |
| `$env:DEBUG='false'; uv run --no-cache --directory 'E:\HACCI\Documents\tools\OtakuNeko\backend' ruff check app/harness/runtime.py app/api/v1/agent.py tests/acceptance/test_primary_runtime_decision_loop.py` | 0 | All checks passed |
| `$env:DEBUG='false'; uv run --no-cache --directory 'E:\HACCI\Documents\tools\OtakuNeko\backend' pytest tests/acceptance/test_primary_runtime_decision_loop.py tests/acceptance/test_primary_harness_flow.py tests/acceptance/test_primary_harness_security.py tests/acceptance/test_primary_harness_recovery.py tests/acceptance/test_primary_harness_side_effects.py -q` | 0 | 10 passed, 22 warnings |
| `$env:DEBUG='false'; uv run --no-cache --directory 'E:\HACCI\Documents\tools\OtakuNeko\backend' pytest -q` | 0 | 675 passed, 1 skipped, 140 warnings |
| `$env:DEBUG='false'; uv run --no-cache --directory 'E:\HACCI\Documents\tools\OtakuNeko\backend' ruff check app tests` | 0 | All checks passed |
| `pnpm.cmd --dir 'E:\HACCI\Documents\tools\OtakuNeko\frontend' lint` | 0 | 0 errors, 99 warnings |
| `pnpm.cmd --dir 'E:\HACCI\Documents\tools\OtakuNeko\frontend' test` | 0 | 9 files passed, 41 tests passed |
| `pnpm.cmd --dir 'E:\HACCI\Documents\tools\OtakuNeko\frontend' typecheck` | 0 | TypeScript check passed |
| `pnpm.cmd --dir 'E:\HACCI\Documents\tools\OtakuNeko\frontend' build` | 0 | Next.js production build passed; 8 routes generated |
| `$env:DEBUG='false'; uv run --no-cache --directory 'E:\HACCI\Documents\tools\OtakuNeko\backend' python -m app.evaluation.runner --config evals/config/fast.yaml` | 0 | 9 passed, 0 failed, 100.0% |
| `$env:DEBUG='false'; uv run --no-cache --directory 'E:\HACCI\Documents\tools\OtakuNeko\backend' python -m app.evaluation.runner --config evals/config/observability.yaml` | 0 | 14 passed, 0 failed, 100.0% |
| `$env:DEBUG='false'; uv run --no-cache --directory 'E:\HACCI\Documents\tools\OtakuNeko\backend' pytest tests/acceptance/test_primary_runtime_decision_loop.py tests/acceptance/test_primary_harness_flow.py tests/acceptance/test_primary_harness_security.py tests/acceptance/test_primary_harness_recovery.py tests/acceptance/test_primary_harness_side_effects.py -q` | 0 | Remediation rerun: 10 passed, 22 warnings |
| `$env:DEBUG='false'; uv run --no-cache --directory 'E:\HACCI\Documents\tools\OtakuNeko\backend' pytest -q` | 0 | Remediation rerun: 675 passed, 1 skipped, 140 warnings |
| `$env:DEBUG='false'; uv run --no-cache --directory 'E:\HACCI\Documents\tools\OtakuNeko\backend' ruff check app tests` | 0 | Remediation rerun: all checks passed |
| `git -C 'E:\HACCI\Documents\tools\OtakuNeko' diff --check` | 0 | No diff errors; existing CRLF/permission warnings only |

## Review

```yaml
review_result:
  batch: BATCH-19
  task: TASK-POST-AUDIT-006
  verdict: pass
  remediation_rounds: 1
  findings: []
  deferred_findings:
    - "Canonical durable Invocation/Event persistence and SSE cursor projection remain TASK-POST-AUDIT-007."
    - "The new Decision Loop is an explicit canary; default enablement remains gated until TASK-POST-AUDIT-007."
```

## Handoff

```yaml
batch_result:
  batch: BATCH-19
  status: completed
  commit: null
  tasks_completed:
    - TASK-POST-AUDIT-006 (Runtime-owned Decision Loop canary seam)
  tests:
    passed:
      - 6 primary Runtime Decision Loop contract tests
      - 10 primary Harness/Decision Loop acceptance tests
      - 675 backend tests
      - backend Ruff
      - 41 frontend tests
      - frontend typecheck and build
      - fast Eval 9/9
      - observability Eval 14/14
      - frontend lint with 0 errors and 99 warnings
      - git diff --check
    failed: []
    skipped:
      - 1 backend test in the full suite
  review:
    verdict: pass
    rounds: 1
    deferred_findings:
      - TASK-POST-AUDIT-007 canonical persistence/SSE pipeline
      - Default cutover remains gated by the explicit canary flag
  changed_files:
    - backend/app/api/v1/agent.py
    - backend/app/harness/runtime.py
    - backend/tests/acceptance/test_primary_runtime_decision_loop.py
    - docs/harness-tasks/UNIFIED-RUNTIME-CONSOLIDATION/TASK-POST-AUDIT-006.md
    - docs/harness-execution/BATCH-19-execution.md
  unresolved_risks:
    - "LangGraph remains the default compatibility path while durable canonical event persistence is not yet wired into stream_decision."
    - "The current task tests Runtime entry and API flag selection; a real main API fake-provider Eval remains TASK-POST-AUDIT-010."
  rollback: Restore the primary chat legacy flag and remove only TASK-POST-AUDIT-006 changes; preserve BATCH-14 through BATCH-18 and user documents.
  next_batch: TASK-POST-AUDIT-007
```
