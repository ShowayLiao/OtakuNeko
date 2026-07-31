# BATCH-01 Execution Record

> Batch: `BATCH-01`
> Task: `TASK-HARNESS-001`
> Start: `2026-07-31 23:04:36 +08:00`
> Branch: `feature-harness`
> Start commit: `95a7406b18539c6910ba6b914d9122fc2490e51c`
> Record status: `ready_for_commit`

## 1. Preflight

### Workspace and prerequisites

- `git status --short`: clean.
- `git branch --show-current`: `feature-harness`.
- `git rev-parse HEAD`: `95a7406b18539c6910ba6b914d9122fc2490e51c`.
- Normal checkout; no linked worktree.
- Previous Batch: BATCH-00 completed; implementation commit `a398da8`, handoff record commit `95a7406`.
- BATCH-01 is the only eligible next Batch in `docs/harness-tasks/INDEX.md`; prerequisite chain is satisfied.
- Allowed changes: `backend/app/api/v1/rss.py`, `backend/app/api/deps.py`, `backend/app/core/config.py`, `.env.example` allowlist documentation, and backend API/acceptance tests; the required execution record is also maintained.
- Forbidden changes: `backend/app/services/qb_service.py`, graph/harness/MCP code, database migrations, dependencies, frontend code, real qB configuration or credentials.

### Authority and source facts checked

- `AGENTS.md`
- `docs/architecture/standard-agent-harness-reference.md`
- `docs/standard-agent-harness-reference-and-codex-audit-guide.md`
- `docs/harness-audit/00-executive-summary.md` through `11-task-backlog.md`
- `docs/harness-tasks/INDEX.md`
- `docs/harness-tasks/BATCH-01/TASK-HARNESS-001.md`
- `docs/code-review.md`
- `docs/harness-execution/README.md` and `TEMPLATE.md`
- Actual source: `backend/app/api/v1/rss.py`, `backend/app/api/deps.py`, `backend/app/core/config.py`, `backend/app/schemas/user.py`, `.env.example`.

### Baseline

| Command | Exit | Result | Notes |
|---|---:|---|---|
| `$env:DEBUG='false'; uv run --no-cache --directory backend pytest tests/agents/test_thread_scope.py tests/agents/test_provider_endpoint.py tests/acceptance/test_harness_baseline.py -q` | 0 | 15 passed | 22 existing Pydantic/pytest-cache warnings |
| `uv run --no-cache --directory backend ruff check app/api/deps.py app/api/v1/rss.py tests/acceptance/test_harness_baseline.py` | 0 | passed | All checks passed |

## 2. Source facts and implementation plan

| Symbol | Current fact | Planned handling |
|---|---|---|
| `app.api.v1.rss` | All seven routes depend only on `check_qb_enabled`; anonymous requests can instantiate `QBService`. | Apply one shared `check_qb_access` dependency to all seven routes; route bodies remain unchanged. |
| `app.api.deps.get_current_user` | Existing JWT/database-backed `UserRead` dependency returns trusted user identity and distinguishes invalid token with 401. | Reuse it; no request/body `user_id` is accepted. |
| `app.core.config.Settings` | No qB user allowlist field exists. | Add `QB_ALLOWED_USER_IDS: str = ""`; parse only positive comma-separated integers and fail closed. |
| `.env.example` | Documents qB host credentials and feature flag only. | Add non-secret allowlist documentation, no credentials. |

## 3. Implementation

Status: implementation complete; remediation round 1 complete; ready for final Review.

### Intended tests

- parser coverage for empty/whitespace, duplicate IDs, valid spacing, and invalid tokens;
- all seven routes reject anonymous and authenticated-but-not-allowed callers before fake `QBService` construction;
- authorized caller reaches every route with the existing request/response shapes;
- disabled qB proxy, empty allowlist, and invalid allowlist fail closed;
- no request/body `user_id` can influence authorization.

### TDD evidence

- Before production changes, the new tests failed against the old route behavior: 6 existing tests passed, 10 new tests failed, and 10 monkeypatch teardown errors occurred because `Settings` had no allowlist field.
- After implementation, the acceptance file passed 23 tests and the scoped ruff check passed.
- Remediation round 1 added a caught conversion failure path for overlong numeric tokens and a regression fixture; the acceptance file then passed 24 tests.

### Changes

- Added `Settings.QB_ALLOWED_USER_IDS: str = ""` and documented the non-secret setting in `.env.example`.
- Added `_parse_qb_allowed_user_ids` with ASCII positive-integer parsing; empty, malformed, zero, and empty tokens fail closed.
- Added `check_qb_access(user=Depends(get_current_user))`, reusing `check_qb_enabled` and rejecting empty/invalid/non-member allowlists with 403.
- Applied `check_qb_access` to all seven RSS endpoints without changing `QBService` operation semantics or accepting request `user_id` values.
- Expanded the existing local fake-service acceptance coverage for anonymous, unauthorized, authorized, invalid configuration, and disabled-proxy paths.

## 4. Verification

| Command | Exit | Result | Known warnings/notes |
|---|---:|---|---|
| `$env:DEBUG='false'; uv run --no-cache --directory backend pytest tests/acceptance/test_harness_baseline.py -q` | 0 | 24 passed | 22 existing Pydantic/pytest-cache warnings |
| `$env:DEBUG='false'; uv run --no-cache --directory backend pytest tests/agents/test_thread_scope.py tests/agents/test_provider_endpoint.py tests/acceptance/test_harness_baseline.py -q` | 0 | 32 passed | 22 existing warnings |
| `$env:DEBUG='false'; uv run --no-cache --directory backend pytest -q` | 0 | 511 passed | 110 existing warnings |
| `uv run --no-cache --directory backend ruff check app tests` | 0 | passed | All checks passed |
| `$env:DEBUG='false'; uv run --no-cache --directory backend python -c "from app.main import app; ..."` | 0 | backend app import smoke passed | No external service started |

No real qBittorrent, external provider, external network, production deployment, or real credential flow was run; the task forbids those side effects. The fake/local acceptance tests cover the required qB route authorization behavior.

## 5. Review

Review follows `docs/code-review.md`: the complete tracked diff, the untracked execution record, scope, secret scan, route dependency count, `git diff --check`, and all verification results were inspected. Review did not modify code.

### Remediation round 1

- Medium finding: an overlong numeric allowlist token could make `int()` raise instead of returning a 403.
- Remediation: parse tokens one by one, catch `ValueError`, return invalid configuration, and add a 5000-digit regression case.
- Re-ran acceptance, task regression, full backend pytest, ruff, and app import smoke after the remediation.

```yaml
review_result:
  batch: BATCH-01
  verdict: pass
  summary: "完整 diff、允许范围、fail-closed 语义和验证结果复核通过；无 blocker、critical、high 或未处理 medium finding。"
  findings: []
  reviewed_commands:
    - "git status --short"
    - "git diff --check"
    - "git diff --stat"
    - "git diff"
    - "uv run --no-cache --directory backend pytest tests/acceptance/test_harness_baseline.py -q"
    - "uv run --no-cache --directory backend pytest tests/agents/test_thread_scope.py tests/agents/test_provider_endpoint.py tests/acceptance/test_harness_baseline.py -q"
    - "uv run --no-cache --directory backend pytest -q"
    - "uv run --no-cache --directory backend ruff check app tests"
    - "uv run --no-cache --directory backend python -c \"from app.main import app; ...\""
  reviewed_files:
    - ".env.example"
    - "backend/app/api/deps.py"
    - "backend/app/api/v1/rss.py"
    - "backend/app/core/config.py"
    - "backend/tests/acceptance/test_harness_baseline.py"
    - "docs/harness-execution/BATCH-01-execution.md"
  deferred_findings:
    - "Allowlist is a server-wide qB resource gate, not per-user qB resource isolation; task explicitly defers resource-level/idempotency work to later Batches."
```

## 6. Handoff

Remediation rounds: 1
Review verdict: `pass`

```yaml
batch_result:
  batch: BATCH-01
  status: ready_for_commit
  commit: null
  tasks_completed:
    - TASK-HARNESS-001
  tests:
    passed:
      - "BATCH-01 acceptance: 24"
      - "task regression: 32"
      - "backend full pytest: 511"
      - "backend ruff"
      - "backend app import smoke"
    failed: []
    skipped:
      - "real qB/provider/external-network flow: forbidden by task scope"
  review:
    verdict: pass
    rounds: 1
    deferred_findings:
      - "server-wide allowlist is not per-user qB resource isolation"
  changed_files:
    - .env.example
    - backend/app/api/deps.py
    - backend/app/api/v1/rss.py
    - backend/app/core/config.py
    - backend/tests/acceptance/test_harness_baseline.py
    - docs/harness-execution/BATCH-01-execution.md
  unresolved_risks:
    - "qB operation idempotency and compensation remain deferred to BATCH-09."
  next_batch: BATCH-02
```
