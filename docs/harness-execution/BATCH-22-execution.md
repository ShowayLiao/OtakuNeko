# BATCH-22 Execution Record

> Batch: `BATCH-22`
> Task: `TASK-POST-AUDIT-007`
> Start: `2026-08-01 23:25 Asia/Shanghai`
> Branch: `feature-harness`
> Start commit: `65d48429144c97699862494807e31fb9f1a591e2`
> Status: `completed`

## Preflight

- BATCH-21 / TASK-POST-AUDIT-012 is completed with Review verdict `pass`.
- Existing BATCH-14 through BATCH-21 worktree changes are preserved; no reset, checkout, restore, commit, push, or deployment is performed.
- This Batch is limited to the primary Runtime canonical Run/Invocation/Result/Event persistence path, replay-safe SSE projection, persistence focused tests, and this execution record.
- The legacy LangGraph default path and `HARNESS_PRIMARY_DECISION_LOOP_ENABLED` default remain unchanged; default cutover is BATCH-26.

## Baseline

| Command | Exit | Result |
|---|---:|---|
| `uv run --no-cache --directory backend pytest -q --disable-warnings` | 0 | 690 passed, 1 skipped, 140 warnings |
| `uv run --no-cache --directory backend ruff check app tests` | 0 | All checks passed |
| `pnpm.cmd --dir frontend lint` | 0 | 0 errors, 99 warnings |
| `pnpm.cmd --dir frontend typecheck` | 0 | Passed |
| `pnpm.cmd --dir frontend test` | 0 | 9 files, 41 tests passed |
| `pnpm.cmd --dir frontend build` | 0 | Next.js build passed, 8 routes generated |
| fast Eval | 0 | 9/9 passed |
| observability Eval | 0 | 14/14 passed |

## TDD / implementation

- Initial red run: `uv run --no-cache --directory backend pytest tests/acceptance/test_primary_runtime_canonical_persistence.py -q`, exit `1`, 2 failed. The primary Runtime produced no durable EventStore facts and persistence failure was not represented in the Run state.
- Implemented Runtime-owned canonical start, ordered event append, durable Invocation creation/finish, terminal Run transition, idempotent terminal replay, and persistence-failure fail-closed handling.
- Primary chat SSE now serializes the already committed Runtime event using its canonical sequence as SSE `id`; the API does not create a second event or add diagnostics to the canonical primary projection.
- Added fake-store and real SQL acceptance coverage for ordered replay, stable invocation correlation, duplicate terminal replay, and persistence failure.

## Verification

| Command | Exit | Result |
|---|---:|---|
| `uv run --no-cache --directory backend pytest tests/acceptance/test_primary_runtime_canonical_persistence.py -q --disable-warnings` | 0 | 4 passed |
| `uv run --no-cache --directory backend pytest tests/acceptance/test_primary_runtime_decision_loop.py tests/acceptance/test_sse_replay.py tests/acceptance/test_run_persistence.py tests/acceptance/test_runtime_single_owner.py -q --disable-warnings` | 0 | 19 passed |
| `uv run --no-cache --directory backend pytest -q --disable-warnings` | 0 | 694 passed, 1 skipped, 155 warnings |
| `uv run --no-cache --directory backend ruff check app tests` | 0 | All checks passed |
| `uv run --no-cache --directory backend python -m app.evaluation.runner --config evals/config/fast.yaml` | 0 | 9/9 passed, 0 failed, 100.0% |
| `uv run --no-cache --directory backend python -m app.evaluation.runner --config evals/config/observability.yaml` | 0 | 14/14 passed, 0 failed, 100.0% |
| `pnpm.cmd --dir frontend lint` | 0 | 0 errors, 99 existing warnings |
| `pnpm.cmd --dir frontend typecheck` | 0 | Passed |
| `pnpm.cmd --dir frontend test` | 0 | 9 files, 41 tests passed |
| `pnpm.cmd --dir frontend build` | 0 | Next.js build passed, 8 routes generated |
| `git -C 'E:\\HACCI\\Documents\\tools\\OtakuNeko' diff --check` | 0 | No diff errors; existing CRLF/permission warnings only |

Frontend package-manager commands required the approved escalated workspace execution because sandbox-only pnpm access returned `EPERM` before the command ran. No frontend source files were changed by this Batch.

## Review

```yaml
review_result:
  batch: BATCH-22
  task: TASK-POST-AUDIT-007
  verdict: pass
  remediation_rounds: 1
  findings: []
  deferred_findings:
    - "Legacy Coordinator/LangGraph persistence remains a compatibility path until BATCH-26 / TASK-POST-AUDIT-010 retires the bypass."
    - "Durable cancellation races, leases, and recovery remain BATCH-24 / TASK-POST-AUDIT-009."
    - "Context and Memory provenance/trust propagation remain BATCH-23 / TASK-POST-AUDIT-008."
```

## Handoff

```yaml
batch_result:
  batch: BATCH-22
  status: completed
  commit: null
  tasks_completed:
    - TASK-POST-AUDIT-007
  tests:
    passed:
      - 694 backend tests
      - backend Ruff
      - 4 canonical primary persistence tests
      - 19 persistence/primary/SSE regression tests
      - fast Eval 9/9
      - observability Eval 14/14
      - frontend lint with 0 errors and 99 existing warnings
      - 41 frontend tests
      - frontend typecheck and build
      - git diff --check
    failed:
      - 2-test initial red run, fixed by this Batch
    skipped:
      - 1 backend test in the full suite
    review:
      verdict: pass
      rounds: 1
      deferred_findings:
        - TASK-POST-AUDIT-008 ContextManager and Memory provenance
        - TASK-POST-AUDIT-009 durable cancellation/lease/recovery
        - TASK-POST-AUDIT-010 legacy retirement and default cutover
  changed_files:
    - backend/app/harness/runtime.py
    - backend/app/api/v1/agent.py
    - backend/tests/acceptance/test_primary_runtime_canonical_persistence.py
    - docs/harness-execution/BATCH-22-execution.md
  unresolved_risks:
    - "The primary canary path is canonical and replayable, but the legacy default remains unchanged until BATCH-26; legacy persistence is still owned by compatibility Coordinator code."
    - "A cancellation request racing with in-flight primary terminal persistence is deferred to BATCH-24."
    - "EventStore and RunStore are separate commits; a cross-store crash leaves an auditable recovery state, with final default hardening deferred to BATCH-24."
  rollback: "Restore only the BATCH-22 primary Runtime/SSE changes and focused tests after preserving this execution record; keep BATCH-14 through BATCH-21 and canonical safety constraints. No git reset/checkout/restore or commit was performed."
  next_batch: BATCH-23 / TASK-POST-AUDIT-008
```
