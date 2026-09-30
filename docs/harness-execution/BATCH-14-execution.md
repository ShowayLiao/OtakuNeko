# BATCH-14 Execution Record

> Batch: `BATCH-14`
> Task: `TASK-POST-AUDIT-001`
> Start: `2026-08-01 19:00 Asia/Shanghai`
> Branch: `feature-harness`
> Start commit: `65d48429144c97699862494807e31fb9f1a591e2`
> Status: `completed`

## 1. Preflight

- Pre-existing user-owned planning changes were preserved: `docs/harness-tasks/INDEX.md`, `docs/harness-audit/12-post-batch13-current-audit.md`, `docs/harness-execution/POST-AUDIT-EXECUTION-PLAN.md`, and `docs/harness-tasks/POST-AUDIT-UNIFIED-RUNTIME/`.
- Branch: `feature-harness`.
- No linked worktree was present.
- BATCH-13 is complete at the start commit.
- Task scope was limited to Harness/Agent/API wiring, backend tests, and verification record. Domain Service rules, qB writes/migrations, frontend protocol names, and deletion of `ALL_TOOLS` were not changed.

### Baseline commands

| Command | Exit | Result |
|---|---:|---|
| `uv run --no-cache --directory backend pytest tests/harness tests/acceptance -q` | 0 | 115 passed, 1 skipped, 37 warnings |
| `uv run --no-cache --directory backend ruff check app tests` | 0 | All checks passed |
| `pnpm.cmd --dir frontend test` | 0 | 41 passed in 9 files |
| `pnpm.cmd --dir frontend typecheck` | 0 | Passed |
| `pnpm.cmd --dir frontend build` | 0 | Next.js build passed, 8 routes generated |

The first uv invocation without `--no-cache` failed because the local uv cache was not writable; the first sandbox pnpm invocation failed with Windows workspace `EPERM`. Both were rerun with the same project command and the permitted environment, with the successful results above recorded.

## 2. Source facts and implementation

- `ChatWorkflow` still owns LangGraph message/checkpoint mechanics, but its ToolNode now receives proposal-only wrappers. It no longer directly executes legacy `ALL_TOOLS` callables.
- Proposal output is versioned and includes `decision_id`, `run_id`, canonical public capability name, and public argument keys. `model_decision` and `tool_requested` are adapted as bounded RunEvents.
- `DecisionParser` validates provider-neutral results, rejects invalid versions, malformed/multiple tool calls, authority fields, and oversized arguments without retaining raw provider payloads.
- `Dispatcher` resolves the canonical Registry action, applies Policy/approval/idempotency checks before adapter execution, injects only trusted `ExecutionContext`, enforces timeout/cancellation, normalizes exceptions, and emits matching invocation start/end events.
- `AgentRuntime.execute_decision()` drives `ModelGateway -> DecisionParser -> Dispatcher -> next Decision/respond` under one budget/cancellation boundary.
- The HTTP primary path creates a trusted `ExecutionContext` from the authenticated user and installs the Dispatcher-backed proposal handler. The legacy routed specialist is fail-closed out of the primary canary until it is migrated to Dispatcher.

## 3. TDD and verification

| Command | Exit | Result |
|---|---:|---|
| `uv run --no-cache --directory backend pytest tests/harness/test_decision_parser.py tests/harness/test_dispatcher.py tests/acceptance/test_primary_decision_path.py -q` | 0 | 20 passed |
| `uv run --no-cache --directory backend pytest tests/agents/test_graph_dual_node.py tests/agents/test_workflow_lifecycle.py tests/harness tests/acceptance -q` | 0 | 174 passed, 1 skipped, 37 warnings |
| `uv run --no-cache --directory backend pytest` | 0 | 648 passed, 1 skipped, 142 warnings |
| `uv run --no-cache --directory backend ruff check app tests` | 0 | All checks passed |
| `pnpm.cmd --dir frontend test` | 0 | 41 passed in 9 files |
| `pnpm.cmd --dir frontend typecheck` | 0 | Passed |
| `pnpm.cmd --dir frontend build` | 0 | Passed; 8 routes generated |
| `uv run --no-cache --directory backend python -m app.evaluation.runner --config evals/config/observability.yaml` | 0 | 14/14 passed, 100% |
| `git diff --check` | 0 | Passed; only LF/CRLF warnings |

The first full backend run exposed 13 Graph failures caused by the proposal wrapper assuming a capability Registry on the legacy ToolRegistry. That was remediated within TASK-001, then the focused suite and full suite were rerun successfully.

## 4. Review

```yaml
review_result:
  batch: BATCH-14
  task: TASK-POST-AUDIT-001
  verdict: pass
  remediation_rounds: 1
  findings: []
  reviewed_commands:
    - git diff --check
    - uv run --no-cache --directory backend pytest
    - uv run --no-cache --directory backend ruff check app tests
    - pnpm.cmd --dir frontend test
    - pnpm.cmd --dir frontend typecheck
    - pnpm.cmd --dir frontend build
    - uv run --no-cache --directory backend python -m app.evaluation.runner --config evals/config/observability.yaml
  deferred_findings:
    - TASK-002 must unify durable invocation identity and RunCoordinator lifecycle.
    - TASK-003 must migrate routed subagents/MCP/side effects to the same Dispatcher boundary.
```

## 5. Handoff

```yaml
batch_result:
  batch: BATCH-14
  status: completed
  commit: null
  tasks_completed:
    - TASK-POST-AUDIT-001
  tests:
    passed:
      - backend pytest: 648 passed
      - backend ruff: passed
      - frontend test: 41 passed
      - frontend typecheck/build: passed
      - observability Eval: 14/14
    failed: []
    skipped:
      - backend pytest: 1 existing skip
  review:
    verdict: pass
    rounds: 1
    deferred_findings:
      - TASK-002 durable Run/cancel/recovery ownership
      - TASK-003 Capability/Tool/MCP/side-effect convergence
  changed_files:
    - backend/app/agents/graph.py
    - backend/app/agents/langgraph_adapter.py
    - backend/app/api/v1/agent.py
    - backend/app/harness/capability_adapter.py
    - backend/app/harness/contracts.py
    - backend/app/harness/decision_parser.py
    - backend/app/harness/dispatcher.py
    - backend/app/harness/model_gateway.py
    - backend/app/harness/model_types.py
    - backend/app/harness/runtime.py
    - backend/tests/acceptance/test_primary_decision_path.py
    - backend/tests/harness/test_decision_parser.py
    - backend/tests/harness/test_dispatcher.py
    - docs/harness-execution/BATCH-14-execution.md
  unresolved_risks:
    - A ChatWorkflow constructed without a proposal handler is proposal-only and must not be treated as an execution entry point.
    - Durable Dispatcher event persistence, cancellation/recovery, and scheduler convergence remain for later tasks.
  rollback: Remove the TASK-001 files/changes and restore the primary adapter wiring; do not remove existing Run/Event data or user planning documents.
  next_batch: TASK-POST-AUDIT-002
```
