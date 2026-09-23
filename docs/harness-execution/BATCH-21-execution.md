# BATCH-21 Execution Record

> Batch: `BATCH-21`
> Task: `TASK-POST-AUDIT-012`
> Start: `2026-08-01 23:03 Asia/Shanghai`
> Branch: `feature-harness`
> Start commit: `65d48429144c97699862494807e31fb9f1a591e2`
> Status: `completed`

## Preflight

- BATCH-20 / TASK-POST-AUDIT-011 is completed with Review verdict `pass`.
- Existing BATCH-14 through BATCH-20 worktree changes are preserved; no reset, checkout, restore, commit, push, or deployment is performed.
- This Batch is limited to the ResultNormalizer, authority contract, Dispatcher/MCP safe boundaries, focused tests, and this execution record.
- The `/chat` default flag and legacy LangGraph compatibility path are unchanged; default cutover remains BATCH-26.

## Baseline

| Command | Exit | Result |
|---|---:|---|
| `uv run --directory backend pytest` | 0 | 683 passed, 1 skipped, 140 warnings |
| `uv run --directory backend ruff check app tests` | 0 | All checks passed |
| `pnpm.cmd --dir frontend lint` | 0 | 0 errors, 99 warnings |
| `pnpm.cmd --dir frontend typecheck` | 0 | Passed |
| `pnpm.cmd --dir frontend test` | 0 | 9 files, 41 tests passed |
| `pnpm.cmd --dir frontend build` | 0 | Next.js build passed, 8 routes generated |
| fast Eval | 0 | 9/9 passed |
| observability Eval | 0 | 14/14 passed |

## TDD / implementation

- Initial red run: `uv run --no-cache --directory backend pytest tests/harness/test_result_normalizer.py -q`, exit `1`, 3 failed / 2 passed. The failures demonstrated that Dispatcher bypassed input schema validation and passed invalid/oversized output as `succeeded`.
- Implemented one authority contract in `backend/app/harness/authority.py`, one ResultNormalizer boundary in `backend/app/harness/normalizer.py`, Dispatcher pre-execution input validation and safe result mapping, model-safe versus UI-safe projections, stable successful-invocation reuse, and MCP v1 compatibility projection from normalized output.
- Reused the authority contract from Contract validators, DecisionParser, CapabilityAdapter, CapabilityRegistry schema projection, and MCP schema/argument handling.
- Remediation: one existing MCP exact-envelope regression was fixed by an explicit compatibility envelope derived from normalized safe data; no raw output path was restored.

## Verification

| Command | Exit | Result |
|---|---:|---|
| `uv run --no-cache --directory backend pytest tests/harness/test_result_normalizer.py tests/harness/test_dispatcher.py tests/harness/test_contracts.py tests/mcp/test_server.py -q --disable-warnings` | 0 | 35 passed |
| `uv run --no-cache --directory backend pytest -q --disable-warnings` | 0 | 690 passed, 1 skipped, 140 warnings |
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
  batch: BATCH-21
  task: TASK-POST-AUDIT-012
  verdict: pass
  remediation_rounds: 1
  findings: []
  deferred_findings:
    - "Canonical durable Run/Invocation/Result/Event persistence and API fact-source convergence remain BATCH-22 / TASK-POST-AUDIT-007."
    - "Context and Memory provenance/trust propagation remain BATCH-23 / TASK-POST-AUDIT-008."
    - "Legacy CapabilityAgent/LangGraph bypass retirement and default API cutover remain BATCH-26 / TASK-POST-AUDIT-010."
```

## Handoff

```yaml
batch_result:
  batch: BATCH-21
  status: completed
  commit: null
  tasks_completed:
    - TASK-POST-AUDIT-012
  tests:
    passed:
      - 690 backend tests
      - backend Ruff
      - 35 focused normalizer/dispatcher/contract/MCP tests
      - fast Eval 9/9
      - observability Eval 14/14
      - frontend lint with 0 errors and 99 existing warnings
      - 41 frontend tests
      - frontend typecheck and build
      - git diff --check
    failed:
      - 3-test initial red run, fixed by this Batch
      - 1 existing MCP envelope regression during remediation, fixed before final verification
    skipped:
      - 1 backend test in the full suite
    review:
      verdict: pass
      rounds: 1
      deferred_findings:
        - TASK-POST-AUDIT-007 canonical persistence/SSE pipeline
        - TASK-POST-AUDIT-008 ContextManager and Memory provenance
        - TASK-POST-AUDIT-010 legacy retirement and default cutover
  changed_files:
    - backend/app/harness/authority.py
    - backend/app/harness/normalizer.py
    - backend/app/harness/contracts.py
    - backend/app/harness/decision_parser.py
    - backend/app/harness/capability_adapter.py
    - backend/app/harness/dispatcher.py
    - backend/app/harness/runtime.py
    - backend/app/capabilities/registry.py
    - backend/app/mcp_server/__init__.py
    - backend/tests/harness/test_result_normalizer.py
    - docs/harness-execution/BATCH-21-execution.md
  unresolved_risks:
    - "Canonical durable event and invocation persistence is not yet the single API fact source; BATCH-22 is required."
    - "CapabilityAgent and legacy LangGraph paths remain compatibility paths until BATCH-26; no default cutover was made."
    - "MCP retains an explicit v1 structured-data envelope adapter, derived only from normalized safe output."
  rollback: "Restore only the BATCH-21 authority/normalizer/dispatcher/runtime/registry/MCP changes and focused tests after preserving this execution record; keep BATCH-14 through BATCH-20 and canonical safety constraints. No git reset/checkout/restore or commit was performed."
  next_batch: BATCH-22 / TASK-POST-AUDIT-007
```
