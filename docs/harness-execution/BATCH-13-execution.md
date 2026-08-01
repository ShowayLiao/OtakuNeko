# BATCH-13 Execution Record

Batch: BATCH-13
Task: TASK-HARNESS-013
Date: 2026-08-01 Asia/Shanghai
Branch: feature-harness
Start commit: d329916a5d1a504345f3e14e4c763556cf39144c
Record status: in_progress

## 1. Preflight

Workspace was clean. The prerequisite BATCH-12 implementation commit is
7a8167b and its handoff finalization commit is d329916.

Loaded:

- AGENTS.md
- docs/architecture/standard-agent-harness-reference.md
- docs/standard-agent-harness-reference-and-codex-audit-guide.md
- docs/harness-audit/06-observability-and-evals.md
- docs/harness-audit/00-executive-summary.md
- docs/harness-audit/02-runtime-flow.md
- docs/harness-audit/05-security-boundaries.md
- docs/harness-audit/07-gap-analysis.md
- docs/harness-audit/09-migration-plan.md
- docs/harness-tasks/INDEX.md
- docs/harness-tasks/BATCH-13/TASK-HARNESS-013.md
- docs/code-review.md

Audit completeness: complete for the current Batch.
Task-plan completeness: complete for the current Batch.

Baseline:

| Command | Exit | Passed | Failed | Skipped | Warnings/notes |
|---|---:|---:|---:|---:|---|
| $env:DEBUG='false'; uv run --no-cache --directory backend pytest tests/trace tests/evaluation tests/harness tests/acceptance -q | 0 | 207 | 0 | 1 | 76 known Pydantic/SQLAlchemy deprecation warnings |

## 2. Scope

Allowed implementation files are the Trace/Eval/metrics/reporting files,
corresponding Trace/Eval tests, and the existing read-only CI workflow job.
Production business behavior, provider selection, tool schemas, database
migrations, frontend protocol, and external production providers are out of
scope.

Authorized scope amendment on 2026-08-01 adds the actual fake Event
normalization boundary (`backend/app/evaluation/adapter.py`), the lazy harness
package import boundary (`backend/app/harness/__init__.py`), Runtime trace
projection (`backend/app/harness/runtime.py`), versioned observability dataset
and config, and corresponding harness tests. These files are limited to
observability/test-fixture/CLI import behavior and do not change business
actions, provider selection, Tool schemas, migrations, or frontend protocol.

## 3. Implementation

Implemented the Trace schema/recorder safety metadata, SQL fallback redaction,
legacy mapping, Eval observability contracts/aggregation/report budget
metadata, fake Event normalization, versioned observability fixtures, Runtime
Trace correlation, lazy harness imports, and CI fast-job observability checks.
Added focused Trace/Eval/Harness regression tests. No business action,
provider selection, Tool schema, database migration, or frontend protocol was
changed.

## 4. Verification

| Command | Exit | Passed | Failed | Skipped | Warnings/notes |
|---|---:|---:|---:|---:|---|
| `$env:DEBUG='false'; uv run --no-cache --directory backend pytest tests/trace tests/evaluation tests/harness tests/acceptance -q` | 0 | 207 | 0 | 1 | 76 known Pydantic/SQLAlchemy deprecation warnings |
| `$env:DEBUG='false'; uv run --no-cache --directory backend pytest tests/trace/test_event_contract.py tests/trace/test_sql_store.py tests/evaluation/test_metrics.py tests/evaluation/test_runner.py tests/evaluation/test_dataset.py -q --disable-warnings` | 0 | 52 | 0 | 0 | 64 warnings suppressed from display |
| `uv run --no-cache --directory backend ruff check app tests` | 0 | all | 0 | 0 | none |
| `$env:DEBUG='false'; uv run --no-cache --directory backend pytest tests/trace tests/evaluation tests/harness tests/acceptance -q --disable-warnings` | 0 | 211 | 0 | 1 | 81 warnings suppressed from display |
| `$env:DEBUG='false'; uv run --no-cache --directory backend pytest tests/evaluation tests/trace tests/harness tests/acceptance -q --disable-warnings` | 0 | 218 | 0 | 1 | 83 warnings suppressed from display |
| `$env:DEBUG='false'; uv run --no-cache --directory backend pytest -q --disable-warnings` | 0 | 628 | 0 | 1 | 142 warnings suppressed from display |
| `git diff --check` | 0 | — | 0 | 0 | Git ignore/LF warnings are non-blocking |
| `$env:DEBUG='false'; uv run --no-cache --directory backend python -m app.evaluation.runner --config evals/config/fast.yaml --report backend/.runtime/evaluation/batch13-fast.json` | 0 | 9 | 0 | 0 | Passed after lazy import remediation; initial attempt failed with the recorded circular import |
| `$env:DEBUG='false'; uv run --no-cache --directory backend python -m app.evaluation.runner --config evals/config/observability.yaml --report backend/.runtime/evaluation/batch13-observability.json` | 0 | 14 | 0 | 0 | Dataset `v1-observability`; no gate failures; report contains no fake secrets |
| `pnpm.cmd --dir frontend test` (equivalent to `pnpm --dir frontend test`) | 0 | 41 | 0 | 0 | 9 test files passed; PowerShell pnpm.ps1 policy required pnpm.cmd |

Frontend lint/typecheck/build were not run; the task requires the frontend
Vitest regression, which passed. No frontend files were modified.

## 5. Initial Review (before authorized scope amendment)

Review covered the complete uncommitted diff and found blockers; Review did
not modify code.

```yaml
review_result:
  batch: BATCH-13
  verdict: blocked
  summary: "In-scope checks pass, but actual Eval event ingestion, complete dataset coverage, and the CI-equivalent Eval CLI cannot be closed within the allowed files."
  findings:
    - id: REVIEW-001
      severity: blocker
      category: architecture
      file: backend/app/evaluation/adapter.py
      symbol: normalize_events
      evidence: "Only route, tool_call_end, message_chunk, structured_response, and recovery are normalized; the newly supported observability event types never populate ExecutionResult."
      impact: "Trace/Eval/Metrics are not connected to the real fake Run/Event stream, so cost, latency, and recovery gates read defaults."
      required_action: "Allow the actual event-normalization boundary to populate run_status, tool/policy/recovery/model/usage fields and add an end-to-end fake-adapter regression."
    - id: REVIEW-002
      severity: blocker
      category: testing
      file: backend/evals/datasets/v1.jsonl
      symbol: dataset cases
      evidence: "The real v1 dataset remains limited to existing normal/routing/safety/provider-failure/cancellation cases; this diff only tests ScriptEvent construction and does not add the required tool args/failure, policy deny, identity spoof, tool injection, memory poisoning, timeout/reconnect, multi-provider, and qB unauthorized cases."
      impact: "The required dataset-level security/recovery baseline is not established."
      required_action: "Allow versioned Eval dataset/manifest changes with fake values and assertions for every required scenario."
    - id: REVIEW-003
      severity: blocker
      category: operations
      file: backend/app/harness/__init__.py
      symbol: package import chain
      evidence: "The CI-equivalent `python -m app.evaluation.runner` command exits 1 because runner -> evaluation.adapter -> agents.langgraph_adapter -> harness.__init__ -> runtime -> coordinator re-imports the partially initialized langgraph_adapter and raises ImportError for adapt_langgraph_event."
      impact: "The CI Eval CLI gate cannot pass."
      required_action: "Fix or separately approve the import-boundary change, then rerun the complete CI-equivalent command."
    - id: REVIEW-004
      severity: high
      category: compatibility
      file: backend/app/harness/runtime.py
      symbol: _record_stream_trace
      evidence: "This path directly constructs TraceEvent without TraceRecorder._new_event, so event.run_id and sequence remain unset; this Batch only covers recorder-created events."
      impact: "Real Runtime route/agent_result traces cannot guarantee the shared Run correlation fields."
      required_action: "Allow a Runtime trace projection or controlled Trace-model entry point to fill shared run_id/sequence, with a real stream-trace regression."
    - id: REVIEW-005
      severity: medium
      category: compatibility
      file: backend/app/trace/sql_store.py
      symbol: _model_to_trace
      evidence: "Legacy headers/step JSON without schema_version are loaded with the new Pydantic default 2 rather than an explicit legacy mapping."
      impact: "Old traces remain readable but cannot be distinguished from the new schema for migration diagnostics."
      required_action: "Add explicit legacy-version mapping and regression coverage."
    - id: REVIEW-006
      severity: medium
      category: correctness
      file: backend/app/evaluation/metrics.py
      symbol: observability_snapshot
      evidence: "When model_call_count > 0 and estimated_cost_usd is None, estimated_cost_unknown_count is raised to at most 1 rather than the number of unknown model calls."
      impact: "Unknown cost is understated for multi-call executions."
      required_action: "Count unknown usage/cost per affected call and add a multi-call regression."
  acceptance_checks:
    task_complete: false
    scope_compliant: true
    tests_verified: false
    architecture_compliant: false
    authorization_checked: true
    side_effects_checked: true
    recovery_checked: false
    compatibility_checked: false
    documentation_consistent: false
    rollback_available: true
  reviewed_commands:
    - command: "uv run --no-cache --directory backend ruff check app tests"
      exit_code: 0
    - command: "$env:DEBUG='false'; uv run --no-cache --directory backend pytest -q --disable-warnings"
      exit_code: 0
    - command: "$env:DEBUG='false'; uv run --no-cache --directory backend python -m app.evaluation.runner --config evals/config/fast.yaml"
      exit_code: 1
  reviewed_files:
    - .github/workflows/evaluation.yml
    - backend/app/evaluation/types.py
    - backend/app/evaluation/metrics.py
    - backend/app/evaluation/runner.py
    - backend/app/evaluation/reporting.py
    - backend/app/trace/__init__.py
    - backend/app/trace/recorder.py
    - backend/app/trace/sql_store.py
    - backend/tests/evaluation/test_dataset.py
    - backend/tests/evaluation/test_metrics.py
    - backend/tests/evaluation/test_runner.py
    - backend/tests/trace/test_event_contract.py
    - backend/tests/trace/test_sql_store.py
    - docs/harness-execution/BATCH-13-execution.md
  deferred_findings:
    - "Real provider price table, OpenTelemetry backend, and production metrics deployment choice remain unresolved as required risks."
```

## 5.1 Final Review

The authorized scope amendment was applied, all prior blockers were
remediated, and the complete current diff was reviewed again without code
changes.

```yaml
review_result:
  batch: BATCH-13
  kind: batch
  verdict: pass
  summary: "Trace/Eval observability is connected to the fake Run/Event path; required fixture scenarios, shared Runtime Trace identifiers, legacy mapping, and CI-equivalent commands are covered."
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
    - command: "uv run --no-cache --directory backend ruff check app tests"
      exit_code: 0
    - command: "$env:DEBUG='false'; uv run --no-cache --directory backend pytest tests/trace tests/evaluation tests/harness tests/acceptance -q --disable-warnings"
      exit_code: 0
    - command: "$env:DEBUG='false'; uv run --no-cache --directory backend pytest -q --disable-warnings"
      exit_code: 0
    - command: "$env:DEBUG='false'; uv run --no-cache --directory backend python -m app.evaluation.runner --config evals/config/fast.yaml"
      exit_code: 0
    - command: "$env:DEBUG='false'; uv run --no-cache --directory backend python -m app.evaluation.runner --config evals/config/observability.yaml"
      exit_code: 0
    - command: "pnpm.cmd --dir frontend test"
      exit_code: 0
    - command: "git diff --check"
      exit_code: 0
  reviewed_files:
    - .github/workflows/evaluation.yml
    - backend/app/evaluation/adapter.py
    - backend/app/evaluation/types.py
    - backend/app/evaluation/metrics.py
    - backend/app/evaluation/runner.py
    - backend/app/evaluation/reporting.py
    - backend/app/harness/__init__.py
    - backend/app/harness/runtime.py
    - backend/app/trace/__init__.py
    - backend/app/trace/recorder.py
    - backend/app/trace/sql_store.py
    - backend/evals/config/observability.yaml
    - backend/evals/datasets/v1-observability.jsonl
    - backend/tests/evaluation/test_cli.py
    - backend/tests/evaluation/test_dataset.py
    - backend/tests/evaluation/test_metrics.py
    - backend/tests/evaluation/test_runner.py
    - backend/tests/trace/test_agent_instrumentation.py
    - backend/tests/trace/test_event_contract.py
    - backend/tests/trace/test_sql_store.py
    - docs/harness-tasks/BATCH-13/TASK-HARNESS-013.md
    - docs/harness-execution/BATCH-13-execution.md
  deferred_findings:
    - "Real provider price tables, OpenTelemetry backend, and production metrics deployment choice remain unresolved as task-specified risks."
```

Remediation rounds: 1. The first review found six findings; the authorized
scope amendment and remediation closed all non-deferred findings.

## 6. Handoff

```yaml
batch_result:
  batch: BATCH-13
  status: committed
  commit: null
  tasks_completed:
    - TASK-HARNESS-013
  tests:
    passed:
      - "Trace/Eval/Harness/Acceptance: 218 passed, 1 skipped"
      - "full backend: 628 passed, 1 skipped"
      - "observability Eval: 14 passed, no gate failures"
      - "fast Eval: 9 passed, no gate failures"
      - "frontend Vitest: 41 passed across 9 files"
      - "ruff check app tests"
      - "git diff --check"
    failed:
      - "none after remediation"
    skipped:
      - "frontend lint/typecheck/build: not required because frontend files were unchanged"
  review:
    verdict: pass
    rounds: 1
    deferred_findings:
      - "Real provider price tables, OpenTelemetry backend, and production metrics deployment choice remain unresolved."
  changed_files:
    - .github/workflows/evaluation.yml
    - backend/app/evaluation/adapter.py
    - backend/app/evaluation/types.py
    - backend/app/evaluation/metrics.py
    - backend/app/evaluation/runner.py
    - backend/app/evaluation/reporting.py
    - backend/app/harness/__init__.py
    - backend/app/harness/runtime.py
    - backend/app/trace/__init__.py
    - backend/app/trace/recorder.py
    - backend/app/trace/sql_store.py
    - backend/evals/config/observability.yaml
    - backend/evals/datasets/v1-observability.jsonl
    - backend/tests/evaluation/test_cli.py
    - backend/tests/evaluation/test_dataset.py
    - backend/tests/evaluation/test_metrics.py
    - backend/tests/evaluation/test_runner.py
    - backend/tests/trace/test_agent_instrumentation.py
    - backend/tests/trace/test_event_contract.py
    - backend/tests/trace/test_sql_store.py
    - docs/harness-tasks/BATCH-13/TASK-HARNESS-013.md
    - docs/harness-execution/BATCH-13-execution.md
  unresolved_risks:
    - "Real provider prices and unknown usage remain unavailable for production cost estimation."
    - "LLM judge non-determinism remains outside the deterministic fast gate."
  next_batch: null
```
