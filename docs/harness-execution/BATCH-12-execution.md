# BATCH-12 Execution Record

Batch: BATCH-12
Task: TASK-HARNESS-012
Date: 2026-08-01 Asia/Shanghai
Branch: feature-harness
Start commit: f68a063cc324f3a524876cd08fee4c1ff89c4209
Record status: completed_pending_commit

## 1. Preflight

### Workspace and prerequisites

    git status --short: clean at start
    git branch --show-current: feature-harness
    git rev-parse HEAD: f68a063cc324f3a524cd08fee4c1ff89c4209
    worktree: ordinary single checkout
    prerequisite: BATCH-11 / f68a063cc324f3a524876cd08fee4c1ff89c4209
    allowed changes: memory interfaces/types/service/extractor/sql repository;
      graph context assembly; tool safe result/log adapter; listed tests;
      this execution record
    forbidden changes: migrations/history cleanup; qBittorrent/Schedule/Collection
      writes; frontend/provider/full Tool catalog; deletion of legacy MemoryManager
      or StoreMemoryRepository

### Authoritative material loaded

- AGENTS.md
- docs/architecture/standard-agent-harness-reference.md
- docs/standard-agent-harness-reference-and-codex-audit-guide.md
- docs/harness-audit/00-executive-summary.md
- docs/harness-audit/01-current-architecture.md
- docs/harness-audit/02-runtime-flow.md
- docs/harness-audit/05-security-boundaries.md
- docs/harness-audit/07-gap-analysis.md
- docs/harness-audit/09-migration-plan.md
- docs/harness-tasks/INDEX.md
- docs/harness-tasks/BATCH-12/TASK-HARNESS-012.md
- docs/code-review.md

Audit completeness: complete for the current Batch.
Task-plan completeness: complete for the current Batch and prerequisites.

### Baseline

| Command | Exit | Passed | Failed | Skipped | Warnings/notes |
|---|---:|---:|---:|---:|---|
| $env:DEBUG='false'; uv run --no-cache --directory backend pytest tests/memory tests/agents/test_graph_dual_node.py tests/trace/test_event_contract.py -q | 0 | 125 | 0 | 0 | 77 known pytest/Pydantic/SQLAlchemy warnings |

## 2. Implementation

- Added typed memory provenance: source type/id, confidence, verification and expiry.
- Mapped legacy SQL rows to legacy and verified=False without schema migration.
- Added bounded ContextCompiler envelopes for fixed policy, preferences, memory facts and tool data.
- Restricted fact extraction to user messages and rejected instruction/credential/approval-shaped outputs.
- Unified the active memory path through MemoryService; retained a scoped, deprecated legacy adapter.
- Added redacted, bounded Tool result and structured argument-shape logging.
- Added prompt preference escaping and protection against compiled-prompt prefix forgery.
- Preserved provenance after retriever ranking and made legacy context use safe envelopes.
- TDD evidence: new injection/provenance tests failed before implementation and passed after remediation.

## 3. Verification

| Command | Exit | Passed | Failed | Skipped | Warnings/notes |
|---|---:|---:|---:|---:|---|
| $env:DEBUG='false'; uv run --no-cache --directory backend pytest tests/memory tests/agents/test_graph_dual_node.py tests/trace/test_event_contract.py -q | 0 | 137 | 0 | 0 | 76 known deprecation warnings |
| uv run --no-cache --directory backend ruff check app tests | 0 | n/a | 0 | n/a | All checks passed |
| $env:DEBUG='false'; uv run --no-cache --directory backend pytest -q | 0 | 617 | 0 | 1 | 135 known deprecation/warning messages |
| git diff --check | 0 | n/a | 0 | n/a | LF/CRLF conversion warnings only |

Frontend lint/typecheck/test/build were not run because this Batch changed no frontend files and the task boundary is backend-only.

## 4. Review

Review was performed against the complete uncommitted diff and docs/code-review.md.

    review_result:
      batch: BATCH-12
      verdict: pass
      summary: No blocker, critical, high, or unhandled medium findings remain.
      rounds: 3
      remediation_rounds: 2
      findings: []
      resolved_findings:
        - prompt_config compiled-prefix forgery could bypass escaping
        - rendered escaped content could exceed the configured bound
        - retriever ranking projection dropped memory provenance
        - legacy aggregate summary could bypass expired-fact filtering
      reviewed_commands:
        - git status --short
        - git diff --stat
        - git diff --check
        - uv run --no-cache --directory backend pytest tests/memory tests/agents/test_graph_dual_node.py tests/trace/test_event_contract.py -q
        - uv run --no-cache --directory backend ruff check app tests
        - uv run --no-cache --directory backend pytest -q
      reviewed_files:
        - backend/app/agents/graph.py
        - backend/app/agents/tools/base.py
        - backend/app/memory/extractor.py
        - backend/app/memory/interfaces.py
        - backend/app/memory/service.py
        - backend/app/memory/sql_repository.py
        - backend/app/memory/types.py
        - backend/tests/memory/test_service_typed.py
        - backend/tests/memory/test_injection.py
        - docs/harness-execution/BATCH-12-execution.md
      deferred_findings:
        - Historical LangGraph Store records without reliable user provenance remain legacy/unverified; history migration is a separate task.
        - LLM extraction remains an additional model call and is subject to the BATCH-05/BATCH-13 budget.

## 5. Handoff

    batch_result:
      batch: BATCH-12
      status: committed_pending_handoff_finalization
      commit: null
      tasks_completed:
        - TASK-HARNESS-012
      tests:
        passed:
          - 137 targeted regression tests
          - 617 full backend tests
          - ruff check app tests
          - git diff --check
        failed: []
        skipped:
          - 1 full-backend test
      review:
        verdict: pass
        rounds: 3
        deferred_findings:
          - legacy unscoped historical data remains unverified
          - extraction model-call budget remains deferred
      changed_files:
        - backend/app/agents/graph.py
        - backend/app/agents/tools/base.py
        - backend/app/memory/extractor.py
        - backend/app/memory/interfaces.py
        - backend/app/memory/service.py
        - backend/app/memory/sql_repository.py
        - backend/app/memory/types.py
        - backend/tests/memory/test_service_typed.py
        - backend/tests/memory/test_injection.py
        - docs/harness-execution/BATCH-12-execution.md
      unresolved_risks:
        - No provenance migration was performed for old LangGraph Store history.
        - Rollback is MEMORY_TRUST_MODE=legacy-read-safe: preserve reads, block unmarked writes, do not delete facts.
      next_batch: BATCH-13
