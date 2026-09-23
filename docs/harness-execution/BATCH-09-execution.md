# BATCH-09 Execution Record

> Batch: `BATCH-09`
> Task: `TASK-HARNESS-009`
> Started: `2026-08-01 01:35 Asia/Shanghai`
> Branch: `feature-harness`
> Starting commit: `92a42fb06ebacf2ecf81947189bd99b666ef4b97`
> Record status: `completed`

## 1. Preflight

### Workspace and prerequisites

```text
Initial git status: clean except Git ignore/pytest-cache permission warnings
Branch: feature-harness
Starting HEAD: 92a42fb06ebacf2ecf81947189bd99b666ef4b97
Prerequisite implementation commits:
  BATCH-01 57da25a
  BATCH-02 336006b
  BATCH-03 8488d32
  BATCH-04 116e6ef
  BATCH-05 ae5b796
  BATCH-06 4519f51
  BATCH-07 ff35cda
  BATCH-08 4a33fbf (handoff record 92a42fb)
```

The user explicitly authorized the BATCH-09 recovery: update the stale authorized baseline and add the missing persistence adapter using the existing BATCH-06 tables/port. No qB instance, database migration, Graph, frontend protocol, or Capability files were changed.

### Loaded authoritative material

- `AGENTS.md`
- `docs/architecture/standard-agent-harness-reference.md`
- `docs/standard-agent-harness-reference-and-codex-audit-guide.md`
- Current conclusions in `docs/harness-audit/`
- `docs/harness-tasks/INDEX.md`
- `docs/harness-tasks/BATCH-09/TASK-HARNESS-009.md`
- `docs/code-review.md`
- `docs/harness-execution/TEMPLATE.md`

Audit and task plan are complete. BATCH-09 was the first eligible Batch after BATCH-08.

### Baseline

| Command | Exit code | Passed | Failed | Skipped | Notes |
|---|---:|---:|---:|---:|---|
| `$env:DEBUG='false'; uv run --no-cache --directory backend pytest tests/acceptance/test_harness_baseline.py tests/mcp/test_policy.py -q` | 0 | 42 | 0 | 0 | 22 warnings; cache permission warnings |

## 2. Source facts and resolved mismatch

| File/symbol | Source fact | Resolution |
|---|---|---|
| `TASK-HARNESS-009` compatibility requirements | Missing write `idempotency_key` must return 422/400; no auto-generated key | Enforced with required printable-ASCII schema fields |
| `tests/acceptance/test_harness_baseline.py::_rss_requests` | Existing write payloads omitted the key | User authorized this baseline update; valid requests now carry explicit keys |
| `test_authorized_user_can_reach_all_qb_routes` | Existing assertion expected 200 for all seven routes | Retained 200 for valid keyed writes and added a missing-key 422 test |
| `backend/app/harness/persistence/` before BATCH-09 | No `IdempotencyStore`/`execute_once` existed despite task background | Added `IdempotencyStore`/SQL adapter on existing `AgentRun`, `AgentInvocation`, and `AgentRunEvent`; no migration |

## 3. Implementation

- Added a required 1–128 printable-ASCII `idempotency_key` to all qB write schemas.
- Added authenticated principal, operation, hashed resource scope, canonical payload hash, and `execute_once` routing for every qB write route. Read routes remain unchanged and do not require a key.
- Added durable replay/conflict/attention handling. Stable results are stored as safe Run Events, and a restart or an in-flight unknown state does not invoke qB again.
- Refactored `QBService` to use fixed safe error codes/messages, never log URL/rule/payload/password/raw downstream exception text, and mark only connection failures as retryable.
- Implemented upsert `read -> no-op/plan -> remove_old -> add_new -> verify` with one bounded old-resource compensation attempt and queryable `attention_required` result.
- Preserved qB external method names, request parameters, and same URL/name no-op behavior.
- Added API, service, durable restart, compensation, redaction, scope, conflict, and baseline regression tests.

### Compatibility and rollback

- Valid keyed writes retain successful 200 responses; missing or unsafe keys fail before qB with 422.
- qB reads retain their existing paths and response models.
- Rollback is the local BATCH-09 implementation commit and its handoff finalization commit; no external qB resources or database schema changes need rollback.

## 4. Verification

| Command | Exit code | Passed | Failed | Skipped | Known warnings |
|---|---:|---:|---:|---:|---|
| `$env:DEBUG='false'; uv run --no-cache --directory backend pytest tests/api/test_rss_idempotency.py tests/services/test_qb_service.py tests/mcp/test_policy.py -q` | 0 | 31 | 0 | 0 | 26 warnings |
| `$env:DEBUG='false'; uv run --no-cache --directory backend pytest tests/api/test_rss_idempotency.py tests/services/test_qb_service.py tests/acceptance/test_harness_baseline.py -q` | 0 | 38 | 0 | 0 | 26 warnings |
| `$env:DEBUG='false'; uv run --no-cache --directory backend pytest -q` | 0 | 582 | 0 | 1 | 136 warnings; existing Pydantic/SQLModel deprecations and cache permission warnings |
| `$env:DEBUG='false'; uv run --no-cache --directory backend ruff check app tests` | 0 | all checks | 0 | 0 | none |
| `git diff --check` | 0 | - | - | - | CRLF conversion warnings only from Git |

Not run: frontend checks, Docker checks, real qB instance, external network, and production migrations; BATCH-09 is backend-only and forbids those external side effects/schema changes.

## 5. Review

```yaml
review_result:
  batch: BATCH-09
  kind: batch
  verdict: pass
  summary: "Full uncommitted BATCH-09 diff reviewed after remediation; no blocker, critical, high, or unhandled medium findings."
  findings: []
  reviewed_commands:
    - command: "$env:DEBUG='false'; uv run --no-cache --directory backend pytest tests/api/test_rss_idempotency.py tests/services/test_qb_service.py tests/mcp/test_policy.py -q"
      exit_code: 0
    - command: "$env:DEBUG='false'; uv run --no-cache --directory backend pytest -q"
      exit_code: 0
    - command: "$env:DEBUG='false'; uv run --no-cache --directory backend ruff check app tests"
      exit_code: 0
    - command: "git diff --check"
      exit_code: 0
  reviewed_files:
    - backend/app/schemas/rss.py
    - backend/app/api/v1/rss.py
    - backend/app/services/qb_service.py
    - backend/app/harness/persistence/idempotency.py
    - backend/tests/api/test_rss_idempotency.py
    - backend/tests/services/test_qb_service.py
    - backend/tests/acceptance/test_harness_baseline.py
    - docs/harness-execution/BATCH-09-execution.md
  deferred_findings:
    - id: REVIEW-009-001
      severity: medium
      category: authorization
      detail: "qB RSS resources remain instance-global; this Batch scopes idempotency by authenticated principal and preserves the existing allowlist, but does not invent per-resource ownership without a domain model."
      owner: "qB/domain authorization follow-up"
      reason: "Task explicitly forbids expanding the resource model and requires this risk to be reported."
```

Remediation rounds: 1. The review pass corrected the public `IdempotencyStore` port name and restored the existing `upsert(name=request.name)` call semantics; the complete verification suite was rerun afterward.

## 6. Handoff

```yaml
batch_result:
  batch: BATCH-09
  status: committed
  commit: "6fc15cc8bab2cd18600e942b016e82ac5a57ef61"
  tasks_completed:
    - "qB write schema idempotency keys"
    - "authenticated scoped replay/conflict persistence"
    - "safe qB error taxonomy and logging"
    - "bounded upsert compensation and attention state"
    - "API/service/baseline regression tests"
  tests:
    passed:
      - "31 targeted regression tests"
      - "38 BATCH-09 plus acceptance tests"
      - "582 full backend tests"
      - "ruff check app tests"
    failed: []
    skipped:
      - "1 optional full-backend test (external PostgreSQL URL not configured)"
  review:
    verdict: pass
    rounds: 1
    deferred_findings:
      - "qB instance-global resource ownership remains governed by existing allowlist; follow-up required before claiming per-resource isolation."
  changed_files:
    - backend/app/schemas/rss.py
    - backend/app/api/v1/rss.py
    - backend/app/services/qb_service.py
    - backend/app/harness/persistence/idempotency.py
    - backend/tests/api/test_rss_idempotency.py
    - backend/tests/services/test_qb_service.py
    - backend/tests/acceptance/test_harness_baseline.py
    - docs/harness-execution/BATCH-09-execution.md
  unresolved_risks:
    - "qB resource ownership is instance-global; retain and verify the allowlist for every write route."
  next_batch: "After local commit and INDEX reread, evaluate BATCH-10 eligibility."
```
