# BATCH-10 Execution Record

> Batch: `BATCH-10`
> Task: `TASK-HARNESS-010`
> Started: `2026-08-01 Asia/Shanghai`
> Branch: `feature-harness`
> Starting commit: `cb0845251bcdd38795af25451eb3cf4582e09c7e`
> Record status: `completed`

## 1. Preflight

### Workspace and prerequisites

```text
git status --short: clean except Git ignore/pytest-cache permission warnings
git branch --show-current: feature-harness
git rev-parse HEAD: cb0845251bcdd38795af25451eb3cf4582e09c7e
Prerequisite implementation commits:
  BATCH-01 57da25a
  BATCH-02 336006b
  BATCH-03 8488d32
  BATCH-04 116e6ef
  BATCH-05 ae5b796
  BATCH-06 4519f51
  BATCH-07 ff35cda
  BATCH-08 4a33fbf
  BATCH-09 6fc15cc
```

### Loaded authoritative material

- `AGENTS.md`
- `docs/architecture/standard-agent-harness-reference.md`
- `docs/standard-agent-harness-reference-and-codex-audit-guide.md`
- Current conclusions in `docs/harness-audit/`
- `docs/harness-tasks/INDEX.md`
- `docs/harness-tasks/BATCH-10/TASK-HARNESS-010.md`
- `docs/code-review.md`
- `docs/harness-execution/TEMPLATE.md`

Audit and task plan are complete. BATCH-10 is the first eligible Batch after BATCH-09.

### Baseline

| Command | Exit code | Passed | Failed | Skipped | Notes |
|---|---:|---:|---:|---:|---|
| `$env:DEBUG='false'; uv run --no-cache --directory backend pytest tests/capabilities/test_schedule.py tests/capabilities/test_langchain_adapter.py tests/harness/test_capability_adapter.py tests/mcp/test_policy.py -q` | 0 | 34 | 0 | 0 | 20 warnings; cache permission warnings |

## 2. Source facts and design decision

| File/symbol | Actual behavior | BATCH-10 treatment |
|---|---|---|
| `ScheduleCapability.actions()` | Public descriptors include `user_id`; write key metadata is incomplete | Remove public identity; require explicit write keys in the adapter while preserving MCP policy-key compatibility |
| `langchain_adapter._build_runtime_tool()` | Removes and then reinjects model-visible identity before direct capability execution | Route through `CapabilityAdapter` with trusted `ExecutionContext` |
| `harness.policy` | Contains only `ProactivePolicy` | Add `Principal`, trusted `Approval`, and default-deny `PolicyEngine` |
| `harness.capability_adapter` | `CapabilityAgent` directly invokes a Capability | Add context-aware policy/idempotency adapter and preserve legacy agent wrapper |
| `harness.persistence.idempotency` | BATCH-09 provides durable `IdempotencyStore` and test port | Reuse the existing port; do not modify persistence or schema |
| `ScheduleService` | Owns transaction and resource authorization through explicit user ID | Keep unchanged; adapter injects principal-derived service arguments |

Three implementation options were evaluated. The selected option is to inject the existing BATCH-06/BATCH-09 idempotency port into the new `CapabilityAdapter`, carry approval only as trusted adapter state, and keep public model arguments identity-free. This preserves durability and the task file boundaries without adding a migration or weakening default deny.

## 3. Implementation record

- Removed `user_id` and `principal_id` from the Schedule public action schemas and LangChain-generated tool schemas.
- Added trusted `Principal`, server-side `Approval`, default-deny `PolicyEngine`, and typed policy decisions.
- Added `CapabilityAdapter.execute(context, action, public_args)` with identity spoofing rejection, capability allowlist checks, trusted principal injection, policy/approval/idempotency gates, scoped replay/conflict handling, and safe exception results.
- Reused the existing BATCH-06/BATCH-09 `IdempotencyStore` port. Idempotent writes are wrapped with explicit succeeded/failed status before persistence and unwrapped back to `CapabilityResult`-compatible output.
- Preserved `CapabilityAgent` and existing MCP/HTTP compatibility paths; `ScheduleService` was not modified.
- Added regression coverage for schema redaction, principal injection, read authentication, policy deny, approval, missing key, replay, conflict, principal scope isolation, and spoofed identity.

## 4. Verification

| Command | Exit code | Passed | Failed | Skipped | Known warnings |
|---|---:|---:|---:|---:|---|
| `$env:DEBUG='false'; uv run --no-cache --directory backend pytest tests/capabilities/test_schedule.py tests/capabilities/test_langchain_adapter.py tests/harness/test_capability_adapter.py tests/mcp/test_policy.py -q` | 0 | 44 | 0 | 0 | 20 Pydantic/cache warnings |
| `$env:DEBUG='false'; uv run --no-cache --directory backend pytest -q` | 0 | 592 | 0 | 1 | 136 existing Pydantic/SQLModel/cache warnings |
| `$env:DEBUG='false'; uv run --no-cache --directory backend ruff check app tests` | 0 | all checks | 0 | 0 | none |
| `git diff --check` | 0 | - | - | - | CRLF conversion warnings only |

Not run: frontend lint/typecheck/test/build, Docker, external services, and production migrations; BATCH-10 is backend-only and forbids changes to those surfaces.

## 5. Review

```yaml
review_result:
  batch: BATCH-10
  kind: batch
  verdict: pass
  summary: "Final review of the complete uncommitted diff passed after one remediation round. No blocker, critical, high, or unhandled medium findings remain."
  findings: []
  acceptance_checks:
    task_complete: true
    scope_compliant: true
    tests_verified: true
    architecture_compliant: true
    authorization_checked: true
    side_effects_checked: true
    recovery_checked: true
    compatibility_checked: true
    documentation_consistent: true
    rollback_available: true
  reviewed_commands:
    - command: "$env:DEBUG='false'; uv run --no-cache --directory backend pytest tests/capabilities/test_schedule.py tests/capabilities/test_langchain_adapter.py tests/harness/test_capability_adapter.py tests/mcp/test_policy.py -q"
      exit_code: 0
    - command: "$env:DEBUG='false'; uv run --no-cache --directory backend pytest -q"
      exit_code: 0
    - command: "$env:DEBUG='false'; uv run --no-cache --directory backend ruff check app tests"
      exit_code: 0
    - command: "git diff --check"
      exit_code: 0
  reviewed_files:
    - backend/app/capabilities/schedule.py
    - backend/app/capabilities/langchain_adapter.py
    - backend/app/harness/policy.py
    - backend/app/harness/capability_adapter.py
    - backend/tests/capabilities/test_schedule.py
    - backend/tests/capabilities/test_langchain_adapter.py
    - backend/tests/harness/test_capability_adapter.py
    - backend/tests/mcp/test_policy.py
    - docs/harness-execution/BATCH-10-execution.md
  deferred_findings: []
```

Remediation rounds: 1. The review corrected fail-closed idempotency enforcement for all side effects and a prerequisite commit reference typo; all verification was rerun.

## 6. Handoff

```yaml
batch_result:
  batch: BATCH-10
  status: committed
  commit: "0c7d3be"
  tasks_completed:
    - "Identity-free Schedule public schemas and LangChain tool schemas"
    - "Trusted Principal injection through CapabilityAdapter"
    - "Default-deny side-effect policy with server-side Approval"
    - "Durable idempotency port replay/conflict integration for Schedule writes"
    - "Authenticated reads and Domain Service resource authorization preservation"
  tests:
    passed:
      - "44 targeted BATCH-10 regression tests"
      - "592 full backend tests"
      - "ruff check app tests"
      - "git diff --check"
    failed: []
    skipped:
      - "1 optional full-backend test (external PostgreSQL URL not configured)"
  review:
    verdict: pass
    rounds: 1
    deferred_findings: []
  changed_files:
    - backend/app/capabilities/langchain_adapter.py
    - backend/app/capabilities/schedule.py
    - backend/app/harness/capability_adapter.py
    - backend/app/harness/policy.py
    - backend/tests/capabilities/test_langchain_adapter.py
    - backend/tests/capabilities/test_schedule.py
    - backend/tests/harness/test_capability_adapter.py
    - backend/tests/mcp/test_policy.py
    - docs/harness-execution/BATCH-10-execution.md
  unresolved_risks:
    - "Approval lifecycle persistence/revocation and production wiring remain follow-up work; this Batch accepts only trusted server-side Approval objects."
    - "Frontend and non-Schedule write capabilities remain outside this Batch."
  next_batch: "Re-read docs/harness-tasks/INDEX.md after handoff commit."
```
