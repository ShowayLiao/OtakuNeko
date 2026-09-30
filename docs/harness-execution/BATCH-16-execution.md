# BATCH-16 Execution Record

> Batch: `BATCH-16`
> Task: `TASK-POST-AUDIT-003`
> Start: `2026-08-01 19:35 Asia/Shanghai`
> Branch: `feature-harness`
> Start commit: `65d48429144c97699862494807e31fb9f1a591e2`
> Status: `completed`

## Preflight

- BATCH-15 was complete with review pass; its uncommitted changes were preserved.
- No linked worktree was present. User planning documents remain unclassified user changes.
- TASK-003 was limited to capability/tool/MCP/side-effect boundary files and corresponding tests.
- Domain service business semantics and unrelated dependencies remained out of scope.

Baseline:

| Command | Exit | Result |
|---|---:|---|
| `uv run --no-cache --directory backend pytest tests/capabilities tests/harness tests/mcp tests/services -q` | 0 | 249 passed, 1 skipped, 35 warnings |
| `uv run --no-cache --directory backend ruff check app tests` | 0 | All checks passed |

## TDD / implementation

The new acceptance boundary contract was added before the implementation. It verifies model-owned identity rejection and fail-closed side-effect dispatch when no idempotency store is available.

Implemented:

- Canonical Registry/ActionDescriptor public metadata remains the source for capability and adapter discovery; public schemas now remove `user_id`, `principal_id`, `db`, and `token` recursively.
- CapabilityAdapter rejects model-owned fields, accepts canonical/public action names, injects trusted dependencies and identity, and requires policy approval plus durable idempotency for side effects.
- CapabilityAgent routes declared side effects through an adapter/context and preserves only explicit legacy read-only fixture compatibility.
- MCP calls now construct a trusted `ExecutionContext` and use CapabilityAdapter/PolicyEngine; public schema exposure and MCP write replay/conflict behavior remain fail-closed.
- Schedule HTTP create/update/delete and legacy upsert/bulk/delete-all/sync writes now use trusted owner scope, approval or authenticated owner context, payload hashing, durable idempotency and unknown-state attention handling.
- Structured Decision contracts reject model-owned authority fields including nested values; primary proposals are dispatched only by the canonical Dispatcher.

## Verification

Diagnostic failures were recorded and remediated rather than hidden:

| Command | Exit | Result |
|---|---:|---|
| `$env:DEBUG='false'; uv run --no-cache --directory backend pytest tests/acceptance/test_capability_boundary.py tests/capabilities -q` | 0 | 62 passed, 21 warnings |
| `$env:DEBUG='false'; uv run --no-cache --directory backend pytest tests/harness tests/mcp -q` | 0 | 170 passed, 1 skipped, 31 warnings |
| `$env:DEBUG='false'; uv run --no-cache --directory backend pytest -q` | 0 | 656 passed, 1 skipped, 140 warnings |
| `$env:DEBUG='false'; uv run --no-cache --directory backend ruff check app tests` | 0 | All checks passed |
| `pnpm.cmd --dir frontend lint` | 0 | 0 errors, 99 warnings |
| `pnpm.cmd --dir frontend test` | 0 | 9 files passed, 41 tests passed |
| `pnpm.cmd --dir frontend typecheck` | 0 | Passed |
| `pnpm.cmd --dir frontend build` | 0 | Next production build passed; 8 routes generated |
| `$env:DEBUG='false'; uv run --no-cache --directory backend python -m app.evaluation.runner --config evals/config/observability.yaml` | 0 | 14/14 evaluations passed |
| `git diff --check` | 0 | Passed; only existing LF/CRLF warnings |

The first combined diagnostic run exited `124` after partial failures. Split runs identified a legacy fake capability without `actions()`, an MCP context type mismatch, and the inherited non-boolean shell `DEBUG=release`; the code issues were fixed and the final commands above were rerun with `DEBUG=false`.

## Review

```yaml
review_result:
  batch: BATCH-16
  task: TASK-POST-AUDIT-003
  verdict: pass
  remediation_rounds: 1
  findings:
    - initial review required trusted run_id injection for tool-call decisions and complete Schedule write idempotency coverage
  resolved_findings:
    - DecisionParser validates or injects the trusted Runtime run_id before Dispatcher execution
    - Schedule delete-all and Bangumi sync are covered by durable idempotency wrappers
    - db/token authority fields are removed from public schemas and rejected in model arguments
  deferred_findings:
    - qB resource ownership semantics remain fail-closed and require a separately verified resource model before any LLM write exposure
    - routed specialist execution remains disabled until its direct capability path is migrated to the same Dispatcher boundary
    - shared-worker cancellation transport and deployment checkpoint consistency remain TASK-004 concerns
```

## Handoff

```yaml
batch_result:
  batch: BATCH-16
  status: completed
  commit: null
  tasks_completed:
    - TASK-POST-AUDIT-003
  tests:
    passed: 656
    failed: 0
    skipped: 1
  review:
    verdict: pass
    rounds: 1
    deferred_findings:
      - qB resource model verification before write exposure
      - routed specialist Dispatcher migration
      - shared-worker cancellation and deployment checkpoint consistency
  changed_files:
    - backend/app/api/v1/endpoints/schedules.py
    - backend/app/capabilities/langchain_adapter.py
    - backend/app/capabilities/registry.py
    - backend/app/harness/capability_adapter.py
    - backend/app/harness/contracts.py
    - backend/app/harness/decision_parser.py
    - backend/app/harness/dispatcher.py
    - backend/app/mcp_server/__init__.py
    - backend/tests/acceptance/test_capability_boundary.py
    - backend/tests/harness/test_decision_parser.py
    - backend/tests/harness/test_dispatcher.py
    - docs/harness-execution/BATCH-16-execution.md
  unresolved_risks:
    - No production deployment or multi-worker MCP cancellation test was run.
    - Existing frontend callers of schedule mutation endpoints must provide Idempotency-Key.
  rollback: Remove only TASK-003 implementation, acceptance-test, and BATCH-16 record changes; preserve BATCH-14, BATCH-15, and user planning documents. No commit was created.
  next_batch: BATCH-17 / TASK-POST-AUDIT-004
```
