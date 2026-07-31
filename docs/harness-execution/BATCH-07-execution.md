# BATCH-07 Execution Record

> Batch: `BATCH-07`
> Task: `TASK-HARNESS-007`
> Started: `2026-08-01 00:35 Asia/Shanghai`
> Branch: `feature-harness`
> Starting commit: `a2d1d42aee38f6fbb3f010e5acda2100ff1c385b`
> Record status: `in_progress`

## 1. Preflight

### Workspace and prerequisites

```text
git status --short: clean (Git ignore/cache access warnings only)
git branch --show-current: feature-harness
git rev-parse HEAD: a2d1d42aee38f6fbb3f010e5acda2100ff1c385b
Previous Batch commit: BATCH-06 implementation 4519f51; handoff finalization a2d1d42
Allowed files: backend/app/api/v1/agent.py; optional new backend/app/api/v1/run.py; frontend/src/app/api/v1/chat/route.ts; frontend/src/lib/fetcher.ts; frontend/src/hooks/useChatStreaming.ts; listed BATCH-07 tests; this execution record
Forbidden files: backend/app/models and Alembic, Run/Event schemas and persistence schema; backend/app/agents/graph.py; Tool/Capability and Model Gateway implementations; frontend chat-storage persistence; replay by resubmitting POST
```

### Authoritative materials

- `docs/architecture/standard-agent-harness-reference.md`
- `docs/standard-agent-harness-reference-and-codex-audit-guide.md`
- `docs/harness-audit/00-executive-summary.md` through `11-task-backlog.md`
- `docs/harness-tasks/INDEX.md`
- `docs/harness-tasks/BATCH-07/TASK-HARNESS-007.md`
- `docs/code-review.md`

### Source facts and dependency check

| File/symbol | Observed behavior | Batch expectation | Handling |
|---|---|---|---|
| `backend/app/api/v1/agent.py::chat_endpoint` | POST `/chat` emits `event`/`data` and `stream_sequence`; it does not emit SSE `id` or `run_id`, and it does not inject BATCH-06 stores into `AgentRuntime` | Expose durable Run identity and terminal status without changing legacy event names | Add API projection/wiring only in the allowed route file |
| `frontend/src/lib/fetcher.ts::chatWithBackend` | Parses only `event`/`data`; EOF calls `onComplete`; network errors call `onError`; no Last-Event-ID/replay path | Track SSE id/run cursor and replay events after disconnect without POST resubmission | Extend callback compatibility layer and add replay helper |
| `frontend/src/hooks/useChatStreaming.ts::stopGeneration` | Aborts the request and marks pending process nodes as `success`, then stores message status `completed` | Abort must not be interpreted as successful terminal status | Change stop/error status handling and consume server terminal status |
| `backend/app/harness/persistence.EventStore` | BATCH-06 provides scoped append/list-after with bounded redacted JSON payloads | Projection must reuse durable events and not change schema | Use existing `RunStore`/`EventStore` from the API route |
| `frontend/next.config.ts::rewrites` | `/api/:path*` is rewritten to backend, while chat route explicitly forwards auth headers | Replay endpoint must be reachable without a new persistence layer | Use same-origin `/api/v1/runs/...` under existing rewrite; only alter chat proxy if tests require it |
| `backend/app/api/deps.py` | `get_current_user` is the authenticated owner dependency; optional auth is used only for chat | Run/Event reads must fail closed with 404 across users/threads | Require `get_current_user` and validate stored user/thread scope |

### Baseline commands

| Command | Exit | Passed | Failed | Skipped | Notes |
|---|---:|---:|---:|---:|---|
| `$env:DEBUG='false'; uv run --no-cache --directory backend pytest tests/trace/test_sql_store.py -q` | 0 | 7 | 0 | 0 | 40 deprecation warnings |
| `cd frontend && pnpm vitest run src/lib/fetcher.test.ts src/app/api/v1/chat/route.test.ts` | 0 | 3 | 0 | 0 | 2 test files passed |

## 2. Implementation log

### Scope

- Add authenticated Run status and Event replay projections backed by BATCH-06 durable stores.
- Include SSE `id`/`run_id` metadata while preserving existing `event` names and data callbacks.
- Add frontend cursor tracking and replay-only reconnection; do not resubmit the original POST.
- Ensure abort, missing terminal status, and failed/cancelled terminal statuses cannot be stored as success.

### Compatibility and rollback

- Existing chat POST path, SSE event names, callback signatures and `chat-storage` format remain compatible; new metadata is additive.
- Existing same-origin `/api` rewrite remains the replay transport; disabling the replay wiring leaves the legacy single-request stream path available.
- Rollback is limited to reverting the BATCH-07 route/fetcher/hook/test changes; BATCH-06 Run/Event data and schema remain intact.
- Remediation round 1 corrected SSE ids to use the persisted RunEvent cursor, paged frontend replay at the EventStore page boundary, and aligned route durability with `INTERACTIVE_RUN_STORE_ENABLED`.

## 3. Verification

| Command | Exit | Passed | Failed | Skipped | Warnings/notes |
|---|---:|---:|---:|---:|---|
| `$env:DEBUG='false'; uv run --no-cache --directory backend pytest tests/acceptance/test_sse_replay.py tests/trace/test_sql_store.py -q` | 0 | 10 | 0 | 0 | 68 deprecation warnings |
| `$env:DEBUG='false'; uv run --no-cache --directory backend pytest -q` | 0 | 559 | 0 | 1 | 132 warnings; one existing skip |
| `uv run --no-cache --directory backend ruff check app tests` | 0 | n/a | n/a | n/a | All checks passed |
| `pnpm.cmd vitest run src/lib/fetcher.test.ts src/app/api/v1/chat/route.test.ts` | 0 | 4 | 0 | 0 | 2 test files |
| `pnpm.cmd test` | 0 | 41 | 0 | 0 | 9 test files |
| `pnpm.cmd typecheck` | 0 | n/a | n/a | n/a | TypeScript check passed |
| `pnpm.cmd lint` | 0 | n/a | n/a | n/a | 99 existing warnings, 0 errors |
| `pnpm.cmd build` | 0 | n/a | n/a | n/a | Next.js production build passed |
| `git diff --check` | 0 | n/a | n/a | n/a | No whitespace errors; Git emitted environment ignore/cache warnings |

Not-run items and reasons: PostgreSQL/live provider/manual browser checks were not run because this Batch is covered by SQLite/fake-provider tests and no live external side effect or production deployment is permitted. Full migration, deployment, and production checks are outside this Batch.

## 4. Review

```yaml
review_result:
  batch: BATCH-07
  kind: batch
  verdict: pass
  summary: "Full uncommitted diff reviewed against the BATCH-07 task, harness invariants, authorization boundaries, replay semantics, compatibility requirements, and rollback plan. One remediation round corrected durable cursor mapping, replay pagination, and disabled-store behavior."
  findings: []
  reviewed_commands:
    - command: "$env:DEBUG='false'; uv run --no-cache --directory backend pytest -q"
      exit_code: 0
    - command: "uv run --no-cache --directory backend ruff check app tests"
      exit_code: 0
    - command: "pnpm.cmd test"
      exit_code: 0
    - command: "pnpm.cmd typecheck"
      exit_code: 0
    - command: "pnpm.cmd lint"
      exit_code: 0
    - command: "pnpm.cmd build"
      exit_code: 0
    - command: "git diff --check"
      exit_code: 0
  reviewed_files:
    - backend/app/api/v1/agent.py
    - backend/tests/acceptance/test_sse_replay.py
    - frontend/src/lib/fetcher.ts
    - frontend/src/lib/fetcher.test.ts
    - frontend/src/hooks/useChatStreaming.ts
    - docs/harness-execution/BATCH-07-execution.md
  deferred_findings: []
```

Remediation rounds: 1. No blocker, critical, high, or unresolved medium findings remain.

## 5. Handoff

```yaml
batch_result:
  batch: BATCH-07
  status: ready_to_commit
  commit: null
  tasks_completed:
    - TASK-HARNESS-007
  tests:
    passed:
      - "backend: 559 passed, 1 skipped"
      - "frontend: 41 passed"
      - "backend/frontend lint, typecheck, and build passed"
    failed: []
    skipped:
      - "Existing backend test skip; PostgreSQL/live provider/manual browser checks not run"
  review:
    verdict: pass
    rounds: 1
    deferred_findings: []
  changed_files:
    - backend/app/api/v1/agent.py
    - backend/tests/acceptance/test_sse_replay.py
    - frontend/src/lib/fetcher.ts
    - frontend/src/lib/fetcher.test.ts
    - frontend/src/hooks/useChatStreaming.ts
    - docs/harness-execution/BATCH-07-execution.md
  unresolved_risks:
    - "Existing backend deprecation/cache warnings and frontend lint warnings remain outside this Batch."
    - "Provider/tool cancellation and checkpoint restart recovery remain assigned to BATCH-08 as specified by the task."
  next_batch: BATCH-08
```
