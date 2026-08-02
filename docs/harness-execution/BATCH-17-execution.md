# BATCH-17 Execution Record

> Batch: `BATCH-17`
> Task: `TASK-POST-AUDIT-004`
> Start: `2026-08-01 20:10 Asia/Shanghai`
> Branch: `feature-harness`
> Start commit: `65d48429144c97699862494807e31fb9f1a591e2`
> Status: `completed`

## Preflight

- BATCH-16 / TASK-POST-AUDIT-003 completed with review pass; its uncommitted changes are preserved.
- No linked worktree is present. User planning, audit, task, and INDEX changes remain preserved and are not attributed to this Batch.
- TASK-004 is limited to model usage/budget, memory namespace/extraction, checkpoint/deployment consistency, provider endpoint safety, and corresponding tests.
- No provider replacement, BYOK strategy change, production migration, or production deployment will be performed.

Baseline:

| Command | Exit | Result |
|---|---:|---|
| `$env:DEBUG='false'; uv run --no-cache --directory backend pytest tests/harness tests/memory tests/agents/test_provider_endpoint.py tests/agents/test_graph_checkpoint.py tests/agents/test_workflow_lifecycle.py tests/agents/test_langgraph_adapter.py tests/acceptance -q` | 0 | 250 passed, 1 skipped, 90 warnings |
| `$env:DEBUG='false'; uv run --no-cache --directory backend ruff check app tests` | 0 | All checks passed |

## TDD / implementation

The first TASK-004 change must be a failing contract/acceptance test for model usage/budget, memory run namespace, and provider DNS/redirect validation. Implementation begins only after recording that red result.

Red result recorded before implementation:

| Command | Exit | Result |
|---|---:|---|
| `$env:DEBUG='false'; uv run --no-cache --directory backend pytest tests/acceptance/test_task_post_audit_004_contract.py -q` | 1 | 5 failed, 2 warnings: missing call/trace fields, fixed empty Memory namespace, missing DNS resolver and redirect contract |

Implemented provider-neutral call correlation and usage normalization, shared Run checkpoint namespace mapping, budget/cancellation-aware Memory extraction through `ModelGateway`, DNS rebinding/IPv6/private-address checks, fail-closed redirect handling, and local/cloud Alembic/checkpoint startup boundaries.

## Verification

| Command | Exit | Result |
|---|---:|---|
| `$env:DEBUG='false'; uv run --no-cache --directory backend pytest tests/harness/test_model_gateway.py tests/memory/test_api.py tests/acceptance/test_task_post_audit_004_contract.py tests/agents/test_provider_endpoint.py -q` | 0 | 25 passed, 38 warnings |
| `$env:DEBUG='false'; uv run --no-cache --directory backend pytest -q` | 0 | 665 passed, 1 skipped, 140 warnings |
| `uv run --no-cache --directory backend ruff check app tests` | 0 | All checks passed |
| `uv run --no-cache --directory backend python -m alembic heads` | 0 | Head `c7d1e4f8a2b6` resolved; no migration executed |
| `pnpm.cmd --dir frontend lint` | 0 | 0 errors, 99 warnings |
| `pnpm.cmd --dir frontend test` | 0 | 9 files passed, 41 tests passed |
| `pnpm.cmd --dir frontend typecheck` | 0 | TypeScript check passed |
| `pnpm.cmd --dir frontend build` | 0 | Next.js build passed; 8 routes generated |
| `$env:DEBUG='false'; uv run --no-cache --directory backend python -m app.evaluation.runner --config evals/config/observability.yaml` | 0 | 14 passed, 0 failed, 100% |
| `git diff --check` | 0 | No whitespace errors |

## Review

```yaml
review_result:
  batch: BATCH-17
  task: TASK-POST-AUDIT-004
  verdict: pass
  remediation_rounds: 1
  findings:
    - "Fixed synthesis result contract annotation and wired fail-closed provider redirect validation."
    - "Preserved compatibility with legacy Memory test doubles without weakening the primary run-aware path."
  deferred_findings: []
```

## Handoff

```yaml
batch_result:
  batch: BATCH-17
  status: completed
  commit: null
  tasks_completed:
    - TASK-POST-AUDIT-004
  tests:
    passed:
      - "Backend: 665 passed, 1 skipped"
      - "Ruff: passed"
      - "Frontend: 41 passed; lint/typecheck/build passed"
      - "Eval: 14/14"
    failed: []
    skipped:
      - "1 backend test skipped as reported by pytest"
  review:
    verdict: pass
    rounds: 1
    deferred_findings: []
  changed_files:
    - backend/Dockerfile
    - backend/app/agents/graph.py
    - backend/app/agents/provider_endpoint.py
    - backend/app/api/v1/agent.py
    - backend/app/core/config.py
    - backend/app/harness/checkpoint.py
    - backend/app/harness/model_gateway.py
    - backend/app/harness/model_types.py
    - backend/app/main.py
    - backend/app/memory/extractor.py
    - backend/app/memory/interfaces.py
    - backend/app/memory/manager.py
    - backend/app/memory/service.py
    - backend/tests/acceptance/test_task_post_audit_004_contract.py
    - docker-compose.yml
    - docs/harness-execution/BATCH-17-execution.md
  unresolved_risks:
    - "Shared multi-worker checkpoint adapter is not implemented; cloud compose is explicitly single-worker with SQLite."
    - "Legacy MemoryManager retains a compatibility direct-provider fallback; the primary API uses run-aware LLMFactExtractor through ModelGateway."
  rollback: Remove only TASK-004 changes listed above; preserve BATCH-14 through BATCH-16 and user planning documents. Do not run production downgrade automatically.
  next_batch: BATCH-18 / TASK-POST-AUDIT-005
```
